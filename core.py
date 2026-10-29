"""Phần dùng chung phía máy chủ cho giao diện người dùng (client/) và trang quản trị (admin/):
CSDL (PostgreSQL; SQLite khi chạy kiểm thử), khóa Gemini mã hóa, đăng nhập và phân quyền, thông báo, ảnh tải lên, bài viết."""
import base64, hashlib, io, json, os, re, secrets, smtplib, sqlite3, time, uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps
import psycopg2, psycopg2.errors, psycopg2.extensions, psycopg2.extras
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app, g, jsonify, request, session
from werkzeug.security import check_password_hash
from PIL import Image, ImageOps

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL, phone TEXT, pw TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user', created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS diagnoses(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, plant_id TEXT, plant TEXT, disease TEXT, raw TEXT, healthy INTEGER, confidence REAL, remedy TEXT, image TEXT, source TEXT DEFAULT 'model', details TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS chats(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, diagnosis_id INTEGER, role TEXT, content TEXT, image TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS ratings(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, diagnosis_id INTEGER, stars INTEGER NOT NULL, comment TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, content TEXT, image TEXT, status TEXT NOT NULL DEFAULT 'pending', ai_decision TEXT, ai_reason TEXT, feedback TEXT, reviewed_by INTEGER, reviewed TEXT, diagnosis_id INTEGER, shared_post_id INTEGER, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS post_likes(post_id INTEGER NOT NULL, user_id INTEGER NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(post_id, user_id));
CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY, post_id INTEGER NOT NULL, user_id INTEGER NOT NULL, content TEXT NOT NULL, ai_decision TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS post_shares(id INTEGER PRIMARY KEY, post_id INTEGER NOT NULL, user_id INTEGER NOT NULL, kind TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, content TEXT NOT NULL, link TEXT, read INTEGER NOT NULL DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS ai_classes(class_name TEXT PRIMARY KEY, plant_id TEXT NOT NULL, plant TEXT NOT NULL, disease TEXT NOT NULL, healthy INTEGER NOT NULL, remedy TEXT, samples INTEGER NOT NULL DEFAULT 0, updated TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS ai_samples(id INTEGER PRIMARY KEY, user_id INTEGER, diagnosis_id INTEGER, class_name TEXT NOT NULL, path TEXT NOT NULL, confidence REAL, embedding BLOB, embed_key TEXT, status TEXT NOT NULL DEFAULT 'pending', reviewed TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS ai_keys(id INTEGER PRIMARY KEY, label TEXT NOT NULL, key_enc TEXT NOT NULL, key_hash TEXT UNIQUE NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, ok_count INTEGER NOT NULL DEFAULT 0, fail_count INTEGER NOT NULL DEFAULT 0, last_used TEXT, last_error TEXT, last_error_at TEXT, cooldowns TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS email_codes(id INTEGER PRIMARY KEY, email TEXT NOT NULL, code TEXT NOT NULL, purpose TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS treatments(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, diagnosis_id INTEGER, name TEXT, plant TEXT, disease TEXT, status TEXT NOT NULL DEFAULT 'active', created TEXT DEFAULT CURRENT_TIMESTAMP, closed TEXT);
CREATE TABLE IF NOT EXISTS treatment_logs(id INTEGER PRIMARY KEY, treatment_id INTEGER NOT NULL, user_id INTEGER NOT NULL, kind TEXT NOT NULL DEFAULT 'khac', content TEXT, image TEXT, done_at TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY, treatment_id INTEGER NOT NULL, user_id INTEGER NOT NULL, content TEXT NOT NULL, due TEXT NOT NULL, repeat_days INTEGER NOT NULL DEFAULT 0, done INTEGER NOT NULL DEFAULT 0, notified INTEGER NOT NULL DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS lookup_cache(key TEXT PRIMARY KEY, data TEXT NOT NULL, user_id INTEGER, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY, user_id INTEGER, diagnosis_id INTEGER NOT NULL, class_name TEXT, plant TEXT, disease TEXT, note TEXT, old_label TEXT, status TEXT NOT NULL DEFAULT 'open', answer TEXT, reviewed_by INTEGER, reviewed TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS push_subs(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, endpoint TEXT UNIQUE NOT NULL, p256dh TEXT NOT NULL, auth TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
"""
# Cột thêm vào CSDL tạo từ phiên bản cũ (CREATE TABLE IF NOT EXISTS không tự thêm cột)
MIGRATIONS = {"users": {"phone": "TEXT", "role": "TEXT NOT NULL DEFAULT 'user'", "locked": "INTEGER NOT NULL DEFAULT 0",
                        "verified": "INTEGER NOT NULL DEFAULT 0", "lat": "REAL", "lon": "REAL", "place": "TEXT", "weather_notified": "TEXT",
                        "google_sub": "TEXT"},
              "diagnoses": {"image": "TEXT", "source": "TEXT DEFAULT 'model'", "details": "TEXT", "lat": "REAL", "lon": "REAL"},
              # mẫu AI có từ trước khi có bước duyệt: chưa ai rà soát nên cũng là "chờ duyệt"
              "ai_samples": {"embedding": "BLOB", "embed_key": "TEXT", "status": "TEXT NOT NULL DEFAULT 'pending'", "reviewed": "TEXT"},
              "chats": {"image": "TEXT"},
              "posts": {"diagnosis_id": "INTEGER", "shared_post_id": "INTEGER"}}

def norm_phone(p):
    """'+84 912.345.678' -> '0912345678'."""
    p = re.sub(r"[\s.\-()]", "", p or "")
    if p.startswith("+84"):
        p = "0" + p[3:]
    elif p.startswith("84") and len(p) == 11:
        p = "0" + p[2:]
    return p

# ---------- Kết nối CSDL: PostgreSQL (DATABASE_URL=postgresql://...) hoặc file SQLite (mặc định khi chạy kiểm thử) ----------
# Câu SQL trong ứng dụng viết một lần với dấu ? như sqlite3; PgConn đổi sang cú pháp psycopg2 khi chạy PostgreSQL.
# PostgreSQL trả dữ liệu giống SQLite để phần còn lại không phải đổi: thời gian là chuỗi "YYYY-MM-DD HH:MM:SS" giờ UTC,
# số thập phân (AVG) là float, True/False lưu thành 1/0 như các cột cờ kiểu INTEGER.
ext = psycopg2.extensions
ext.register_type(ext.new_type((1114,), "TIMESTAMP_TEXT", lambda v, cur: v[:19] if v is not None else None))
ext.register_type(ext.new_type(ext.DECIMAL.values, "DECIMAL_FLOAT", lambda v, cur: float(v) if v is not None else None))
ext.register_adapter(bool, lambda b: ext.AsIs(int(b)))
IntegrityError = (sqlite3.IntegrityError, psycopg2.IntegrityError)
TABLES = ["users", "diagnoses", "chats", "ratings", "posts", "post_likes", "comments", "post_shares", "notifications",
          "ai_classes", "ai_samples", "ai_keys", "settings", "treatments", "treatment_logs", "reminders", "lookup_cache",
          "reports", "push_subs"]

def is_pg(target):
    return str(target).startswith(("postgresql://", "postgres://"))

class PgConn:
    """Kết nối PostgreSQL dùng giống sqlite3.Connection: execute(sql với dấu ?, tham số), executescript, commit, close.
    Dòng kết quả đọc được cả theo tên cột (r["id"]) lẫn chỉ số (r[0]) như sqlite3.Row."""

    def __init__(self, url):
        self.raw = psycopg2.connect(url, cursor_factory=psycopg2.extras.DictCursor)
        self.executescript("SET TIME ZONE 'UTC'; SET DateStyle TO ISO, YMD")  # CURRENT_TIMESTAMP lưu giờ UTC như SQLite

    def execute(self, sql, params=()):
        cur = self.raw.cursor()
        # ? -> %s (giữ nguyên dấu % có sẵn); LIKE của SQLite không phân biệt hoa thường -> ILIKE
        cur.execute(re.sub(r"\bLIKE\b", "ILIKE", sql.replace("%", "%%").replace("?", "%s")), tuple(params))
        return cur

    def executescript(self, sql):
        self.raw.cursor().execute(sql)
        self.raw.commit()

    def commit(self):
        self.raw.commit()

    def close(self):
        self.raw.close()

def connect(target):
    """target: URL postgresql://... hoặc đường dẫn file SQLite."""
    if is_pg(target):
        return PgConn(target)
    c = sqlite3.connect(target, timeout=5)
    c.row_factory = sqlite3.Row
    return c

def pg_types(sql):
    """Kiểu cột SQLite -> PostgreSQL: khóa tự tăng, số thực, nhị phân, cột thời gian."""
    sql = sql.replace("INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY").replace(" REAL", " DOUBLE PRECISION").replace("BLOB", "BYTEA")
    return re.sub(r"\b(created|updated|reviewed|last_used|last_error_at) TEXT", r"\1 TIMESTAMP", sql)

def create_pg_database(url):
    """Tạo CSDL ghi trong URL nếu chưa có (kết nối vào CSDL mặc định "postgres" để tạo)."""
    p = ext.parse_dsn(url)
    try:
        c = psycopg2.connect(**{**p, "dbname": "postgres"})
    except psycopg2.Error:  # không vào được CSDL "postgres": coi như CSDL đã có, lỗi thật (nếu có) hiện khi kết nối
        return
    c.autocommit = True
    with closing(c):
        cur = c.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (p["dbname"],))
        if not cur.fetchone():
            try:
                cur.execute(f'CREATE DATABASE "{p["dbname"]}"')
            except psycopg2.errors.DuplicateDatabase:  # tiến trình server khác vừa tạo
                pass

def table_columns(c, table, pg):
    if pg:
        return [r[0] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() "
                                        "AND table_name=? ORDER BY ordinal_position", (table,))]
    return [r[1] for r in c.execute(f"PRAGMA table_info({table})")]

def init_db(target):
    pg = is_pg(target)
    if pg:
        create_pg_database(target)
    with closing(connect(target)) as c:
        if pg:  # 2 tiến trình (cổng 5000, 5443) khởi động cùng lúc: tạo bảng lần lượt
            c.execute("SELECT pg_advisory_lock(20261027)")
        c.executescript(pg_types(SCHEMA) if pg else SCHEMA)
        for table, cols in MIGRATIONS.items():
            have = table_columns(c, table, pg)
            for col, typ in cols.items():
                if col not in have:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {pg_types(typ) if pg else typ}")
                    if (table, col) == ("users", "verified"):  # tài khoản tạo trước khi có xác thực email: coi như đã xác thực
                        c.execute("UPDATE users SET verified=1")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_phone ON users(phone)")
        c.commit()

def copy_sqlite(path, target):
    """Chép mọi bảng từ file SQLite cũ sang CSDL PostgreSQL (đã tạo bảng), giữ nguyên id; trả về {bảng: số dòng}."""
    with closing(connect(path)) as s, closing(connect(target)) as d:
        if d.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            raise RuntimeError("CSDL PostgreSQL đã có người dùng; để tránh ghi đè, chỉ chép vào CSDL mới (chưa có tài khoản nào).")
        d.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY")  # bỏ dòng tự sinh lúc khởi động (VD khóa Gemini nhập từ .env)
        counts = {}
        for t in TABLES:
            want = table_columns(d, t, True)
            cols = [col for col in table_columns(s, t, False) if col in want]
            rows = s.execute(f"SELECT {', '.join(cols)} FROM {t}").fetchall() if cols else []
            for r in rows:
                d.execute(f"INSERT INTO {t}({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})", tuple(r))
            if "id" in cols:  # bộ đếm id tiếp tục sau id lớn nhất đã chép
                d.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {t}")
            counts[t] = len(rows)
        d.commit()
    return counts

class KeyStore:
    """Khóa Gemini lưu mã hóa (Fernet, khóa suy ra từ SECRET_KEY) trong bảng ai_keys; ai_service đọc qua keys()/models()/report().
    Lượt dùng và thời điểm hết hạn mức lưu trong CSDL nên 2 tiến trình (cổng 5000 và 5443) dùng chung."""

    def __init__(self, target, secret):
        self.target = target
        self.fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(("gemini-keys:" + secret).encode()).digest()))

    def _conn(self):
        return connect(self.target)

    @staticmethod
    def fingerprint(key):
        return hashlib.sha256(key.encode()).hexdigest()

    def encrypt(self, key):
        return self.fernet.encrypt(key.encode()).decode()

    def decrypt(self, token):
        try:
            return self.fernet.decrypt(token.encode()).decode()
        except InvalidToken:  # SECRET_KEY đã đổi
            return None

    def keys(self):
        """Khóa đang bật (thứ tự thêm vào); None nếu chưa có khóa nào trong CSDL (khi đó dùng GEMINI_API_KEY trong .env)."""
        with closing(self._conn()) as c:
            rows = c.execute("SELECT * FROM ai_keys ORDER BY id").fetchall()
        if not rows:
            return None
        out = []
        for r in rows:
            k = self.decrypt(r["key_enc"]) if r["enabled"] else None
            if k:
                out.append(dict(id=r["id"], label=r["label"], key=k, cooldowns=json.loads(r["cooldowns"] or "{}")))
        return out

    def models(self, fast):
        with closing(self._conn()) as c:
            r = c.execute("SELECT value FROM settings WHERE key=?", ("fast_models" if fast else "models",)).fetchone()
        return r["value"] if r and r["value"] else None

    def report(self, key_id, model, outcome, error=None, until=None):
        if not isinstance(key_id, int):  # khóa trong .env không lưu thống kê
            return
        with closing(self._conn()) as c:
            if outcome == "ok":
                c.execute("UPDATE ai_keys SET ok_count=ok_count+1, last_used=CURRENT_TIMESTAMP WHERE id=?", (key_id,))
            else:
                r = c.execute("SELECT cooldowns FROM ai_keys WHERE id=?", (key_id,)).fetchone()
                cool = {m: t for m, t in json.loads((r and r["cooldowns"]) or "{}").items() if t > time.time()}
                if until:
                    cool[model] = until
                c.execute("UPDATE ai_keys SET fail_count=fail_count+1, last_error=?, last_error_at=CURRENT_TIMESTAMP, cooldowns=? WHERE id=?",
                          (error, json.dumps(cool), key_id))
            c.commit()

    def add(self, label, key):
        with closing(self._conn()) as c:
            kid = c.execute("INSERT INTO ai_keys(label,key_enc,key_hash) VALUES(?,?,?) RETURNING id",
                            (label, self.encrypt(key), self.fingerprint(key))).fetchone()[0]
            c.commit()
            return kid

def backfill_embeddings(app):
    """Tính vector đặc trưng cho mẫu AI chưa có, hoặc đã tính bằng mô hình khác (VD sau khi huấn luyện lại)."""
    with closing(connect(app.config["DATABASE"])) as c:
        for sid, rel in c.execute("SELECT id, path FROM ai_samples WHERE embed_key IS DISTINCT FROM ?", (app.model.embed_key,)).fetchall():
            try:
                with open(os.path.join(app.config["AI_DATASET_DIR"], rel), "rb") as f:
                    e = app.model.embed(f.read())
            except OSError:
                continue
            c.execute("UPDATE ai_samples SET embedding=?, embed_key=? WHERE id=?", (e.tobytes(), app.model.embed_key, sid))
        c.commit()


# ---------- CSDL, phản hồi, đăng nhập ----------
def db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db

def close_db(_=None):
    d = g.pop("db", None)
    if d:
        d.close()

def err(msg, code=400, field=None):
    return jsonify(error=msg, field=field), code

def me_row():
    if "me" not in g:
        g.me = db().execute("SELECT * FROM users WHERE id=?", (session["uid"],)).fetchone() if "uid" in session else None
    return g.me

def is_admin():
    return bool(me_row()) and me_row()["role"] == "admin"

LOCKED = "Tài khoản đã bị khóa, hãy liên hệ quản trị viên"

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not me_row():
            return err("Vui lòng đăng nhập", 401)
        if me_row()["locked"]:  # bị khóa khi đang đăng nhập: đăng xuất luôn
            session.clear()
            return err(LOCKED, 403)
        return f(*a, **k)
    return w

def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        if not me_row():
            return err("Vui lòng đăng nhập", 401)
        if me_row()["locked"]:
            session.clear()
            return err(LOCKED, 403)
        if not is_admin():
            return err("Chỉ quản trị viên được thực hiện", 403)
        return f(*a, **k)
    return w

def notify(user_id, content, link=""):
    """Thông báo trong app, đồng thời đẩy tới điện thoại / trình duyệt người đó đã bật thông báo (push.py)."""
    db().execute("INSERT INTO notifications(user_id,content,link) VALUES(?,?,?)", (user_id, content, link))
    push_out(db(), [user_id], content, link)

def push_out(c, user_ids, content, link=""):
    """Đẩy thông báo; lỗi gửi không làm hỏng việc chính (thông báo trong app đã lưu)."""
    try:
        import push
        push.send(c, current_app.config["DATABASE"], user_ids, content, link)
    except Exception as e:
        print("[push] không gửi được:", repr(e)[:200], flush=True)

def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def deliver_reminders(c, uid=None, email=False):
    """Nhắc việc đã đến hạn (chưa làm, chưa nhắc) -> tạo thông báo trong ứng dụng, gửi email nếu email=True và đã cấu hình SMTP.
    Gọi khi người dùng mở ứng dụng (uid) và từ lệnh `flask remind` chạy theo lịch (mọi người dùng). Trả về số nhắc việc đã gửi."""
    rows = c.execute("SELECT r.id, r.user_id, r.content, r.due, r.treatment_id, t.name, t.plant, t.disease, u.email FROM reminders r "
                     "JOIN treatments t ON t.id=r.treatment_id JOIN users u ON u.id=r.user_id "
                     "WHERE r.done=0 AND r.notified=0 AND r.due<=? " + ("AND r.user_id=? " if uid else "") + "ORDER BY r.due",
                     (utcnow(), uid) if uid else (utcnow(),)).fetchall()
    by_user = {}
    for r in rows:
        title = r["name"] or f"{r['plant']}: {r['disease']}"
        c.execute("INSERT INTO notifications(user_id,content,link) VALUES(?,?,?)",
                  (r["user_id"], f"Đến hạn: {r['content']} ({title})", f"/journal/{r['treatment_id']}"))
        c.execute("UPDATE reminders SET notified=1 WHERE id=?", (r["id"],))
        by_user.setdefault((r["user_id"], r["email"]), []).append((r["content"], title))
    c.commit()
    if not uid:  # chạy theo lịch: đẩy về điện thoại (người đang mở app thì đã thấy trong app)
        for r in rows:
            title = r["name"] or f"{r['plant']}: {r['disease']}"
            push_out(c, [r["user_id"]], f"Đến hạn: {r['content']} ({title})", f"/journal/{r['treatment_id']}")
    if email and mail_configured():
        import emails
        for (_, to), items in by_user.items():
            try:
                send_mail(to, *emails.reminders_mail(items))
            except Exception as e:  # lỗi SMTP không làm hỏng việc nhắc trong ứng dụng
                print(f"[mail] lỗi gửi nhắc việc tới {to}: {e}", flush=True)
    return len(rows)

def user_plants(c, uid):
    """Id cây người dùng đã tra cứu 90 ngày qua hoặc đang theo dõi trong nhật ký (để lọc cảnh báo thời tiết liên quan)."""
    import knowledge
    since = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")
    ids = {r[0] for r in c.execute("SELECT DISTINCT plant_id FROM diagnoses WHERE user_id=? AND created>=?", (uid, since)).fetchall()}
    names = {r[0] for r in c.execute("SELECT DISTINCT plant FROM treatments WHERE user_id=? AND status='active'", (uid,)).fetchall()}
    ids |= {k for k, v in knowledge.PLANTS.items() if v in names}
    return ids - {"unknown", "background", "pest", None}

def weather_notify(c):
    """Mỗi ngày một lần: người dùng đã lưu vị trí nhận thông báo (và email) về các cảnh báo mức cao trong dự báo 5 ngày tới.
    Trả về số người đã gửi."""
    import weather
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    users = c.execute("SELECT id, email, lat, lon, place FROM users WHERE lat IS NOT NULL AND locked=0 AND (weather_notified IS NULL OR weather_notified<>?)",
                      (today,)).fetchall()
    sent = 0
    for u in users:
        try:
            alerts = [a for a in weather.assess(weather.forecast(u["lat"], u["lon"]), user_plants(c, u["id"])) if a["level"] == "cao"]
        except Exception as e:
            print(f"[weather] lỗi dự báo cho người dùng {u['id']}: {e}", flush=True)
            continue
        c.execute("UPDATE users SET weather_notified=? WHERE id=?", (today, u["id"]))
        if not alerts:
            continue
        names = ", ".join(a["name"] for a in alerts[:3])
        text = f"Cảnh báo thời tiết: nguy cơ cao {names} trong những ngày tới" + (f" tại {u['place']}" if u["place"] else "")
        c.execute("INSERT INTO notifications(user_id,content,link) VALUES(?,?,?)", (u["id"], text, "/weather"))
        push_out(c, [u["id"]], text, "/weather")
        sent += 1
        if mail_configured():
            import emails
            try:
                send_mail(u["email"], *emails.weather_mail([(a["name"], a["advice"]) for a in alerts], u["place"]))
            except Exception as e:
                print(f"[mail] lỗi gửi cảnh báo tới {u['email']}: {e}", flush=True)
    c.commit()
    return sent

# ---------- Ảnh tải lên ----------
def save_image(data, kind, name=None):
    """Xoay đúng chiều theo EXIF, thu nhỏ, lưu JPEG vào UPLOAD_DIR/kind (tên ngẫu nhiên, hoặc name cho trước, VD ảnh thêm của một lượt
    tra cứu đặt theo tên ảnh chính). Trả về (tên tương đối, bytes JPEG) hoặc (None, None)."""
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except Exception:
        return None, None
    img.thumbnail((1600, 1600))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    name = name or f"{kind}/{uuid.uuid4().hex}.jpg"
    path = os.path.join(current_app.config["UPLOAD_DIR"], name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return name, buf.getvalue()

def remove_upload(name):
    if name:
        try:
            os.remove(os.path.join(current_app.config["UPLOAD_DIR"], name))
        except OSError:
            pass

def image_url(name):
    return f"/uploads/{name}" if name else None

# ---------- Giao diện React đã build (frontend/dist) ----------
DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")

def spa_page(name):
    """index.html (người dùng) hoặc admin.html (quản trị) trong frontend/dist; chưa build thì hướng dẫn cách build."""
    path = os.path.join(DIST_DIR, name)
    if not os.path.exists(path):
        return ("<!doctype html><meta charset=utf-8><title>Chưa build giao diện</title>"
                "<body style='font-family:system-ui;max-width:40rem;margin:4rem auto;line-height:1.6'><h1>Chưa build giao diện</h1>"
                "<p>Chạy trong thư mục <code>frontend/</code>: <code>npm install</code> rồi <code>npm run build</code> "
                "(hoặc <code>npm run dev</code> để phát triển ở cổng 5173), sau đó tải lại trang.</p></body>"), 503
    with open(path, encoding="utf-8") as f:
        return f.read(), 200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-cache"}

# ---------- Giới hạn tần suất (trong bộ nhớ của từng tiến trình: chống dò mật khẩu, spam) ----------
_hits = {}

def rate_limit(key, limit, window):
    """True nếu còn trong hạn mức: tối đa `limit` lần trong `window` giây cho `key` (VD ("login", ip, tên))."""
    now = time.time()
    hits = [t for t in _hits.get(key, []) if t > now - window]
    if len(hits) >= limit:
        _hits[key] = hits
        return False
    hits.append(now)
    _hits[key] = hits
    if len(_hits) > 5000:  # dọn bớt khóa cũ
        for k in [k for k, v in _hits.items() if not v or v[-1] < now - 3600][:1000]:
            _hits.pop(k, None)
    return True

def client_ip():
    return (request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "?")

TOO_MANY = "Bạn thao tác quá nhanh, hãy thử lại sau ít phút"

# ---------- Gửi email (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_FROM trong .env) ----------
def mail_configured():
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER"))

def send_mail(to, subject, body, html=None):
    """Gửi email (văn bản thuần, kèm bản HTML của emails.py nếu có, logo đính kèm nội tuyến); chưa cấu hình SMTP thì in nội dung
    ra log và trả về False."""
    if not mail_configured():
        print(f"[mail] (chưa cấu hình SMTP) tới {to}: {subject}\n{body}", flush=True)
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, os.getenv("MAIL_FROM") or os.getenv("SMTP_USER"), to
    msg.set_content(body)
    if html:
        import emails
        msg.add_alternative(html, subtype="html")
        lg = emails.logo()
        if lg and f"cid:{lg[1]}" in html:
            msg.get_payload()[1].add_related(lg[0], "image", "png", cid=f"<{lg[1]}>")
    port = int(os.getenv("SMTP_PORT", "587"))
    with (smtplib.SMTP_SSL if port == 465 else smtplib.SMTP)(os.getenv("SMTP_HOST"), port, timeout=20) as s:
        if port != 465:
            s.starttls()
        s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS") or "")
        s.send_message(msg)
    return True

CODE_TTL = 15 * 60  # mã xác thực có hiệu lực 15 phút

def issue_code(email, purpose):
    """Tạo mã 6 số cho email (purpose: verify | reset), tối đa 1 mã/phút và 5 mã/giờ mỗi email. Trả về (mã, response lỗi)."""
    if not rate_limit(("code-min", email, purpose), 1, 60) or not rate_limit(("code-hour", email, purpose), 5, 3600):
        return None, err("Đã gửi mã rồi, hãy kiểm tra hộp thư (cả mục Spam) hoặc đợi 1 phút để gửi lại", 429)
    code = f"{secrets.randbelow(10 ** 6):06d}"
    db().execute("UPDATE email_codes SET used=1 WHERE email=? AND purpose=?", (email, purpose))
    db().execute("INSERT INTO email_codes(email,code,purpose) VALUES(?,?,?)", (email, code, purpose))
    db().commit()
    return code, None

def check_code(email, code, purpose):
    """Mã đúng, chưa dùng, chưa quá 15 phút -> đánh dấu đã dùng và trả về True."""
    r = db().execute("SELECT id, created FROM email_codes WHERE email=? AND purpose=? AND code=? AND used=0 ORDER BY id DESC LIMIT 1",
                     (email, purpose, code)).fetchone()
    if not r:
        return False
    created = datetime.strptime(str(r["created"])[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created > timedelta(seconds=CODE_TTL):
        return False
    db().execute("UPDATE email_codes SET used=1 WHERE id=?", (r["id"],))
    return True

def deliver_code(email, purpose, code):
    """Gửi mã qua email; chưa cấu hình SMTP (lúc phát triển) thì trả mã về cho giao diện hiện để thử được."""
    import emails
    subject, body, html = emails.code_mail(purpose, code)
    try:
        sent = send_mail(email, subject, body, html)
    except Exception as e:
        print("[mail] lỗi gửi:", repr(e), flush=True)
        return err("Không gửi được email, hãy thử lại sau hoặc báo quản trị viên", 503)
    return jsonify(ok=True, sent=sent, **({} if sent else {"debug_code": code, "note": "Chưa cấu hình SMTP nên mã hiện tại đây để thử."}))

# ---------- Tài khoản ----------
def check_login():
    """Kiểm tra tài khoản/mật khẩu trong body; trả về (bản ghi người dùng, None) hoặc (None, response lỗi).
    Chống dò mật khẩu: tối đa 10 lần sai trong 15 phút cho mỗi (địa chỉ IP, tài khoản)."""
    j = request.get_json(silent=True) or {}
    ident, p = (j.get("username") or "").strip(), j.get("password") or ""
    key = ("login", client_ip(), ident.lower())
    if not rate_limit(key, 10, 15 * 60):
        return None, err("Đăng nhập sai quá nhiều lần, hãy đợi 15 phút", 429)
    r = db().execute("SELECT * FROM users WHERE username=? OR email=? OR phone=?", (ident, ident.lower(), norm_phone(ident))).fetchone()
    if not r or not check_password_hash(r["pw"], p):
        return None, err("Sai tên đăng nhập hoặc mật khẩu", 401)
    _hits.pop(key, None)  # đúng mật khẩu: xóa đếm
    if r["locked"]:
        return None, err(LOCKED, 403)
    if not r["verified"]:
        return None, (jsonify(error="Email chưa được xác thực, hãy nhập mã đã gửi tới email của bạn", field="unverified", email=r["email"]), 403)
    return r, None

# ---------- Dữ liệu AI ----------
def drop_samples(rows):
    """Gỡ mẫu khỏi dataset_ai và bộ nhớ (nhãn sai); lớp AI không còn mẫu nào thì quên luôn."""
    for s in rows:
        try:
            os.remove(os.path.join(current_app.config["AI_DATASET_DIR"], s["path"]))
        except OSError:
            pass
        db().execute("DELETE FROM ai_samples WHERE id=?", (s["id"],))
        db().execute("UPDATE ai_classes SET samples=samples-1 WHERE class_name=?", (s["class_name"],))
    db().execute("DELETE FROM ai_classes WHERE samples<=0")

# ---------- Bài viết (bảng tin và trang duyệt bài) ----------
def post_rows(where, params=()):
    """Bài viết kèm người đăng, số lượt thích/bình luận/chia sẻ và người đang xem đã thích chưa."""
    return db().execute(
        "SELECT p.*, u.username, (SELECT COUNT(*) FROM post_likes l WHERE l.post_id=p.id) likes, "
        "(SELECT COUNT(*) FROM post_likes l WHERE l.post_id=p.id AND l.user_id=?) liked, "
        "(SELECT COUNT(*) FROM comments c WHERE c.post_id=p.id) comments, "
        "(SELECT COUNT(*) FROM post_shares s WHERE s.post_id=p.id) shares "
        "FROM posts p JOIN users u ON u.id=p.user_id " + where, (session["uid"], *params)).fetchall()

def diag_card(did):
    """Thẻ kết quả tra cứu được chia sẻ trong bài viết."""
    r = db().execute("SELECT id, plant_id, plant, disease, confidence, healthy, source, image FROM diagnoses WHERE id=?", (did,)).fetchone() if did else None
    return dict(r, image_url=image_url(r["image"])) if r else None

def post_out(r, embed=True):
    mine = r["user_id"] == session["uid"]
    d = dict(id=r["id"], content=r["content"], image_url=image_url(r["image"]), status=r["status"], created=r["created"],
             username=r["username"], is_mine=mine, likes=r["likes"], liked=bool(r["liked"]), comments=r["comments"],
             shares=r["shares"], diagnosis=diag_card(r["diagnosis_id"]), shared=None)
    if r["shared_post_id"] and embed:  # bài chia sẻ lại: kèm bài gốc (nếu còn và đã duyệt)
        o = post_rows("WHERE p.id=? AND p.status='approved'", (r["shared_post_id"],))
        d["shared"] = post_out(o[0], embed=False) if o else {"deleted": True}
    if mine or is_admin():
        d.update(feedback=r["feedback"])
    if is_admin():
        d.update(ai_decision=r["ai_decision"], ai_reason=r["ai_reason"])
    return d
