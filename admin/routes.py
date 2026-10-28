"""Trang quản trị riêng (/admin) và API /api/admin/*: duyệt bài, người dùng, bình luận, đánh giá, dữ liệu AI, khóa Gemini.
Mọi API (trừ đăng nhập) yêu cầu tài khoản quản trị viên. Giao diện React ở frontend/src/admin, build ra frontend/dist/admin.html."""
import csv, json, os, re, secrets, time
from datetime import datetime, timedelta, timezone
from flask import Blueprint, current_app, jsonify, request, send_from_directory, session
from werkzeug.security import generate_password_hash
import ai_service
from core import (KeyStore, admin_required, check_login, db, drop_samples, err, image_url, is_pg, notify, post_out, post_rows,
                  remove_upload, spa_page)

bp = Blueprint("admin", __name__)

@bp.get("/admin", strict_slashes=False)  # trang quản trị riêng (điều hướng bằng hash); mọi API /api/admin vẫn tự kiểm tra quyền
def admin_page():
    return spa_page("admin.html")

@bp.post("/api/admin/login")
def admin_login():
    """Đăng nhập từ trang quản trị: tài khoản thường bị từ chối và phiên đang có giữ nguyên."""
    r, bad = check_login()
    if bad:
        return bad
    if r["role"] != "admin":
        return err("Tài khoản này không có quyền quản trị", 403)
    session.clear(); session["uid"] = r["id"]
    return jsonify(ok=True, username=r["username"])

# ---------- Quản trị ----------
def search_args():
    q = (request.args.get("q") or "").strip()[:100]
    return q, f"%{q}%"

@bp.get("/api/admin/posts")
@admin_required
def admin_posts():
    status, (q, like) = request.args.get("status", "pending"), search_args()
    if status not in ("pending", "approved", "rejected", "all"):
        return err("Trạng thái không hợp lệ")
    where, params = ["(? = '' OR p.content LIKE ? OR u.username LIKE ?)"], [q, like, like]
    if status != "all":
        where.append("p.status=?"); params.append(status)
    return jsonify([post_out(r) for r in post_rows("WHERE " + " AND ".join(where) + " ORDER BY p.id DESC LIMIT 200", tuple(params))])

@bp.post("/api/admin/posts/<int:pid>")
@admin_required
def admin_review(pid):
    j = request.get_json(silent=True) or {}
    action, note = j.get("action"), (j.get("note") or "").strip()[:500]
    if action not in ("approve", "reject"):
        return err("Hành động không hợp lệ")
    p = db().execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
    if not p:
        return err("Không tìm thấy bài viết", 404)
    if action == "approve":
        db().execute("UPDATE posts SET status='approved', feedback=NULL, reviewed_by=?, reviewed=CURRENT_TIMESTAMP WHERE id=?", (session["uid"], pid))
        notify(p["user_id"], "Bài viết của bạn đã được quản trị viên duyệt và đăng lên trang chủ.", "#/home/mine")
    else:
        note = note or "Nội dung chưa phù hợp với tiêu chuẩn cộng đồng."
        db().execute("UPDATE posts SET status='rejected', feedback=?, reviewed_by=?, reviewed=CURRENT_TIMESTAMP WHERE id=?", (note, session["uid"], pid))
        notify(p["user_id"], f"Bài viết của bạn bị quản trị viên từ chối: {note}", "#/home/mine")
    db().commit()
    return jsonify(ok=True)

@bp.get("/api/admin/stats")
@admin_required
def admin_stats():
    one = lambda q, *a: db().execute(q, a).fetchone()[0]
    # Lượt tra cứu 14 ngày gần nhất theo giờ Việt Nam (CSDL lưu giờ UTC); hàm ngày tháng khác nhau giữa PostgreSQL và SQLite
    since = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
    day = "to_char(created + interval '7 hours', 'YYYY-MM-DD')" if is_pg(current_app.config["DATABASE"]) else "date(created, '+7 hours')"
    per_day = {r[0]: r[1] for r in db().execute(f"SELECT {day} d, COUNT(*) FROM diagnoses WHERE created >= ? GROUP BY d", (since,))}
    today = time.time() + 7 * 3600
    days = [time.strftime("%Y-%m-%d", time.gmtime(today - i * 86400)) for i in range(13, -1, -1)]
    keys = db().execute("SELECT enabled, cooldowns FROM ai_keys").fetchall()
    cooling = sum(1 for k in keys if k["enabled"] and any(t > time.time() for t in json.loads(k["cooldowns"] or "{}").values()))
    return jsonify(
        users=one("SELECT COUNT(*) FROM users"), locked=one("SELECT COUNT(*) FROM users WHERE locked=1"),
        diagnoses=one("SELECT COUNT(*) FROM diagnoses"), today=per_day.get(days[-1], 0),
        posts={r[0]: r[1] for r in db().execute("SELECT status, COUNT(*) FROM posts GROUP BY status")},
        pending=one("SELECT COUNT(*) FROM posts WHERE status='pending'"),
        comments=one("SELECT COUNT(*) FROM comments"), flagged=one("SELECT COUNT(*) FROM comments WHERE ai_decision IS DISTINCT FROM 'approve'"),
        ratings=one("SELECT COUNT(*) FROM ratings"), rating_avg=round(one("SELECT COALESCE(AVG(stars), 0) FROM ratings"), 2),
        samples=one("SELECT COUNT(*) FROM ai_samples"),
        keys=dict(total=len(keys), enabled=sum(1 for k in keys if k["enabled"]), cooling=cooling),
        daily=[dict(day=d, n=per_day.get(d, 0)) for d in days],
        top=[dict(r) for r in db().execute("SELECT plant, disease, COUNT(*) n FROM diagnoses WHERE healthy=0 AND plant_id NOT IN "
                                           "('unknown', 'background') GROUP BY plant, disease ORDER BY n DESC LIMIT 6")],
        classes=[dict(r) for r in db().execute("SELECT class_name, COUNT(*) n FROM ai_samples GROUP BY class_name ORDER BY n DESC")])

@bp.get("/api/admin/analytics")
@admin_required
def admin_analytics():
    """Thống kê sâu: tra cứu theo tháng (12 tháng, chia mô hình/AI/sâu hại), bệnh theo tháng, độ chính xác suy từ sao, lượt AI 30 ngày."""
    pg = is_pg(current_app.config["DATABASE"])
    month = "to_char(created + interval '7 hours', 'YYYY-MM')" if pg else "strftime('%Y-%m', created, '+7 hours')"
    day = "to_char(created + interval '7 hours', 'YYYY-MM-DD')" if pg else "date(created, '+7 hours')"
    now = datetime.now(timezone.utc) + timedelta(hours=7)
    months = []
    y, m = now.year, now.month
    for _ in range(12):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    months.reverse()
    since = (now - timedelta(days=366)).strftime("%Y-%m-%d")
    kind = "CASE WHEN plant_id='pest' THEN 'pest' WHEN source='ai' THEN 'ai' WHEN source='memory' THEN 'memory' ELSE 'model' END"
    by_month = {}
    for r in db().execute(f"SELECT {month} m, {kind} k, COUNT(*) n FROM diagnoses WHERE created >= ? GROUP BY m, k", (since,)):
        by_month.setdefault(r[0], {})[r[1]] = r[2]
    monthly = [dict(month=mo, **{k: by_month.get(mo, {}).get(k, 0) for k in ("model", "ai", "memory", "pest")}) for mo in months]
    diseases = {}
    for r in db().execute(f"SELECT {month} m, plant, disease, COUNT(*) n FROM diagnoses WHERE created >= ? AND healthy=0 AND plant_id NOT IN "
                          "('unknown', 'background') GROUP BY m, plant, disease", (since,)):
        diseases.setdefault(f"{r[1]}: {r[2]}", {})[r[0]] = r[3]
    top = sorted(diseases.items(), key=lambda kv: -sum(kv[1].values()))[:8]
    disease_rows = [dict(name=name, total=sum(v.values()), months=[v.get(mo, 0) for mo in months]) for name, v in top]
    # Độ chính xác suy từ đánh giá: 4-5 sao coi là đúng, 1-2 sao sai, 3 sao không tính
    acc = []
    for r in db().execute("SELECT d.source, d.plant_id='pest' pest, COUNT(*) n, AVG(r.stars) avg, "
                          "SUM(CASE WHEN r.stars >= 4 THEN 1 ELSE 0 END) good, SUM(CASE WHEN r.stars <= 2 THEN 1 ELSE 0 END) bad "
                          "FROM ratings r JOIN diagnoses d ON d.id=r.diagnosis_id GROUP BY d.source, d.plant_id='pest'"):
        name = {"ai": "AI Gemini", "memory": "Bộ nhớ ảnh AI", "model": "Mô hình sâu hại" if r["pest"] else "Mô hình bệnh lá"}[r["source"]]
        judged = (r["good"] or 0) + (r["bad"] or 0)
        acc.append(dict(name=name, n=r["n"], avg=round(float(r["avg"] or 0), 2), good=r["good"] or 0, bad=r["bad"] or 0,
                        accuracy=round((r["good"] or 0) / judged, 3) if judged else None))
    since30 = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    ai_daily = {}
    for r in db().execute(f"SELECT {day} d, 'vision' k, COUNT(*) FROM diagnoses WHERE created >= ? AND source='ai' GROUP BY d "
                          f"UNION ALL SELECT {day} d, 'chat' k, COUNT(*) FROM chats WHERE created >= ? AND role='user' GROUP BY d", (since30, since30)):
        ai_daily.setdefault(r[0], {})[r[1]] = r[2]
    today = time.time() + 7 * 3600
    days = [time.strftime("%Y-%m-%d", time.gmtime(today - i * 86400)) for i in range(29, -1, -1)]
    ai_usage = [dict(day=d, vision=ai_daily.get(d, {}).get("vision", 0), chat=ai_daily.get(d, {}).get("chat", 0)) for d in days]
    top_users = [dict(r) for r in db().execute("SELECT u.username, COUNT(*) n FROM diagnoses d JOIN users u ON u.id=d.user_id "
                                               "WHERE d.created >= ? GROUP BY u.username ORDER BY n DESC LIMIT 5", (since30,))]
    keys_ok = db().execute("SELECT COALESCE(SUM(ok_count), 0), COALESCE(SUM(fail_count), 0) FROM ai_keys").fetchone()
    return jsonify(months=months, monthly=monthly, diseases=disease_rows, accuracy=acc, ai_usage=ai_usage, top_users=top_users,
                   keys=dict(ok=int(keys_ok[0]), fail=int(keys_ok[1])))

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
RESULT_FILES = {"confusion_matrix.png", "class_metrics.png", "training_accuracy.png", "training_loss.png",
                "gradcam_examples.png", "gradcam_errors.png"}  # 2 hình cuối do gradcam_examples.py vẽ
RESULT_ORDER = ["confusion_matrix.png", "class_metrics.png", "gradcam_examples.png", "gradcam_errors.png", "training_accuracy.png", "training_loss.png"]

@bp.get("/api/admin/models")
@admin_required
def admin_models():
    """Kết quả đánh giá hai mô hình (do train.py / train_pests.py ghi ra results/) để hiện ma trận nhầm lẫn, F1 từng lớp."""
    def read_csv(name):
        p = os.path.join(RESULTS_DIR, name)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    leaf = None
    overall = read_csv("overall_metrics.csv")
    if overall:
        report = read_csv("classification_report.csv") or []
        per_class = [dict(name=r.get("") or r.get("class", ""), precision=float(r["precision"]), recall=float(r["recall"]), f1=float(r["f1-score"]),
                          support=int(float(r["support"]))) for r in report if (r.get("") or "") not in ("accuracy", "macro avg", "weighted avg")]
        leaf = dict(overall={k: float(v) for k, v in overall[0].items() if v not in ("", None)}, per_class=per_class,
                    images=[f for f in sorted(RESULT_FILES, key=RESULT_ORDER.index) if os.path.exists(os.path.join(RESULTS_DIR, f))],
                    trained=time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(os.path.join(RESULTS_DIR, "overall_metrics.csv")))))
        ev = os.path.join(RESULTS_DIR, "leaf_eval.json")  # số liệu do evaluate_leaf.py đánh giá lại (không phải lúc huấn luyện)
        if os.path.exists(ev) and os.path.getmtime(ev) >= os.path.getmtime(os.path.join(RESULTS_DIR, "overall_metrics.csv")) - 60:
            with open(ev, encoding="utf-8") as f:
                leaf["reevaluated"] = json.load(f)
    pest = None
    p = os.path.join(RESULTS_DIR, "pest_metrics.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            m = json.load(f)
        import pests as pk
        name = lambda c: f"{pk.info(c)['name']} ({c})"
        pest = dict(classes=m["classes"], images=m["images"], accuracy=m["accuracy"], top5=m["top5"], macro_f1=m["macro_f1"], finetune=m.get("finetune_epochs", 0),
                    worst=[dict(w, label=name(w["name"])) for w in m["worst"]], confused=[dict(c, true_label=name(c["true"]), pred_label=name(c["pred"])) for c in m["confused"]],
                    per_class=[dict(x, label=pk.info(x["name"])["name"]) for x in m["per_class"]],
                    trained=time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(p))))
    compare = None  # so sánh kiến trúc do compare_models.py (notebooks/so_sanh_kien_truc.ipynb) ghi ra results/compare/
    rows = read_csv(os.path.join("compare", "summary.csv"))
    if rows:
        num = lambda v: float(v) if v not in ("", None) else None
        compare = dict(rows=[dict(r, accuracy=num(r["accuracy"]), top3=num(r.get("top3")), macro_f1=num(r["macro_f1"]), weighted_f1=num(r.get("weighted_f1")),
                                  params_m=num(r["params_m"]), size_mb=num(r["size_mb"]), cpu_ms=num(r["cpu_ms"]), batch_ms=num(r.get("batch_ms")),
                                  train_min=num(r["train_min"]), epochs=int(float(r["epochs"])), best_val_acc=num(r.get("best_val_acc")),
                                  test_images=int(float(r["test_images"])), classes=int(float(r["classes"])),
                                  image=os.path.exists(os.path.join(RESULTS_DIR, "compare", r["arch"], "confusion_matrix.png"))) for r in rows],
                       chart=os.path.exists(os.path.join(RESULTS_DIR, "compare", "summary.png")),
                       trained=time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(os.path.join(RESULTS_DIR, "compare", "summary.csv")))))
    return jsonify(leaf=leaf, pest=pest, compare=compare, model_loaded=not current_app.model.demo, pest_loaded=current_app.pests.available,
                   class_count=len(current_app.model.class_names), pest_class_count=len(current_app.pests.class_names))

@bp.get("/api/admin/results/<path:name>")
@admin_required
def admin_result_file(name):
    """Ảnh kết quả: results/<tên>.png hoặc results/compare/<kiến trúc>/confusion_matrix.png, results/compare/summary.png."""
    ok = name in RESULT_FILES or re.fullmatch(r"compare/(summary|[a-z0-9]+/confusion_matrix)\.png", name)
    if not ok:
        return err("Không có file này", 404)
    return send_from_directory(RESULTS_DIR, name)

@bp.post("/api/admin/broadcast")
@admin_required
def admin_broadcast():
    content = ((request.get_json(silent=True) or {}).get("content") or "").strip()
    if not content or len(content) > 300:
        return err("Nội dung thông báo từ 1 đến 300 ký tự", field="content")
    ids = [r[0] for r in db().execute("SELECT id FROM users WHERE locked=0")]
    for uid in ids:
        notify(uid, f"Thông báo từ quản trị viên: {content}", "#/home")
    db().commit()
    return jsonify(ok=True, sent=len(ids))

# Người dùng
@bp.get("/api/admin/users")
@admin_required
def admin_users():
    q, like = search_args()
    rows = db().execute(
        "SELECT u.id, u.username, u.email, u.phone, u.role, u.locked, u.created, "
        "(SELECT COUNT(*) FROM diagnoses d WHERE d.user_id=u.id) scans, (SELECT COUNT(*) FROM posts p WHERE p.user_id=u.id) posts, "
        "(SELECT COUNT(*) FROM comments c WHERE c.user_id=u.id) comments, (SELECT COUNT(*) FROM ratings r WHERE r.user_id=u.id) ratings "
        "FROM users u WHERE ? = '' OR u.username LIKE ? OR u.email LIKE ? OR u.phone LIKE ? ORDER BY u.id DESC LIMIT 300",
        (q, like, like, like)).fetchall()
    return jsonify([dict(r, is_me=r["id"] == session["uid"]) for r in rows])

@bp.post("/api/admin/users/<int:uid>")
@admin_required
def admin_user_action(uid):
    action = (request.get_json(silent=True) or {}).get("action")
    u = db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        return err("Không tìm thấy người dùng", 404)
    if uid == session["uid"] and action in ("lock", "make_user"):
        return err("Không thể tự khóa hoặc tự bỏ quyền quản trị của chính mình")
    updates = {"lock": ("locked", 1), "unlock": ("locked", 0), "make_admin": ("role", "admin"), "make_user": ("role", "user")}
    if action in updates:
        col, val = updates[action]
        db().execute(f"UPDATE users SET {col}=? WHERE id=?", (val, uid))
        if action == "make_admin":
            notify(uid, "Bạn đã được cấp quyền quản trị viên.", "/admin")
        db().commit()
        return jsonify(ok=True)
    if action == "reset_password":  # mật khẩu tạm, chỉ hiện một lần cho quản trị viên để báo lại người dùng
        pw = "".join(secrets.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(10))
        db().execute("UPDATE users SET pw=? WHERE id=?", (generate_password_hash(pw), uid))
        db().commit()
        return jsonify(ok=True, password=pw)
    return err("Hành động không hợp lệ")

@bp.delete("/api/admin/users/<int:uid>")
@admin_required
def admin_delete_user(uid):
    """Xóa tài khoản cùng bài viết, bình luận, tra cứu, đánh giá của người đó (ảnh trong dataset_ai vẫn giữ để huấn luyện)."""
    if uid == session["uid"]:
        return err("Không thể tự xóa tài khoản của chính mình")
    if not db().execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
        return err("Không tìm thấy người dùng", 404)
    files = [r[0] for r in db().execute("SELECT image FROM posts WHERE user_id=? UNION ALL SELECT image FROM diagnoses WHERE user_id=?", (uid, uid))]
    for t in ("post_likes", "comments", "post_shares"):
        db().execute(f"DELETE FROM {t} WHERE post_id IN (SELECT id FROM posts WHERE user_id=?) OR user_id=?", (uid, uid))
    for t in ("posts", "chats", "ratings", "diagnoses", "notifications"):
        db().execute(f"DELETE FROM {t} WHERE user_id=?", (uid,))
    db().execute("UPDATE ai_samples SET user_id=NULL WHERE user_id=?", (uid,))
    db().execute("DELETE FROM users WHERE id=?", (uid,))
    db().commit()
    for f in files:
        remove_upload(f)
    return jsonify(ok=True)

# Bình luận
@bp.get("/api/admin/comments")
@admin_required
def admin_comments():
    q, like = search_args()
    flagged = request.args.get("flagged") == "1"  # AI chưa duyệt được (review/lỗi) -> cần người xem
    rows = db().execute(
        "SELECT c.id, c.content, c.created, c.ai_decision, c.post_id, u.username, substr(p.content, 1, 90) post_excerpt "
        "FROM comments c JOIN users u ON u.id=c.user_id JOIN posts p ON p.id=c.post_id "
        "WHERE (? = '' OR c.content LIKE ? OR u.username LIKE ?) AND (? = 0 OR c.ai_decision IS DISTINCT FROM 'approve') ORDER BY c.id DESC LIMIT 300",
        (q, like, like, int(flagged))).fetchall()
    return jsonify([dict(r) for r in rows])

# Đánh giá
@bp.get("/api/admin/ratings")
@admin_required
def admin_ratings():
    stars = request.args.get("stars", type=int)
    rows = db().execute(
        "SELECT r.id, r.stars, r.comment, r.created, u.username, d.plant, d.disease, d.image, d.source FROM ratings r "
        "JOIN users u ON u.id=r.user_id LEFT JOIN diagnoses d ON d.id=r.diagnosis_id WHERE ? IS NULL OR r.stars=? ORDER BY r.id DESC LIMIT 300",
        (stars, stars)).fetchall()
    return jsonify([dict(r, image_url=image_url(r["image"])) for r in rows])

@bp.delete("/api/admin/ratings/<int:rid>")
@admin_required
def admin_delete_rating(rid):
    if not db().execute("DELETE FROM ratings WHERE id=?", (rid,)).rowcount:
        return err("Không tìm thấy đánh giá", 404)
    db().commit()
    return jsonify(ok=True)

# Khóa Gemini và cài đặt AI
MODEL_RE = r"[a-z0-9][a-z0-9.\-]{1,60}"

def mask(k):
    return f"{k[:4]}…{k[-4:]}" if k and len(k) > 12 else "••••"

def model_chain(fast):
    return current_app.keys.models(fast) or ((os.getenv("GEMINI_FAST_MODEL") or ai_service.FAST_MODELS) if fast
                                     else (os.getenv("GEMINI_MODEL") or ai_service.DEFAULT_MODELS))

@bp.get("/api/admin/keys")
@admin_required
def admin_keys():
    now, out = time.time(), []
    for r in db().execute("SELECT * FROM ai_keys ORDER BY id"):
        key = current_app.keys.decrypt(r["key_enc"])
        out.append(dict(id=r["id"], label=r["label"], masked=mask(key) if key else None, enabled=bool(r["enabled"]),
                        ok_count=r["ok_count"], fail_count=r["fail_count"], last_used=r["last_used"], last_error=r["last_error"],
                        last_error_at=r["last_error_at"], created=r["created"],
                        cooling={m: t for m, t in json.loads(r["cooldowns"] or "{}").items() if t > now}))
    return jsonify(keys=out, models=model_chain(False), fast_models=model_chain(True),
                   default_models=ai_service.DEFAULT_MODELS, default_fast_models=ai_service.FAST_MODELS)

@bp.post("/api/admin/keys")
@admin_required
def admin_add_key():
    j = request.get_json(silent=True) or {}
    key, label = (j.get("key") or "").strip(), (j.get("label") or "").strip()[:60]
    if len(key) < 20 or re.search(r"\s", key):
        return err("Khóa không đúng định dạng (dán nguyên chuỗi khóa lấy ở aistudio.google.com/apikey)", field="key")
    if db().execute("SELECT 1 FROM ai_keys WHERE key_hash=?", (KeyStore.fingerprint(key),)).fetchone():
        return err("Khóa này đã có trong danh sách", 409, "key")
    ok, why = ai_service.test_key(key, model_chain(True).split(",")[0].strip())
    if not ok and "không hợp lệ" in why:
        return err(f"Không thêm được: {why}", field="key")
    n = db().execute("SELECT COUNT(*) FROM ai_keys").fetchone()[0]
    kid = current_app.keys.add(label or f"Khóa {n + 1}", key)
    return jsonify(ok=True, id=kid, tested=ok, message="Đã thêm và kiểm tra khóa" if ok else f"Đã thêm khóa. Lưu ý: {why}"), 201

@bp.patch("/api/admin/keys/<int:kid>")
@admin_required
def admin_update_key(kid):
    j = request.get_json(silent=True) or {}
    if not db().execute("SELECT 1 FROM ai_keys WHERE id=?", (kid,)).fetchone():
        return err("Không tìm thấy khóa", 404)
    if "label" in j:
        label = (j.get("label") or "").strip()[:60]
        if not label:
            return err("Tên khóa không được trống", field="label")
        db().execute("UPDATE ai_keys SET label=? WHERE id=?", (label, kid))
    if "enabled" in j:
        db().execute("UPDATE ai_keys SET enabled=? WHERE id=?", (int(bool(j["enabled"])), kid))
    if j.get("reset"):  # mở lại ngay khóa đang bị tạm bỏ qua (VD vừa nâng gói)
        db().execute("UPDATE ai_keys SET cooldowns=NULL WHERE id=?", (kid,))
    db().commit()
    return jsonify(ok=True)

@bp.delete("/api/admin/keys/<int:kid>")
@admin_required
def admin_delete_key(kid):
    if not db().execute("DELETE FROM ai_keys WHERE id=?", (kid,)).rowcount:
        return err("Không tìm thấy khóa", 404)
    db().commit()
    return jsonify(ok=True)

@bp.post("/api/admin/keys/<int:kid>/test")
@admin_required
def admin_test_key(kid):
    r = db().execute("SELECT key_enc FROM ai_keys WHERE id=?", (kid,)).fetchone()
    if not r:
        return err("Không tìm thấy khóa", 404)
    key = current_app.keys.decrypt(r["key_enc"])
    if not key:
        return err("Không giải mã được khóa (SECRET_KEY đã đổi), hãy xóa và thêm lại", 400)
    model = model_chain(True).split(",")[0].strip()
    ok, why = ai_service.test_key(key, model)
    if ok:
        db().execute("UPDATE ai_keys SET cooldowns=NULL WHERE id=?", (kid,))
        db().commit()
    return jsonify(ok=ok, model=model, message=f"Khóa hoạt động với {model}" if ok else why)

@bp.put("/api/admin/settings")
@admin_required
def admin_settings():
    j = request.get_json(silent=True) or {}
    for name in ("models", "fast_models"):
        if name not in j:
            continue
        chain = [m.strip() for m in (j.get(name) or "").split(",") if m.strip()]
        if any(not re.fullmatch(MODEL_RE, m) for m in chain):
            return err("Tên model chỉ gồm chữ thường, số, dấu chấm và gạch ngang, cách nhau bởi dấu phẩy", field=name)
        if chain:
            db().execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (name, ",".join(chain)))
        else:  # để trống = dùng mặc định
            db().execute("DELETE FROM settings WHERE key=?", (name,))
    db().commit()
    return jsonify(ok=True, models=model_chain(False), fast_models=model_chain(True))

@bp.get("/api/admin/samples")
@admin_required
def admin_samples():
    rows = db().execute("SELECT s.id, s.class_name, s.confidence, s.created, u.username, d.plant, d.disease, d.image FROM ai_samples s "
                        "LEFT JOIN users u ON u.id=s.user_id LEFT JOIN diagnoses d ON d.id=s.diagnosis_id ORDER BY s.id DESC LIMIT 100").fetchall()
    return jsonify([dict(r, image_url=image_url(r["image"])) for r in rows])

@bp.delete("/api/admin/samples/<int:sid>")
@admin_required
def admin_delete_sample(sid):
    s = db().execute("SELECT * FROM ai_samples WHERE id=?", (sid,)).fetchone()
    if not s:
        return err("Không tìm thấy mẫu dữ liệu", 404)
    drop_samples([s])
    db().commit()
    return jsonify(ok=True)
