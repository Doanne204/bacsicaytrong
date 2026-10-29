"""Máy chủ Flask "Bác sĩ cây trồng": tạo ứng dụng, gắn giao diện người dùng (client/) và trang quản trị (admin/).
Phần dùng chung phía máy chủ ở core.py; tài nguyên tĩnh dùng chung (logo, common.js, base.css) ở shared/."""
import os, re
from contextlib import closing
import click
from flask import Flask, abort, send_from_directory, session
from dotenv import load_dotenv
ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT, ".env"))  # GEMINI_API_KEY, SECRET_KEY... (không ghi đè biến đã có)
import ai_service
from model_service import ModelService, PestService
from core import (DIST_DIR, IntegrityError, KeyStore, backfill_embeddings, close_db, connect, copy_sqlite, db, deliver_reminders, init_db,
                  is_admin, is_pg, login_required, weather_notify)
from client.routes import bp as client_bp
from admin.routes import bp as admin_bp

def create_app(test_config=None):
    # shared/ phục vụ ở /static (logo, biểu tượng, ảnh giới thiệu); giao diện React build sẵn ở frontend/dist
    app = Flask(__name__, static_folder="shared", static_url_path="/static")
    app.config.update(SECRET_KEY=os.getenv("SECRET_KEY", "dev-secret-change-me"), SESSION_COOKIE_SAMESITE="Lax",
                      # PostgreSQL: DATABASE_URL=postgresql://user:mật_khẩu@localhost:5432/tên_csdl trong .env; không có thì dùng file SQLite
                      DATABASE=os.getenv("DATABASE") or os.getenv("DATABASE_URL") or os.path.join(app.instance_path, "app.db"),
                      UPLOAD_DIR=os.getenv("UPLOAD_DIR", os.path.join(app.instance_path, "uploads")),
                      AI_DATASET_DIR=os.getenv("AI_DATASET_DIR", os.path.join(ROOT, "dataset_ai")),
                      MAX_CONTENT_LENGTH=8 * 1024 * 1024)
    if test_config:
        app.config.update(test_config)
    if not is_pg(app.config["DATABASE"]):
        os.makedirs(os.path.dirname(os.path.abspath(app.config["DATABASE"])), exist_ok=True)
    init_db(app.config["DATABASE"])
    app.model = ModelService()
    app.pests = PestService()  # nhận diện sâu hại; chưa có models/pest_model.keras thì ẩn lựa chọn này
    backfill_embeddings(app)
    app.keys = KeyStore(app.config["DATABASE"], app.config["SECRET_KEY"])
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key and app.keys.keys() is None:  # lần đầu: chuyển khóa trong .env vào trang quản trị để quản lý chung
        try:
            app.keys.add("Khóa từ file .env", env_key)
        except IntegrityError:  # tiến trình server khác vừa thêm cùng lúc
            pass
    ai_service.configure(app.keys)
    app.teardown_appcontext(close_db)
    app.register_blueprint(client_bp)  # / và API người dùng
    app.register_blueprint(admin_bp)  # /admin và /api/admin/*

    @app.get("/uploads/<kind>/<name>")
    @login_required
    def uploads(kind, name):
        rel, uid, admin = f"{kind}/{name}", session["uid"], int(is_admin())
        if kind == "scans":  # ảnh tra cứu, ảnh thêm <tên>-p2/-p3.jpg, ảnh tô vết hại [-p2]-lesion.jpg, bản đồ nhiệt cũ -cam[-<mã>].jpg:
            # của mình, hoặc đã được chia sẻ trong bài viết đã duyệt
            base = re.sub(r"(-p[23])?(-(cam(-[0-9a-f]{8})?|lesion))?\.jpg$", ".jpg", rel)
            ok = db().execute("SELECT 1 FROM diagnoses d WHERE d.image=? AND (d.user_id=? OR ?=1 OR EXISTS (SELECT 1 FROM posts p "
                              "WHERE p.diagnosis_id=d.id AND p.status='approved'))", (base, uid, admin)).fetchone()
        elif kind == "posts":
            ok = db().execute("SELECT 1 FROM posts WHERE image=? AND (status='approved' OR user_id=? OR ?=1)", (rel, uid, admin)).fetchone()
        elif kind == "chats":  # ảnh gửi trong chat: chỉ chủ cuộc trò chuyện
            ok = db().execute("SELECT 1 FROM chats WHERE image=? AND user_id=?", (rel, uid)).fetchone()
        elif kind == "treatments":  # ảnh trong nhật ký điều trị: chỉ chủ nhật ký
            ok = db().execute("SELECT 1 FROM treatment_logs WHERE image=? AND user_id=?", (rel, uid)).fetchone()
        else:
            ok = None
        if not ok:
            abort(404)
        return send_from_directory(os.path.join(app.config["UPLOAD_DIR"], kind), name)

    @app.get("/favicon.ico")  # trình duyệt tự xin đường dẫn này
    def favicon():
        return send_from_directory(os.path.join(ROOT, "shared", "img"), "favicon.ico")

    @app.get("/sw.js")  # service worker (frontend/public/sw.js) phải nằm ở gốc trang mới điều khiển được mọi đường dẫn
    def service_worker():
        resp = send_from_directory(DIST_DIR, "sw.js", max_age=0)
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.get("/assets/<path:name>")  # JS/CSS do Vite build, tên file có mã băm nên cache được lâu
    def assets(name):
        return send_from_directory(os.path.join(DIST_DIR, "assets"), name, max_age=31536000)

    @app.cli.command("build-centroids")
    @click.argument("data_dir")
    @click.option("--per-class", default=60, help="Số ảnh mỗi lớp dùng để tính tâm")
    def build_centroids(data_dir, per_class):
        """Tính tâm vector đặc trưng mỗi lớp (để nhận ra ảnh cây lạ). Chạy lại mỗi khi đổi mô hình:
        flask --app app build-centroids dataset/Plant_leave_diseases_dataset_without_augmentation"""
        app.model.build_centroids(data_dir, per_class)
        click.echo(f"Đã lưu tâm {len(app.model.class_names)} lớp cho {app.model.embed_key}")

    @app.cli.command("make-admin")
    @click.argument("username")
    def make_admin(username):
        """Cấp quyền quản trị: flask --app app make-admin <tên đăng nhập>"""
        with closing(connect(app.config["DATABASE"])) as c:
            n = c.execute("UPDATE users SET role='admin', verified=1 WHERE username=?", (username,)).rowcount
            c.commit()
        click.echo(f"Đã cấp quyền quản trị cho {username}" if n else f"Không tìm thấy tài khoản {username}")

    @app.cli.command("remind")
    @click.option("--no-weather", is_flag=True, help="Chỉ nhắc việc, không gửi cảnh báo thời tiết")
    def remind(no_weather):
        """Gửi nhắc việc đến hạn (thông báo + email) và cảnh báo sâu bệnh mức cao theo thời tiết cho người đã lưu vị trí.
        Đặt lịch chạy mỗi sáng: flask --app app remind (xem README)."""
        with closing(connect(app.config["DATABASE"])) as c:
            n = deliver_reminders(c, email=True)
            click.echo(f"Đã gửi {n} nhắc việc")
            if not no_weather:
                click.echo(f"Đã gửi {weather_notify(c)} cảnh báo thời tiết")

    @app.cli.command("export-dataset")
    @click.argument("out_dir", default="dataset_ai_duyet")
    def export_dataset(out_dir):
        """Chép các mẫu AI đã được quản trị viên duyệt sang out_dir/<lớp>/ để huấn luyện lại (mẫu chờ duyệt không chép):
        flask --app app export-dataset dataset_ai_duyet, rồi python train.py --data ... --extra dataset_ai_duyet"""
        import shutil
        root = app.config["AI_DATASET_DIR"]
        mark = os.path.join(out_dir, ".xuat-tu-dataset-ai")
        if os.path.isdir(out_dir) and os.listdir(out_dir) and not os.path.exists(mark):
            raise click.ClickException(f"{out_dir} đã có dữ liệu khác, hãy chọn thư mục mới")
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir)  # xuất lại từ đầu (chỉ thư mục do lệnh này tạo): mẫu đã bị xóa / đổi nhãn không còn sót
        os.makedirs(out_dir)
        open(mark, "w").close()
        with closing(connect(app.config["DATABASE"])) as c:
            rows = c.execute("SELECT class_name, path FROM ai_samples WHERE status='approved'").fetchall()
        n = 0
        for r in rows:
            src = os.path.join(root, r["path"])
            if os.path.exists(src):
                os.makedirs(os.path.join(out_dir, r["class_name"]), exist_ok=True)
                shutil.copy2(src, os.path.join(out_dir, r["class_name"], os.path.basename(src)))
                n += 1
        click.echo(f"Đã chép {n} ảnh đã duyệt ({len({r['class_name'] for r in rows})} lớp) vào {out_dir}")

    @app.cli.command("import-sqlite")
    @click.argument("sqlite_path", default=os.path.join("instance", "app.db"))
    def import_sqlite(sqlite_path):
        """Chép dữ liệu từ file SQLite cũ sang PostgreSQL (DATABASE_URL), giữ nguyên id: flask --app app import-sqlite instance/app.db"""
        if not is_pg(app.config["DATABASE"]):
            raise click.ClickException("Chưa cấu hình DATABASE_URL=postgresql://... trong file .env")
        if not os.path.exists(sqlite_path):
            raise click.ClickException(f"Không thấy file {sqlite_path}")
        try:
            counts = copy_sqlite(sqlite_path, app.config["DATABASE"])
        except RuntimeError as e:
            raise click.ClickException(str(e))
        click.echo("Đã chép: " + ", ".join(f"{t} {n}" for t, n in counts.items()))

    return app

if __name__ == "__main__":
    # Không bật debug: trình gỡ lỗi Werkzeug cho phép chạy mã từ xa khi mở ra mạng LAN
    create_app().run(host="0.0.0.0", port=5000)
