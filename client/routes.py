"""Giao diện người dùng: trang chính (/) và API cho người dùng: tài khoản, tra cứu bệnh (mô hình + AI), lịch sử, chat AI,
đánh giá, bài đăng cộng đồng có AI kiểm duyệt, thông báo. Giao diện React ở frontend/src/client, build ra frontend/dist (index.html)."""
import hashlib, json, os, re, secrets, unicodedata, uuid
from datetime import datetime, timedelta, timezone
import numpy as np
from flask import Blueprint, abort, current_app, jsonify, request, send_from_directory, session
from werkzeug.security import generate_password_hash, check_password_hash
import knowledge, ai_service, care, google_login, pests, push, shopping, weather
from model_service import lesion_overlay, pest_entry, severity, severity_level
from core import (LOCKED, TOO_MANY, IntegrityError, check_code, check_login, client_ip, db, deliver_code, deliver_reminders, drop_samples, err,
                  image_url, is_admin, issue_code, login_required, me_row, norm_phone, notify, post_out, post_rows, rate_limit, remove_upload,
                  save_image, spa_page, user_plants, utcnow)

bp = Blueprint("client", __name__, static_folder="static", static_url_path="/client/static")
RESERVED = ("api/", "uploads/", "static/", "assets/", "admin", "client/", "favicon.ico")

LOW_CONF = 0.60
AI_SAMPLE_MIN_CONF = 0.60  # chỉ lưu ảnh vào dataset khi AI đủ chắc chắn, tránh dán nhãn sai
# Độ giống (cosine) vector đặc trưng MobileNetV3 với ảnh AI đã xác định. Đo lại với mô hình bản 2 (train.py v2, 28/10/2026) trên
# ảnh test PlantVillage: cùng ảnh bị cắt/xoay/đổi sáng/lật trung vị 0.97, 95% >= 0.88; hai ảnh khác lớp giống nhất cao nhất 0.80
# (99% dưới 0.74) -> 0.88 coi là cùng chiếc lá, 0.80 chỉ để gợi ý. (Mô hình bản 1: 0.92 / 0.85.)
MEMORY_MATCH = 0.88
MEMORY_HINT = 0.80
# Độ giống cao nhất với tâm các lớp đã học (models/class_centroids.npz). Mô hình bản 2: ảnh lá test PlantVillage trung vị 0.91,
# 99% >= 0.66; ảnh cây chưa có trong mô hình (lúa, sầu riêng, đậu phộng... AI đã học) trung vị 0.39, cao nhất 0.68;
# côn trùng INSECT204 trung vị 0.39 -> dưới 0.65 coi là cây lạ, nhờ AI. (Mô hình bản 1 dùng 0.70.)
FAMILIAR_MIN = 0.65
# Mô hình sâu hại YOLO11m-cls (tâm 204 loài INSECT204), đo 29/10/2026 bằng yolo/export_pest.py và trên 3.000 ảnh test sâu hại,
# 1.500 ảnh lá PlantVillage, 30 ảnh lá thật người dùng gửi (dataset_ai). YOLO tự tin hơn MobileNetV3 cũ, kể cả với ảnh lá, nên
# chế độ Tự nhận diện dùng ngưỡng riêng, chặt hơn (không chuyển thì app vẫn nhờ AI phân tích, chuyển nhầm lá thành sâu thì tệ hơn).
# Người dùng chọn "Sâu hại": ảnh có độ giống tâm loài gần nhất < 0.50 coi là không có côn trùng / loài chưa học (94% ảnh sâu hại test
# qua ngưỡng); kết luận khi độ tin cậy >= 0.70 (31.312 ảnh test: kết luận được 79% số ảnh, đúng 88%; MobileNetV3 cũ ở ngưỡng 0.4:
# 66% số ảnh, đúng 87%).
PEST_FAMILIAR_MIN = 0.50
PEST_MIN_PROB = 0.70
# Tự nhận diện (mô hình bệnh lá thấy ảnh lạ): chỉ chuyển sang sâu hại khi độ giống >= 0.60 và độ tin cậy >= 0.90: 56% ảnh sâu hại
# được chuyển, đúng loài 94%; ảnh lá thật 0/30, ảnh lá PlantVillage 4% (ảnh lá quen thì mô hình bệnh lá đã xử lý, không tới bước này).
PEST_AUTO_FAMILIAR = 0.60
PEST_AUTO_MIN_PROB = 0.90
USER_RE = r"[A-Za-z0-9_.]{3,30}"
EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
PHONE_RE = r"0[35789]\d{8}"  # di động Việt Nam: 10 số, đầu 03/05/07/08/09

def slug(s):
    """'leaf spot' -> 'Leaf_spot': tên thư mục lớp theo kiểu PlantVillage."""
    s = "_".join(re.findall(r"[A-Za-z0-9]+", s or ""))
    return s[:1].upper() + s[1:]

def words(s):
    """Tập từ để so tên (bỏ dấu tiếng Việt, giữ phần trong ngoặc): 'Bệnh đạo ôn' -> {benh, dao, on}."""
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return set(re.findall(r"[a-z0-9]+", "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()))

def coords(lat, lon):
    """Tọa độ hợp lệ (lat, lon) hoặc (None, None)."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else (None, None)

def taken(col, value, uid=None):
    return db().execute(f"SELECT 1 FROM users WHERE {col}=? AND id IS DISTINCT FROM ?", (value, uid)).fetchone() is not None

def contact_error(email, phone, uid=None):
    """Kiểm tra định dạng và trùng lặp email/SĐT; trả về response lỗi hoặc None."""
    if len(email) > 254 or not re.fullmatch(EMAIL_RE, email):
        return err("Email không hợp lệ (VD: ten@gmail.com)", field="email")
    if not re.fullmatch(PHONE_RE, phone):
        return err("Số điện thoại không hợp lệ: cần 10 số, bắt đầu bằng 03, 05, 07, 08 hoặc 09", field="phone")
    if taken("email", email, uid):
        return err("Email đã được sử dụng", 409, "email")
    if taken("phone", phone, uid):
        return err("Số điện thoại đã được sử dụng", 409, "phone")
    return None

@bp.get("/")
@bp.get("/<path:path>")
def index(path=""):
    """Ứng dụng một trang: mọi đường dẫn (/home, /diagnosis/3, /p/12...) đều trả index.html, React Router hiển thị đúng trang."""
    if path.startswith(RESERVED):
        abort(404)
    return spa_page("index.html")

# ---------- Tài khoản ----------
@bp.post("/api/register")
def register():
    j = request.get_json(silent=True) or {}
    u, e, p = (j.get("username") or "").strip(), (j.get("email") or "").strip().lower(), j.get("password") or ""
    ph = norm_phone(j.get("phone"))
    if not re.fullmatch(USER_RE, u):
        return err("Tên đăng nhập 3-30 ký tự (chữ, số, _ .)", field="username")
    bad = contact_error(e, ph)
    if bad:
        return bad
    if len(p) < 6:
        return err("Mật khẩu tối thiểu 6 ký tự", field="password")
    if taken("username", u):
        return err("Tên đăng nhập đã tồn tại", 409, "username")
    if not rate_limit(("register", client_ip()), 10, 3600):
        return err("Tạo quá nhiều tài khoản từ máy này, hãy thử lại sau 1 giờ", 429)
    try:
        db().execute("INSERT INTO users(username,email,phone,pw,verified) VALUES(?,?,?,?,0)", (u, e, ph, generate_password_hash(p)))
        db().commit()
    except IntegrityError:
        return err("Tên đăng nhập, email hoặc số điện thoại đã tồn tại", 409)
    code, bad = issue_code(e, "verify")
    if bad:
        return bad
    resp = deliver_code(e, "verify", code)
    return (resp if isinstance(resp, tuple) else (resp, 201))

def user_by_email(email):
    return db().execute("SELECT * FROM users WHERE email=?", ((email or "").strip().lower(),)).fetchone()

@bp.post("/api/verify/resend")
def verify_resend():
    """Gửi lại mã xác thực email cho tài khoản chưa xác thực."""
    u = user_by_email((request.get_json(silent=True) or {}).get("email"))
    if not u or u["verified"]:
        return err("Không có tài khoản nào đang chờ xác thực với email này", 404)
    code, bad = issue_code(u["email"], "verify")
    return bad or deliver_code(u["email"], "verify", code)

@bp.post("/api/verify")
def verify():
    """Nhập mã 6 số nhận qua email -> tài khoản được xác thực và đăng nhập luôn."""
    j = request.get_json(silent=True) or {}
    u = user_by_email(j.get("email"))
    if not u:
        return err("Không tìm thấy tài khoản", 404)
    if not u["verified"]:
        if not rate_limit(("verify", u["email"]), 10, 15 * 60):
            return err("Nhập sai mã quá nhiều lần, hãy gửi lại mã mới sau 15 phút", 429)
        if not check_code(u["email"], (j.get("code") or "").strip(), "verify"):
            return err("Mã không đúng hoặc đã hết hạn", field="code")
        db().execute("UPDATE users SET verified=1 WHERE id=?", (u["id"],))
        db().commit()
    session.clear(); session["uid"] = u["id"]
    return jsonify(ok=True, username=u["username"])

@bp.post("/api/password/forgot")
def password_forgot():
    """Quên mật khẩu: gửi mã đặt lại qua email. Email không tồn tại cũng trả ok để không lộ danh sách tài khoản."""
    u = user_by_email((request.get_json(silent=True) or {}).get("email"))
    if not u:
        return jsonify(ok=True, sent=True)
    code, bad = issue_code(u["email"], "reset")
    return bad or deliver_code(u["email"], "reset", code)

@bp.post("/api/password/reset")
def password_reset():
    j = request.get_json(silent=True) or {}
    u, p = user_by_email(j.get("email")), j.get("new_password") or ""
    if len(p) < 6:
        return err("Mật khẩu mới tối thiểu 6 ký tự", field="new_password")
    if not u or not rate_limit(("reset", u["email"]), 10, 15 * 60) or not check_code(u["email"], (j.get("code") or "").strip(), "reset"):
        return err("Mã không đúng hoặc đã hết hạn", field="code")
    db().execute("UPDATE users SET pw=?, verified=1 WHERE id=?", (generate_password_hash(p), u["id"]))
    db().commit()
    session.clear(); session["uid"] = u["id"]
    return jsonify(ok=True, username=u["username"])

@bp.post("/api/login")
def login():
    r, bad = check_login()
    if bad:
        return bad
    session.clear(); session["uid"] = r["id"]
    return jsonify(ok=True, username=r["username"])

@bp.get("/api/auth/config")
def auth_config():
    """Cấu hình đăng nhập cho giao diện: mã ứng dụng Google (không bí mật) nếu đã bật đăng nhập bằng Google."""
    return jsonify(google_client_id=google_login.client_id())

def google_username(email, name):
    """Tên đăng nhập chưa dùng, lấy từ phần trước @ của email (bỏ dấu, ký tự lạ): nguyenvan.a@gmail.com -> nguyenvan.a, trùng thì thêm số."""
    base = re.sub(r"[^A-Za-z0-9_.]", "", unicodedata.normalize("NFD", email.split("@")[0]).replace("đ", "d").replace("Đ", "D"))[:26]
    if len(base) < 3:
        base = re.sub(r"[^A-Za-z0-9_.]", "", unicodedata.normalize("NFD", name.replace(" ", "")))[:26]
    base = base if len(base) >= 3 else "nongdan"
    for i in range(1000):
        cand = base if i == 0 else f"{base[:26]}{i}"
        if not taken("username", cand):
            return cand
    return f"nd{uuid.uuid4().hex[:10]}"

@bp.post("/api/auth/google")
def auth_google():
    """Đăng nhập / đăng ký bằng Google: {credential: ID token từ nút Google}. Tài khoản cùng email đã có thì đăng nhập vào đó (và gắn
    Google); chưa có thì tạo mới, email coi như đã xác thực (Google đã xác minh), chưa có SĐT (bổ sung trong hồ sơ), mật khẩu ngẫu nhiên
    (muốn đăng nhập bằng mật khẩu thì dùng Quên mật khẩu)."""
    if not google_login.client_id():
        return err("Máy chủ chưa bật đăng nhập bằng Google", 503)
    if not rate_limit(("google", client_ip()), 20, 15 * 60):
        return err(TOO_MANY, 429)
    try:
        g = google_login.verify((request.get_json(silent=True) or {}).get("credential"))
    except google_login.GoogleTokenError as e:
        return err(str(e), 401)
    except OSError:
        return err("Không kết nối được tới Google, hãy thử lại sau", 503)
    u = db().execute("SELECT * FROM users WHERE google_sub=?", (g["sub"],)).fetchone() or user_by_email(g["email"])
    created = False
    if u:
        if u["locked"]:
            return err(LOCKED, 403)
        if u["google_sub"] and u["google_sub"] != g["sub"]:
            return err("Email này đã gắn với một tài khoản Google khác", 409)
        db().execute("UPDATE users SET google_sub=?, verified=1 WHERE id=?", (g["sub"], u["id"]))
    else:
        if taken("email", g["email"]):
            return err("Email đã được sử dụng", 409)
        if not rate_limit(("register", client_ip()), 10, 3600):
            return err("Tạo quá nhiều tài khoản từ máy này, hãy thử lại sau 1 giờ", 429)
        uname = google_username(g["email"], g["name"])
        try:
            uid = db().execute("INSERT INTO users(username,email,phone,pw,verified,google_sub) VALUES(?,?,NULL,?,1,?) RETURNING id",
                               (uname, g["email"], generate_password_hash(secrets.token_urlsafe(32)), g["sub"])).fetchone()[0]
        except IntegrityError:
            return err("Tài khoản với email này vừa được tạo, hãy thử đăng nhập lại", 409)
        u, created = db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone(), True
    db().commit()
    session.clear(); session["uid"] = u["id"]
    return jsonify(ok=True, username=u["username"], created=created, need_phone=not u["phone"]), 201 if created else 200

@bp.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)

@bp.get("/api/me")
@login_required
def me():
    r, uid = me_row(), session["uid"]
    deliver_reminders(db(), uid)  # nhắc việc đến hạn -> thông báo (ứng dụng gọi /api/me mỗi khi mở)
    count = lambda q: db().execute(q, (uid,)).fetchone()[0]
    return jsonify(id=r["id"], username=r["username"], email=r["email"], phone=r["phone"], role=r["role"], created=r["created"],
                   location=dict(lat=r["lat"], lon=r["lon"], place=r["place"]) if r["lat"] is not None else None,
                   stats=dict(scans=count("SELECT COUNT(*) FROM diagnoses WHERE user_id=?"),
                              posts=count("SELECT COUNT(*) FROM posts WHERE user_id=? AND status='approved'"),
                              ratings=count("SELECT COUNT(*) FROM ratings WHERE user_id=?"),
                              treatments=count("SELECT COUNT(*) FROM treatments WHERE user_id=? AND status='active'")),
                   due=db().execute("SELECT COUNT(*) FROM reminders WHERE user_id=? AND done=0 AND due<=?", (uid, utcnow())).fetchone()[0],
                   unread=count("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0"))

@bp.put("/api/me/location")
@login_required
def update_location():
    """Lưu vị trí (GPS hoặc chọn địa danh) để nhận cảnh báo thời tiết và ghim ca bệnh lên bản đồ; gửi null để xóa."""
    j = request.get_json(silent=True) or {}
    if j.get("lat") is None:
        db().execute("UPDATE users SET lat=NULL, lon=NULL, place=NULL WHERE id=?", (session["uid"],))
    else:
        lat, lon = coords(j.get("lat"), j.get("lon"))
        if lat is None:
            return err("Tọa độ không hợp lệ")
        db().execute("UPDATE users SET lat=?, lon=?, place=? WHERE id=?", (lat, lon, (j.get("place") or "")[:120] or None, session["uid"]))
    db().commit()
    return jsonify(ok=True)

@bp.put("/api/me")
@login_required
def update_me():
    j = request.get_json(silent=True) or {}
    e, ph = (j.get("email") or "").strip().lower(), norm_phone(j.get("phone"))
    bad = contact_error(e, ph, session["uid"])
    if bad:
        return bad
    db().execute("UPDATE users SET email=?, phone=? WHERE id=?", (e, ph, session["uid"]))
    db().commit()
    return jsonify(ok=True)

@bp.post("/api/me/password")
@login_required
def change_password():
    j = request.get_json(silent=True) or {}
    if not check_password_hash(me_row()["pw"], j.get("old_password") or ""):
        return err("Mật khẩu hiện tại không đúng", field="old_password")
    if len(j.get("new_password") or "") < 6:
        return err("Mật khẩu mới tối thiểu 6 ký tự", field="new_password")
    db().execute("UPDATE users SET pw=? WHERE id=?", (generate_password_hash(j["new_password"]), session["uid"]))
    db().commit()
    return jsonify(ok=True)

# ---------- Tra cứu ----------
AI_DAILY_LIMIT = int(os.getenv("AI_DAILY_LIMIT", "40"))  # lượt gọi AI (phân tích ảnh + chat) mỗi người mỗi ngày; quản trị viên không giới hạn

def ai_quota_ok():
    """Còn lượt AI hôm nay: đếm tin nhắn chat và lượt tra cứu do AI phân tích trong 24 giờ qua."""
    if is_admin():
        return True
    since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    n = db().execute("SELECT (SELECT COUNT(*) FROM chats WHERE user_id=? AND role='user' AND created >= ?) + "
                     "(SELECT COUNT(*) FROM diagnoses WHERE user_id=? AND source='ai' AND created >= ?) + "
                     "(SELECT COUNT(*) FROM lookup_cache WHERE user_id=? AND created >= ?)",  # tìm thuốc, tìm cửa hàng bằng AI
                     (session["uid"], since, session["uid"], since, session["uid"], since)).fetchone()[0]
    return n < AI_DAILY_LIMIT

VAGUE_WORDS = {"unknown", "unidentified", "unidentifiable", "identifiable", "identified", "not", "clearly", "clear", "unclear", "from",
                "image", "plant", "plants", "type", "species", "undetermined", "uncertain", "n", "a", "na", "none", "leaf",
                "khong", "xac", "dinh", "ro", "loai", "cay", "tu", "anh", "chua", "la"}

def vague_plant(name):
    """Tên cây không mang thông tin ("Unknown", "Plant type not clearly identifiable from image", "Không xác định rõ loại cây")."""
    return words(name) <= VAGUE_WORDS

def vague_class(cls):
    return vague_plant(cls.partition("___")[0].replace("_", " "))

def learned_plants():
    """Cây mới do AI học được từ ảnh người dùng (chưa có trong mô hình); bỏ các "cây" AI không xác định được."""
    rows = db().execute("SELECT plant_id, MAX(plant) plant FROM ai_classes GROUP BY plant_id").fetchall()
    return {r["plant_id"]: r["plant"] for r in rows if r["plant_id"] not in knowledge.PLANTS and not vague_plant(r["plant_id"].replace("_", " "))}

@bp.get("/api/plants")
@login_required
def plants():
    pest = [dict(id="pest", name="Sâu hại, côn trùng", note="", source="pest")] if current_app.pests.available else []
    out = [dict(id=k, name=v, note=knowledge.LIMITS[k], source="model") for k, v in knowledge.PLANTS.items()]
    return jsonify(pest + out + [dict(id=k, name=v, note="", source="ai") for k, v in learned_plants().items()])

def model_class(name):
    """Tên lớp của mô hình khớp với name (bỏ qua khác biệt cách viết), hoặc None."""
    if not name:
        return None
    return next((c for c in current_app.model.class_names
                 if knowledge.norm(c) == knowledge.norm(name) and knowledge.info(c)["plant_id"] in knowledge.PLANTS), None)

def known_classes():
    """Các lớp đã biết: của mô hình và do AI học thêm."""
    known = [dict(class_name=c, plant_id=i["plant_id"], plant=i["plant"], disease=i["disease"]) for c in current_app.model.class_names
             for i in [knowledge.info(c)] if i["plant_id"] in knowledge.PLANTS]
    return known + [dict(r) for r in db().execute("SELECT class_name, plant_id, plant, disease FROM ai_classes") if not vague_class(r["class_name"])]

def match_class(a):
    """Ghép kết luận của AI với lớp đã biết: cùng cây (tên Anh hoặc Việt) và tên bệnh gần trùng.
    Trả về (lớp khớp hoặc None, lớp cùng cây đầu tiên hoặc None) để lớp mới dùng chung tên cây/mã cây."""
    plant_en, plant_vi = words(a["plant_en"]), words(a["plant_vi"])
    dis_en = {"healthy"} if a["healthy"] else words(a["disease_en"]) - plant_en - {"disease"}
    dis_vi = {"khoe", "manh"} if a["healthy"] else words(a["disease_vi"]) - plant_vi - {"benh"}
    best, same_plant = (0.0, None), None
    for k in known_classes():
        p, _, d = k["class_name"].partition("___")
        kp_vi = words(k["plant"])
        if not (words(p) & plant_en or (kp_vi and kp_vi == plant_vi)):
            continue
        same_plant = same_plant or k
        theirs = words(d) - words(p) - {"disease"}
        both = dis_en & theirs
        # Tên tiếng Anh trùng quá nửa hoặc tên này nằm trọn trong tên kia ("Blast" ~ "Rice blast", "Gray leaf spot" ~
        # "Cercospora leaf spot Gray leaf spot"); "Southern rust" khác "Common rust", "Early blight" khác "Late blight".
        score = len(both) / len(dis_en | theirs) if both else 0.0
        if score > 0.5 or (both and (dis_en <= theirs or theirs <= dis_en)):
            best = max(best, (score, k["class_name"]))
        elif dis_vi and dis_vi == words(k["disease"]) - kp_vi - {"benh"}:  # tiếng Việt chỉ ghép khi trùng hẳn
            best = max(best, (1.0, k["class_name"]))
    return best[1], same_plant

MAX_PHOTOS = 3  # một lượt tra cứu: 1 ảnh bắt buộc + tối đa 2 ảnh thêm của cùng cây / cùng con sâu
ALL = 10_000   # top_k "lấy hết" để gộp xác suất nhiều ảnh

def fuse(tops):
    """Gộp kết quả nhiều ảnh: trung bình xác suất từng lớp (ảnh không có lớp đó tính 0), xếp giảm dần.
    Lấy trung bình thay vì biểu quyết: một ảnh rất chắc và hai ảnh phân vân vẫn ra kết luận hợp lý, ảnh lẻ đoán sai bị kéo xuống."""
    total, info = {}, {}
    for top in tops:
        for t in top:
            total[t["raw"]] = total.get(t["raw"], 0.0) + t["prob"]
            info.setdefault(t["raw"], t)
    return sorted((dict(info[r], prob=p / len(tops)) for r, p in total.items()), key=lambda t: -t["prob"])

def photo_notes(per, good, label):
    """Ghi chú khi gửi nhiều ảnh: ảnh bị loại vì không dùng được, các ảnh kết luận khác nhau. Trả về (ghi chú, có bất đồng không)."""
    if len(per) < 2:
        return [], False
    notes = [f"Ảnh {i + 1} {label} nên không dùng để kết luận." for i, p in enumerate(per) if p not in good]
    firsts = [p["top"][0] for p in good]
    differ = len({t["raw"] for t in firsts}) > 1
    if differ:
        notes.append("Các ảnh cho kết quả khác nhau (" + "; ".join(f"ảnh {per.index(p) + 1}: {t['disease'].lower()} {t['prob']:.0%}"
                                                                  for p, t in zip(good, firsts)) + "), hệ thống lấy trung bình các ảnh.")
    elif len(good) > 1:
        notes.append(f"{len(good)} ảnh cùng cho một kết quả, kết luận chắc chắn hơn so với một ảnh.")
    return notes, differ

def model_result(datas, plant_id):
    """Kết quả mô hình bệnh lá cho 1-3 ảnh: mỗi ảnh dự đoán riêng; ảnh không phải lá hoặc khác xa dữ liệu đã học bị loại (nếu còn ảnh
    dùng được), xác suất các ảnh còn lại lấy trung bình. Trả về (kết quả, vector đặc trưng ảnh chính, thông tin từng ảnh)."""
    per = []
    for data in datas:
        top, overall, emb = current_app.model.predict(data, None if plant_id == "auto" else plant_id, top_k=ALL)
        fam = current_app.model.familiarity(emb)
        bg = overall["plant_id"] == "background"
        per.append(dict(top=top, overall=overall, emb=emb, fam=fam, bg=bg, strange=fam is not None and fam < FAMILIAR_MIN and not bg))
    good = [p for p in per if not p["bg"] and not p["strange"]] or per
    top = fuse([p["top"] for p in good])[:3]
    plants = [p["overall"]["plant_id"] for p in good]
    overall = next(p["overall"] for p in good if p["overall"]["plant_id"] == max(set(plants), key=plants.count))
    best, notes = top[0], []
    not_leaf = all(p["bg"] for p in good)
    fam = max((p["fam"] for p in good if p["fam"] is not None), default=None)
    strange = not not_leaf and all(p["bg"] or p["strange"] for p in good)
    extra, differ = photo_notes(per, good, "không giống lá bệnh mô hình đã học")
    if not_leaf:
        notes.append("Không nhận ra lá cây trong ảnh, hãy chụp cận cảnh một chiếc lá.")
    elif strange:
        notes.append(f"Ảnh khác xa dữ liệu mô hình đã học (giống nhất {fam:.0%}), có thể là cây chưa có trong dữ liệu.")
    elif plant_id != "auto" and overall["plant_id"] != plant_id:
        notes.append(f"Ảnh giống lá {overall['plant'].lower()} hơn lá {knowledge.PLANTS[plant_id].lower()}, hãy kiểm tra lại loại cây đã chọn.")
    if best["prob"] < LOW_CONF:
        notes.append("Độ tin cậy thấp, hãy chụp lại ảnh rõ hơn (1 lá, đủ sáng, nền đơn giản).")
    if knowledge.LIMITS.get(best["plant_id"]):
        notes.append(knowledge.LIMITS[best["plant_id"]])
    # Mô hình chưa chắc bệnh gì nhưng các khả năng đều cùng một loại cây (và ảnh giống dữ liệu đã học) -> gợi ý loại cây cho AI
    plants = {t["plant_id"] for t in top if t["prob"] >= 0.05}
    plant_guess = knowledge.PLANTS.get(best["plant_id"]) if len(plants) == 1 and not (not_leaf or strange) else None
    # unsure: mô hình không đủ cơ sở để kết luận -> không đưa lớp gần nhất ra như một chẩn đoán.
    # Các ảnh bất đồng: nhờ AI xem lại (uncertain), nhưng vẫn giữ kết quả trung bình nếu đủ tin cậy.
    return dict(result=best, top=top, source="model", notes=extra + notes, uncertain=bool(notes) or differ, plant_guess=plant_guess,
                unsure=not_leaf or strange or best["prob"] < LOW_CONF), good[0]["emb"], per

def pest_result(datas, min_prob=PEST_MIN_PROB, familiar_min=PEST_FAMILIAR_MIN):
    """Kết quả mô hình sâu hại cho 1-3 ảnh (gộp như model_result). Ảnh khác xa các loài đã học hoặc độ tin cậy dưới min_prob ->
    "chưa xác định", các loài gần nhất chỉ để tham khảo."""
    per = []
    for data in datas:
        t, f = current_app.pests.predict(data, top_k=ALL)
        per.append(dict(top=t, fam=f, strange=f is not None and f < familiar_min))
    good = [p for p in per if not p["strange"]] or per
    top = fuse([p["top"] for p in good])[:3]
    fam = max((p["fam"] for p in good if p["fam"] is not None), default=None)
    best, notes = top[0], photo_notes(per, good, "khác xa các loài sâu hại mô hình đã học")[0]
    strange = all(p["strange"] for p in good)
    unsure = strange or best["prob"] < min_prob
    if strange:
        notes.append(f"Ảnh khác xa các loài sâu hại mô hình đã học (giống nhất {fam:.0%}): có thể ảnh không có côn trùng, "
                     "hoặc là loài chưa có trong dữ liệu.")
    if best["prob"] < LOW_CONF:
        notes.append("Độ tin cậy thấp, hãy chụp gần hơn, lấy nét vào con sâu, đủ sáng.")
    if best["beneficial"] and not unsure:
        notes.append("Đây là thiên địch có ích, ăn sâu hại: đừng phun thuốc diệt.")
    pest = dict(group_name=best["group_name"], hosts=best["hosts"], beneficial=best["beneficial"], sci=best["raw"])
    if unsure:
        best = dict(raw="", plant_id="unknown", plant="Sâu hại", disease="Chưa xác định được loài", healthy=False, prob=best["prob"],
                    remedy="Chụp lại gần hơn, lấy nét vào con sâu (hoặc ổ trứng, vết hại), đủ sáng; có thể hỏi trợ lý AI hoặc cán bộ "
                           "khuyến nông. Các loài mô hình đưa ra bên dưới chưa đủ tin cậy để xử lý theo.")
        pest = None
    else:
        best = dict(best, remedy=(f"Cây bị hại: {best['hosts']}. " if not best["beneficial"] else "") + best["remedy"])
    return dict(result=best, top=top, source="model", notes=notes, kind="pest", pest=pest, unsure=unsure, per=per)

def class_info(cls):
    mc = model_class(cls)
    if mc:
        i = knowledge.info(mc)
        return dict(plant_id=i["plant_id"], plant=i["plant"], disease=i["disease"], healthy=i["healthy"], remedy=i["remedy"])
    r = db().execute("SELECT * FROM ai_classes WHERE class_name=?", (cls,)).fetchone()
    if r:
        return dict(plant_id=r["plant_id"], plant=r["plant"], disease=r["disease"], healthy=bool(r["healthy"]), remedy=r["remedy"])
    return dict(plant_id="unknown", plant="Không rõ", disease=cls, healthy=False, remedy="")

def recall(emb):
    """Mẫu AI đã xác định giống ảnh này nhất -> (độ giống, dòng ai_samples) hoặc (0, None)."""
    rows = db().execute("SELECT * FROM ai_samples WHERE embed_key=? AND embedding IS NOT NULL", (current_app.model.embed_key,)).fetchall()
    # bỏ mẫu mà AI không xác định được loại cây (nhãn kiểu "Unknown___..."): dùng lại sẽ ra kết quả "Không xác định"
    rows = [r for r in rows if len(r["embedding"]) == emb.nbytes and not vague_class(r["class_name"])]
    if not rows:
        return 0.0, None
    sims = np.vstack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows]) @ emb
    i = int(np.argmax(sims))
    return float(sims[i]), rows[i]

def memory_result(row):
    """Dùng lại chẩn đoán AI gốc của mẫu đã học (còn lưu thì lấy cả triệu chứng, cách xử lý)."""
    src = db().execute("SELECT * FROM diagnoses WHERE id=?", (row["diagnosis_id"],)).fetchone()
    if src:
        info = dict(plant_id=src["plant_id"], plant=src["plant"], disease=src["disease"], healthy=bool(src["healthy"]), remedy=src["remedy"])
        symptoms = json.loads(src["details"] or "{}").get("symptoms", "")
    else:
        info, symptoms = class_info(row["class_name"]), ""
    return dict(raw=row["class_name"], prob=row["confidence"], symptoms=symptoms, **info)

def unknown_result(prob, plant_id):
    return dict(raw="", plant_id="unknown", plant=knowledge.PLANTS.get(plant_id, "Chưa xác định"), disease="Chưa xác định được bệnh",
                healthy=False, prob=prob,
                remedy="Chụp lại rõ nét một chiếc lá (đủ sáng, nền đơn giản) hoặc bấm Phân tích lại bằng AI sau ít phút. "
                       "Các khả năng mô hình đưa ra bên dưới chưa đủ tin cậy để xử lý theo.")

def ai_raw(a):
    """Tên AI dùng và các bệnh AI đã cân nhắc, lưu lại để quản trị viên rà soát nhãn."""
    return {k: a.get(k) for k in ("plant_en", "disease_en", "differential", "confidence")}

def ai_notes(best, cls, plant_id):
    notes = []
    if best["plant_id"] == "unidentified":
        notes.append("AI chưa xác định được loại cây nên kết quả này không được lưu để hệ thống học. Hãy chọn đúng loại cây khi tra cứu "
                     "hoặc chụp cả chiếc lá (thấy rõ hình dạng, mép lá) để kết quả chính xác hơn.")
    elif cls is None:
        notes.append("AI không nhận ra cây trồng trong ảnh, hãy chụp cận cảnh một chiếc lá.")
    elif plant_id in knowledge.PLANTS and best["plant_id"] != plant_id:
        notes.append(f"AI nhận ra đây là cây {best['plant'].lower()}, không phải {knowledge.PLANTS[plant_id].lower()}.")
    if cls and best["prob"] < LOW_CONF:
        notes.append("AI chưa chắc chắn, hãy chụp lại ảnh rõ hơn hoặc hỏi cán bộ khuyến nông.")
    if cls and best["prob"] >= AI_SAMPLE_MIN_CONF:
        notes.append("Ảnh đã được lưu vào bộ dữ liệu để hệ thống học thêm.")
    return notes

def ai_result(a):
    """Kết quả Gemini -> (kết quả chẩn đoán, tên lớp để lưu dataset hoặc None nếu ảnh không phải cây / AI không xác định được loại cây)."""
    if not a["is_plant"]:
        return dict(raw="", plant_id="background", plant="Không rõ", disease="Không nhận ra cây trồng", healthy=False,
                    remedy="Hãy chụp cận cảnh một chiếc lá, đủ sáng, nền đơn giản.", prob=a["confidence"], symptoms=a["symptoms"]), None
    healthy = a["healthy"]
    if vague_plant(a["plant_en"]) and vague_plant(a["plant_vi"]):
        # AI thấy bệnh nhưng không biết cây gì: vẫn hiện chẩn đoán, nhưng không tạo "cây" mới và không lưu để học (nhãn không dùng được)
        return dict(raw="", plant_id="unidentified", plant="Chưa rõ loại cây", healthy=healthy, prob=a["confidence"], symptoms=a["symptoms"],
                    disease="Khỏe mạnh" if healthy else (a["disease_vi"] or a["disease_en"] or "Chưa rõ bệnh"), remedy=a["remedy"]), None
    cls, same_plant = match_class(a)
    if cls:  # bệnh đã biết: dùng tên thống nhất của lớp đó
        info = class_info(cls)
    else:  # bệnh mới: lớp mới, dùng chung tên cây nếu cây đã có (VD AI gọi "Maize" nhưng hệ thống đã có "Corn")
        plant_part = same_plant["class_name"].partition("___")[0] if same_plant else slug(a["plant_en"]) or "Unknown"
        cls = f"{plant_part}___{'healthy' if healthy else slug(a['disease_en']) or 'Unknown'}"
        info = dict(plant_id=same_plant["plant_id"] if same_plant else slug(a["plant_en"]).lower() or "unknown",
                    plant=same_plant["plant"] if same_plant else a["plant_vi"] or a["plant_en"],
                    disease="Khỏe mạnh" if healthy else (a["disease_vi"] or a["disease_en"]), healthy=healthy)
    return dict(raw=cls, plant_id=info["plant_id"], plant=info["plant"], disease=info["disease"], healthy=info["healthy"],
                remedy=a["remedy"], prob=a["confidence"], symptoms=a["symptoms"]), cls

def save_sample(data, cls, did, best, emb):
    """Lưu ảnh vào dataset_ai/<lớp>/ (cùng cấu trúc PlantVillage) để train.py dùng lần sau,
    kèm vector đặc trưng để nhận lại ảnh giống ngay mà không cần huấn luyện lại."""
    rel = f"{cls}/{uuid.uuid4().hex}.jpg"
    path = os.path.join(current_app.config["AI_DATASET_DIR"], rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    db().execute("INSERT INTO ai_samples(user_id,diagnosis_id,class_name,path,confidence,embedding,embed_key) VALUES(?,?,?,?,?,?,?)",
                 (session["uid"], did, cls, rel, best["prob"], emb.astype(np.float32).tobytes(), current_app.model.embed_key))
    if not model_class(cls):  # lớp mới: ghi nhớ để lần sau hiện trong danh sách cây và dùng đúng tên
        db().execute("INSERT INTO ai_classes(class_name,plant_id,plant,disease,healthy,remedy,samples) VALUES(?,?,?,?,?,?,1) "
                     "ON CONFLICT(class_name) DO UPDATE SET samples=ai_classes.samples+1, remedy=excluded.remedy, updated=CURRENT_TIMESTAMP",
                     (cls, best["plant_id"], best["plant"], best["disease"], int(best["healthy"]), best["remedy"]))

@bp.post("/api/predict")
@login_required
def predict():
    plant_id, files = request.form.get("plant") or "auto", request.files.getlist("image")
    learned = learned_plants()
    if plant_id not in knowledge.PLANTS and plant_id not in learned and plant_id not in ("auto", "other", "pest"):
        return err("Vui lòng chọn cây trồng hợp lệ")
    if not files:
        return err("Chưa có ảnh")
    if len(files) > MAX_PHOTOS:
        return err(f"Mỗi lần tra cứu tối đa {MAX_PHOTOS} ảnh")
    if plant_id == "pest" and not current_app.pests.available:
        return err("Chưa có mô hình nhận diện sâu hại (models/pest_model.onnx), hãy chạy yolo/export_pest.py", 503)
    # Ảnh chính tên ngẫu nhiên; ảnh thêm đặt theo tên ảnh chính (<tên>-p2.jpg, -p3.jpg) để cùng quyền xem, cùng bị xóa
    names, datas = [], []
    for i, f in enumerate(files):
        n, data = save_image(f.read(), "scans", names[0][:-4] + f"-p{i + 1}.jpg" if names else None)
        if not n:
            for x in names:
                remove_upload(x)
            return err("File không phải ảnh hợp lệ" if len(files) == 1 else f"Ảnh {i + 1} không phải ảnh hợp lệ")
        names.append(n); datas.append(data)
    name, data = names[0], datas[0]
    # Thứ tự: mô hình -> ảnh AI đã xác định trước đó (bộ nhớ) -> gọi AI -> báo "chưa xác định" (không đoán bừa)
    res, need_ai, ai_failed, per = None, True, False, None
    if plant_id == "pest":  # sâu hại: chỉ dùng mô hình INSECT204 (AI và bộ nhớ ảnh đang dành cho bệnh lá)
        res, need_ai, emb = pest_result(datas), False, None
        res.pop("unsure")
    elif plant_id in knowledge.PLANTS or plant_id == "auto":
        try:
            res, emb, per = model_result(datas, plant_id)
        except ValueError as e:
            for x in names:
                remove_upload(x)
            return err(str(e))
        need_ai = res.pop("uncertain")
        # Tự nhận diện: ảnh không giống lá bệnh đã học -> thử mô hình sâu hại trước khi nhờ AI
        if plant_id == "auto" and res["unsure"] and current_app.pests.available:
            pres = pest_result(datas, PEST_AUTO_MIN_PROB, PEST_AUTO_FAMILIAR)
            if not pres.pop("unsure"):
                res, need_ai = pres, False
                res["notes"].insert(0, "Ảnh giống côn trùng, sâu hại hơn lá bệnh nên hệ thống dùng mô hình nhận diện sâu hại.")
    else:
        emb = current_app.model.embed(data)
    if res and "per" in res:  # sâu hại: thông tin từng ảnh
        per = res.pop("per")
    sim, row = recall(emb) if need_ai else (0.0, None)
    if sim >= MEMORY_MATCH:
        res = dict(result=memory_result(row), top=res["top"] if res else [], source="memory",
                   notes=[f"Ảnh giống {sim:.0%} với một mẫu trong dữ liệu hệ thống đã học, hệ thống dùng lại kết quả của mẫu đó."])
        need_ai = False
    if need_ai:
        a, why = None, "chưa cấu hình khóa Gemini"
        if not ai_quota_ok():
            why = f"bạn đã dùng hết {AI_DAILY_LIMIT} lượt AI hôm nay"
        elif ai_service.vision_available():
            try:
                guess = (res or {}).get("plant_guess") if plant_id == "auto" else None
                # nhiều ảnh: gửi tất cả trong một lần gọi để AI xem chung (không tốn thêm lượt)
                a = ai_service.analyze_image(datas if len(datas) > 1 else data, knowledge.PLANTS.get(plant_id) or learned.get(plant_id),
                                             **({"model_plant": guess} if guess else {}))
            except Exception as e:
                print("[ai] lỗi phân tích ảnh:", repr(e), flush=True)
                why = ai_service.reason(e)
        hint = ""
        if sim >= MEMORY_HINT:
            info = class_info(row["class_name"])
            hint = f"Ảnh khá giống mẫu đã học: {info['plant']}, {info['disease'][:1].lower() + info['disease'][1:]} (giống {sim:.0%})."
        if a:
            best, cls = ai_result(a)
            notes = (["Mô hình chưa chắc chắn với ảnh này nên AI (Gemini) đã phân tích lại."] if res else []) + ai_notes(best, cls, plant_id)
            res = dict(result=best, top=res["top"] if res else [], source="ai", notes=notes, cls=cls, ai=ai_raw(a))
        elif res is None:
            for x in names:
                remove_upload(x)
            return err(f"Cây này chưa có trong mô hình nên cần AI phân tích, nhưng {why}. " + (hint or "Hãy thử lại sau."), 503)
        elif res.pop("unsure"):
            ai_failed = True
            res = dict(result=unknown_result(res["result"]["prob"], plant_id), top=res["top"], source="model",
                       notes=[f"Mô hình chưa nhận ra ảnh này và chưa gọi được AI: {why}."] + ([hint] if hint else []) + res["notes"])
        else:
            ai_failed = True
            res["notes"].append(f"Chưa gọi được AI để kiểm tra thêm ({why}), kết quả dưới đây là của mô hình.")
    best, cls = res["result"], res.get("cls")
    explain = {}
    # Ảnh nào được dùng để kết luận (ảnh không phải lá / khác xa dữ liệu bị loại, trừ khi ảnh nào cũng vậy)
    used = [not (p.get("bg") or p.get("strange")) for p in per] if per else [True] * len(datas)
    used = used if any(used) else [True] * len(datas)
    photos = [dict(url=image_url(n), used=u) for n, u in zip(names, used)]
    for ph, p in zip(photos, per or []):
        ph.update(disease=p["top"][0]["disease"], plant=p["top"][0]["plant"], prob=p["top"][0]["prob"])
    if lesion_ok(best["plant_id"], best["healthy"], res.get("kind")):  # lá có bệnh: tô vết hại và ước lượng mức độ theo màu
        try:
            sevs = []
            for n, d, u, ph in zip(names, datas, used, photos):
                ph["lesion_url"] = make_lesion(n, d)
                s = severity(d) if u else None
                if s:
                    sevs.append(s)
            if sevs:  # nhiều ảnh: trung bình tỉ lệ vết hại các ảnh dùng được
                explain["severity"] = sevs[0] if len(sevs) == 1 else dict(
                    severity_level(sum(s["pct"] for s in sevs) / len(sevs), sum(s["leaf_pct"] for s in sevs) / len(sevs)), photos=len(sevs))
            if photos[0]["lesion_url"]:
                explain["lesion_url"] = photos[0]["lesion_url"]
        except Exception as e:
            print("[model] lỗi tìm vết hại:", repr(e), flush=True)
    if len(photos) > 1:
        explain["photos"] = photos
    keep = res["source"] == "ai" and cls and best["prob"] >= AI_SAMPLE_MIN_CONF
    demo = current_app.model.demo and res["source"] == "model" and res.get("kind") != "pest"
    details = dict(top=res["top"], notes=res["notes"], symptoms=best.get("symptoms", ""), demo=demo, plant_choice=plant_id, ai_failed=ai_failed,
                   ai=res.get("ai"), **explain, **({"kind": "pest", "pest": res["pest"]} if res.get("kind") == "pest" else {}))
    # Vị trí để ghim ca bệnh lên bản đồ: gửi kèm, hoặc vị trí đã lưu trong hồ sơ (không có thì để trống)
    lat, lon = coords(request.form.get("lat", me_row()["lat"]), request.form.get("lon", me_row()["lon"]))
    diag_id = db().execute("INSERT INTO diagnoses(user_id,plant_id,plant,disease,raw,healthy,confidence,remedy,image,source,details,lat,lon) "
                           "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
                           (session["uid"], best["plant_id"], best["plant"], best["disease"], best["raw"], int(best["healthy"]), best["prob"],
                            best["remedy"], name, res["source"], json.dumps(details, ensure_ascii=False), lat, lon)).fetchone()[0]
    if keep:  # AI kết luận chung cho cả lượt: lưu mọi ảnh dùng được, mỗi ảnh một mẫu
        for i, (d, u) in enumerate(zip(datas, used)):
            if u:
                save_sample(d, cls, diag_id, best, per[i]["emb"] if per and "emb" in per[i] else emb if i == 0 else current_app.model.embed(d))
    db().commit()
    return jsonify(diagnosis_id=diag_id, result=best, top=res["top"], source=res["source"], demo=demo,
                   low_confidence=best["prob"] < LOW_CONF, notes=res["notes"], image_url=image_url(name))

@bp.post("/api/diagnoses/<int:did>/reanalyze")
@login_required
def reanalyze(did):
    """Gọi lại AI cho một kết quả: khi lần trước AI lỗi (VD hết lượt gọi) hoặc người dùng thấy kết quả chưa đúng.
    Nhãn mới thay nhãn cũ: mẫu của lần chẩn đoán này và ảnh gần như trùng mang nhãn khác bị gỡ khỏi bộ nhớ/dataset."""
    d = get_diag(did)
    if not d:
        return err("Không tìm thấy kết quả chẩn đoán", 404)
    if not d["image"]:
        return err("Kết quả này không có ảnh để phân tích lại")
    if json.loads(d["details"] or "{}").get("kind") == "pest":
        return err("Phân tích lại bằng AI hiện chỉ dành cho bệnh trên lá; với sâu hại hãy hỏi trợ lý AI")
    if not ai_quota_ok():
        return err(f"Bạn đã dùng hết {AI_DAILY_LIMIT} lượt AI hôm nay, hãy thử lại ngày mai", 429)
    if not ai_service.vision_available():
        return err("Chưa cấu hình khóa Gemini nên không phân tích lại được", 503)
    try:
        with open(os.path.join(current_app.config["UPLOAD_DIR"], d["image"]), "rb") as f:
            data = f.read()
    except OSError:
        return err("Không còn ảnh gốc để phân tích lại", 404)
    det = json.loads(d["details"] or "{}")
    choice = det.get("plant_choice", "auto")
    datas = [data] + [x for x in (read_upload(p["url"]) for p in (det.get("photos") or [])[1:] if p.get("used", True)) if x]  # ảnh thêm
    try:
        a = ai_service.analyze_image(datas if len(datas) > 1 else data, knowledge.PLANTS.get(choice) or learned_plants().get(choice))
    except Exception as e:
        print("[ai] lỗi phân tích lại:", repr(e), flush=True)
        return err(f"Chưa phân tích lại được: {ai_service.reason(e)}.", 503)
    best, cls = ai_result(a)
    emb = current_app.model.embed(data)
    stale = {s["id"]: s for s in db().execute("SELECT * FROM ai_samples WHERE diagnosis_id=?", (did,))}
    for s in db().execute("SELECT * FROM ai_samples WHERE embed_key=? AND class_name IS DISTINCT FROM ?", (current_app.model.embed_key, cls)):
        if len(s["embedding"] or b"") == emb.nbytes and float(np.frombuffer(s["embedding"], dtype=np.float32) @ emb) >= MEMORY_MATCH:
            stale[s["id"]] = s
    drop_samples(stale.values())
    det.update(notes=["Đã phân tích lại bằng AI (Gemini)."] + ai_notes(best, cls, choice), symptoms=best["symptoms"], ai_failed=False,
               demo=False, ai=ai_raw(a))
    db().execute("UPDATE diagnoses SET plant_id=?, plant=?, disease=?, raw=?, healthy=?, confidence=?, remedy=?, source='ai', details=? WHERE id=?",
                 (best["plant_id"], best["plant"], best["disease"], best["raw"], int(best["healthy"]), best["prob"], best["remedy"],
                  json.dumps(det, ensure_ascii=False), did))
    if cls and best["prob"] >= AI_SAMPLE_MIN_CONF:
        for i, x in enumerate(datas):
            save_sample(x, cls, did, best, emb if i == 0 else current_app.model.embed(x))
    db().commit()
    return jsonify(ok=True)

def read_upload(url):
    """Nội dung file đã tải lên theo đường dẫn /uploads/...; None nếu không còn."""
    try:
        with open(os.path.join(current_app.config["UPLOAD_DIR"], url.removeprefix("/uploads/")), "rb") as f:
            return f.read()
    except (OSError, AttributeError):
        return None

def get_diag(did):
    if did is None:
        return None
    r = db().execute("SELECT * FROM diagnoses WHERE id=? AND user_id=?", (did, session["uid"])).fetchone()
    return dict(r) if r else None

@bp.get("/api/history")
@login_required
def history():
    rows = db().execute("SELECT d.id, d.plant, d.disease, d.confidence, d.healthy, d.source, d.image, d.created, r.stars FROM diagnoses d "
                        "LEFT JOIN ratings r ON r.diagnosis_id=d.id AND r.user_id=d.user_id WHERE d.user_id=? ORDER BY d.id DESC LIMIT 200",
                        (session["uid"],)).fetchall()
    return jsonify([dict(r, image_url=image_url(r["image"])) for r in rows])

@bp.get("/api/diagnoses/<int:did>")
@login_required
def diagnosis(did):
    d = get_diag(did)
    if not d:
        return err("Không tìm thấy kết quả chẩn đoán", 404)
    r = db().execute("SELECT stars, comment FROM ratings WHERE diagnosis_id=? AND user_id=?", (did, session["uid"])).fetchone()
    d.update(image_url=image_url(d.pop("image")), details=json.loads(d["details"]) if d["details"] else {}, rating=dict(r) if r else None)
    for k in ("cams", "cam_url"):  # Grad-CAM đã bỏ (vùng chú ý không khớp vết bệnh); kết quả cũ vẫn còn trường này
        d["details"].pop(k, None)
    d["details"]["lesion_available"] = bool(d["image_url"]) and lesion_ok(d["plant_id"], d["healthy"], d["details"].get("kind"))
    d["details"]["notes"] = [n.replace("với ảnh AI đã xác định trước đó, hệ thống dùng lại kết quả đã học",  # ghi chú của kết quả cũ
                                       "với một mẫu trong dữ liệu hệ thống đã học, hệ thống dùng lại kết quả của mẫu đó")
                             for n in d["details"].get("notes") or []]
    return jsonify(d)

@bp.delete("/api/diagnoses/<int:did>")
@login_required
def delete_diagnosis(did):
    d = get_diag(did)
    if not d:
        return err("Không tìm thấy kết quả chẩn đoán", 404)
    for t in ("chats", "ratings", "reports"):
        db().execute(f"DELETE FROM {t} WHERE diagnosis_id=? AND user_id=?", (did, session["uid"]))
    db().execute("UPDATE posts SET diagnosis_id=NULL WHERE diagnosis_id=?", (did,))  # bài đã chia sẻ thì bỏ thẻ kết quả
    db().execute("DELETE FROM diagnoses WHERE id=?", (did,))
    db().commit()
    remove_upload(d["image"])  # ảnh đã lưu vào dataset_ai (nếu có) vẫn giữ để huấn luyện
    if d["image"]:
        remove_upload(d["image"][:-4] + "-cam.jpg")
        remove_upload(d["image"][:-4] + "-lesion.jpg")
        det = json.loads(d["details"]) if d["details"] else {}
        for c in list(det.get("cams", {}).values()) + det.get("photos", []):  # bản đồ Grad-CAM của kết quả cũ, ảnh thêm và ảnh vết bệnh của chúng
            for k in ("url", "lesion_url"):
                if c.get(k) and c[k] != image_url(d["image"]):
                    remove_upload(c[k].removeprefix("/uploads/"))
    return jsonify(ok=True)

# ---------- Vết bệnh: phần lá không còn xanh, tìm theo màu (không dùng mô hình) ----------
def lesion_ok(plant_id, healthy, kind=None):
    """Có tô vết hại cho kết quả này không: chỉ lá có bệnh (không phải sâu hại, lá khỏe, ảnh không nhận ra lá)."""
    return kind != "pest" and plant_id not in ("unknown", "background", "pest") and not healthy

def make_lesion(image_name, data):
    """Lưu ảnh tô vết hại cạnh ảnh tra cứu (<ảnh>-lesion.jpg); None nếu không tách được lá khỏi nền."""
    img = lesion_overlay(data)
    if not img:
        return None
    lesion_name = image_name[:-4] + "-lesion.jpg"
    with open(os.path.join(current_app.config["UPLOAD_DIR"], lesion_name), "wb") as fh:
        fh.write(img)
    return image_url(lesion_name)

@bp.get("/api/diagnoses/<int:did>/lesion")
@login_required
def diagnosis_lesion(did):
    """Ảnh tô vết hại của một kết quả; kết quả cũ (trước khi có tính năng này) thì vẽ lần đầu rồi lưu vào details.lesion_url."""
    d = get_diag(did)
    if not d:
        return err("Không tìm thấy kết quả chẩn đoán", 404)
    det = json.loads(d["details"]) if d["details"] else {}
    if det.get("lesion_url"):
        return jsonify(url=det["lesion_url"])
    if not d["image"] or not lesion_ok(d["plant_id"], d["healthy"], det.get("kind")):
        return err("Kết quả này không có ảnh vết bệnh (chỉ có cho lá bị bệnh)", 400)
    if not rate_limit(("lesion", session["uid"]), 30, 60):
        return err(TOO_MANY, 429)
    try:
        with open(os.path.join(current_app.config["UPLOAD_DIR"], d["image"]), "rb") as f:
            data = f.read()
    except OSError:
        return err("Không tìm thấy ảnh gốc", 404)
    url = make_lesion(d["image"], data)
    if not url:
        return err("Không tách được lá khỏi nền ảnh nên chưa tô được vết bệnh; hãy chụp lá trên nền đơn giản", 422)
    det["lesion_url"] = url
    db().execute("UPDATE diagnoses SET details=? WHERE id=?", (json.dumps(det, ensure_ascii=False), did))
    db().commit()
    return jsonify(url=url)

# ---------- Chat AI ----------
@bp.get("/api/chat")
@login_required
def chat_history():
    did = request.args.get("diagnosis_id", type=int)
    if did is not None and not get_diag(did):
        return err("Không tìm thấy kết quả chẩn đoán", 404)
    rows = db().execute("SELECT role, content, image, created FROM chats WHERE user_id=? AND diagnosis_id IS NOT DISTINCT FROM ? ORDER BY id", (session["uid"], did)).fetchall()
    return jsonify([dict(role=r["role"], content=r["content"], created=r["created"], image_url=image_url(r["image"])) for r in rows])

@bp.post("/api/chat")
@login_required
def chat():
    """JSON {message, diagnosis_id} hoặc multipart (message, diagnosis_id, image): gửi kèm ảnh để AI xem và trả lời."""
    if request.files.get("image"):
        f, src_form = request.files["image"], request.form
    else:
        f, src_form = None, request.get_json(silent=True) or {}
    msg = (src_form.get("message") or "").strip()
    if len(msg) > 1000 or (not msg and not f):
        return err("Tin nhắn trống hoặc quá dài (tối đa 1000 ký tự)")
    if not rate_limit(("chat", session["uid"]), 20, 60):
        return err(TOO_MANY, 429)
    if not ai_quota_ok():
        return err(f"Bạn đã dùng hết {AI_DAILY_LIMIT} lượt AI hôm nay, hãy thử lại ngày mai", 429)
    did = src_form.get("diagnosis_id")
    did = int(did) if did not in (None, "", "null") else None
    d = get_diag(did)
    if did is not None and not d:
        return err("Không tìm thấy kết quả chẩn đoán", 404)
    name = data = None
    if f:
        name, data = save_image(f.read(), "chats")
        if not name:
            return err("File không phải ảnh hợp lệ", field="image")
        msg = msg or "Hãy xem ảnh này và cho tôi biết cây có bị gì không, cách xử lý ra sao."
    hist = [dict(r) for r in db().execute("SELECT role,content FROM chats WHERE user_id=? AND diagnosis_id IS NOT DISTINCT FROM ? ORDER BY id", (session["uid"], did)).fetchall()]
    reply, src = ai_service.ask(msg, hist, d, data)
    for role, content, img in (("user", msg, name), ("assistant", reply, None)):
        db().execute("INSERT INTO chats(user_id,diagnosis_id,role,content,image) VALUES(?,?,?,?,?)", (session["uid"], did, role, content, img))
    db().commit()
    return jsonify(reply=reply, source=src, message=msg, image_url=image_url(name))

# ---------- Đánh giá ----------
@bp.post("/api/rating")
@login_required
def rating():
    j = request.get_json(silent=True) or {}
    stars, did = j.get("stars"), j.get("diagnosis_id")
    if not isinstance(stars, int) or isinstance(stars, bool) or not 1 <= stars <= 5:
        return err("Số sao phải từ 1 đến 5")
    if did is None:
        return err("Hãy chọn một kết quả tra cứu để đánh giá")
    if not get_diag(did):
        return err("Không tìm thấy kết quả chẩn đoán", 404)
    db().execute("DELETE FROM ratings WHERE user_id=? AND diagnosis_id=?", (session["uid"], did))
    db().execute("INSERT INTO ratings(user_id,diagnosis_id,stars,comment) VALUES(?,?,?,?)", (session["uid"], did, stars, (j.get("comment") or "").strip()[:500]))
    db().commit()
    return jsonify(ok=True), 201

@bp.get("/api/ratings")
@login_required
def ratings():
    dist = {s: 0 for s in range(1, 6)}
    for r in db().execute("SELECT stars, COUNT(*) n FROM ratings WHERE diagnosis_id IS NOT NULL GROUP BY stars"):
        dist[r["stars"]] = r["n"]
    count = sum(dist.values())
    items = db().execute("SELECT r.id, r.stars, r.comment, r.created, u.username, d.plant, d.disease, d.source FROM ratings r "
                         "JOIN users u ON u.id=r.user_id JOIN diagnoses d ON d.id=r.diagnosis_id ORDER BY r.id DESC LIMIT 50").fetchall()
    pending = db().execute("SELECT d.id, d.plant, d.disease, d.confidence, d.image, d.created FROM diagnoses d WHERE d.user_id=? AND NOT EXISTS "
                           "(SELECT 1 FROM ratings r WHERE r.diagnosis_id=d.id AND r.user_id=d.user_id) ORDER BY d.id DESC LIMIT 10",
                           (session["uid"],)).fetchall()
    return jsonify(avg=round(sum(s * n for s, n in dist.items()) / count, 2) if count else 0, count=count, dist=dist,
                   items=[dict(r) for r in items], pending=[dict(r, image_url=image_url(r["image"])) for r in pending])

# ---------- Bài đăng cộng đồng ----------
def visible_post(pid, approved=False):
    """Bài viết người đang xem được thấy (đã duyệt, của mình, hoặc là quản trị viên); approved=True: chỉ bài đã duyệt."""
    rows = post_rows("WHERE p.id=?", (pid,))
    r = rows[0] if rows else None
    if not r or (r["status"] != "approved" and (approved or (r["user_id"] != session["uid"] and not is_admin()))):
        return None
    return r

def moderation_status(m):
    status = {"approve": "approved", "reject": "rejected"}.get(m["decision"], "pending")
    return status, (m["feedback"] or "Nội dung chưa phù hợp với tiêu chuẩn cộng đồng.") if status == "rejected" else None

def post_created(pid, status, feedback):
    if status == "rejected":
        notify(session["uid"], f"Bài viết của bạn không được đăng: {feedback}", "#/home/mine")
    db().commit()
    message = {"approved": "Bài viết đã được đăng.", "pending": "Bài viết đang chờ quản trị viên duyệt.",
               "rejected": f"Bài viết không được đăng: {feedback}"}[status]
    return jsonify(post=post_out(post_rows("WHERE p.id=?", (pid,))[0]), status=status, message=message), 201

@bp.get("/api/posts")
@login_required
def posts():
    if request.args.get("scope") == "mine":
        rows = post_rows("WHERE p.user_id=? ORDER BY p.id DESC LIMIT 100", (session["uid"],))
    else:
        rows = post_rows("WHERE p.status='approved' ORDER BY p.id DESC LIMIT 50")
    return jsonify([post_out(r) for r in rows])

@bp.get("/api/posts/<int:pid>")
@login_required
def post_detail(pid):
    r = visible_post(pid)
    if not r:
        return err("Không tìm thấy bài viết", 404)
    uid = session["uid"]
    rows = db().execute("SELECT c.id, c.content, c.created, c.user_id, u.username FROM comments c JOIN users u ON u.id=c.user_id "
                        "WHERE c.post_id=? ORDER BY c.id", (pid,)).fetchall()
    comments = [dict(id=c["id"], content=c["content"], created=c["created"], username=c["username"],
                     can_delete=c["user_id"] == uid or r["user_id"] == uid or is_admin()) for c in rows]
    return jsonify(post=post_out(r), comments=comments)

@bp.get("/api/posts/<int:pid>/result")
@login_required
def shared_result(pid):
    """Chi tiết kết quả tra cứu được chia sẻ trong bài viết (chỉ đọc, ai thấy bài viết đều xem được)."""
    r = visible_post(pid)
    d = db().execute("SELECT * FROM diagnoses WHERE id=?", (r["diagnosis_id"],)).fetchone() if r and r["diagnosis_id"] else None
    if not d:
        return err("Không tìm thấy kết quả tra cứu", 404)
    det = json.loads(d["details"] or "{}")
    return jsonify(post_id=pid, username=r["username"], is_mine=d["user_id"] == session["uid"], diagnosis_id=d["id"],
                   plant=d["plant"], plant_id=d["plant_id"], disease=d["disease"], healthy=bool(d["healthy"]), confidence=d["confidence"],
                   remedy=d["remedy"], symptoms=det.get("symptoms", ""), differential=(det.get("ai") or {}).get("differential", ""),
                   image_url=image_url(d["image"]), created=d["created"])

@bp.post("/api/posts")
@login_required
def create_post():
    if not rate_limit(("post", session["uid"]), 5, 10 * 60):
        return err("Bạn đăng bài quá nhanh (tối đa 5 bài trong 10 phút)", 429)
    content, f = (request.form.get("content") or "").strip(), request.files.get("image")
    did = request.form.get("diagnosis_id", type=int)
    diag = get_diag(did) if did else None
    if did and not diag:
        return err("Không tìm thấy kết quả tra cứu để chia sẻ", 404)
    if len(content) > 2000:
        return err("Nội dung tối đa 2000 ký tự", field="content")
    if not content and not f and not diag:
        return err("Hãy viết nội dung, thêm ảnh hoặc chia sẻ một kết quả tra cứu", field="content")
    name = data = None
    if f:
        name, data = save_image(f.read(), "posts")
        if not name:
            return err("File không phải ảnh hợp lệ", field="image")
    check = data
    if diag and not check and diag["image"]:  # ảnh tra cứu sẽ hiện công khai nên cũng cần AI kiểm tra
        try:
            with open(os.path.join(current_app.config["UPLOAD_DIR"], diag["image"]), "rb") as fh:
                check = fh.read()
        except OSError:
            pass
    text = content + (f"\n(Kèm kết quả tra cứu: {diag['plant']}, {diag['disease']})" if diag else "")
    m = ai_service.moderate(text, check)
    status, feedback = moderation_status(m)
    pid = db().execute("INSERT INTO posts(user_id,content,image,status,ai_decision,ai_reason,feedback,diagnosis_id) VALUES(?,?,?,?,?,?,?,?) RETURNING id",
                       (session["uid"], content, name, status, m["decision"], m["reason"], feedback, did)).fetchone()[0]
    return post_created(pid, status, feedback)

@bp.delete("/api/posts/<int:pid>")
@login_required
def delete_post(pid):
    p = db().execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
    if not p or (p["user_id"] != session["uid"] and not is_admin()):
        return err("Không tìm thấy bài viết", 404)
    for t in ("post_likes", "comments", "post_shares"):
        db().execute(f"DELETE FROM {t} WHERE post_id=?", (pid,))
    db().execute("DELETE FROM posts WHERE id=?", (pid,))  # bài chia sẻ lại sẽ hiện "bài gốc đã bị xóa"
    db().commit()
    remove_upload(p["image"])
    return jsonify(ok=True)

@bp.post("/api/posts/<int:pid>/like")
@login_required
def like_post(pid):
    r = visible_post(pid, approved=True)
    if not r:
        return err("Không tìm thấy bài viết", 404)
    uid = session["uid"]
    liked = not db().execute("SELECT 1 FROM post_likes WHERE post_id=? AND user_id=?", (pid, uid)).fetchone()
    if liked:
        db().execute("INSERT INTO post_likes(post_id,user_id) VALUES(?,?)", (pid, uid))
        if r["user_id"] != uid:
            notify(r["user_id"], f"{me_row()['username']} đã thích bài viết của bạn.", f"#/p/{pid}")
    else:
        db().execute("DELETE FROM post_likes WHERE post_id=? AND user_id=?", (pid, uid))
    db().commit()
    return jsonify(liked=liked, likes=db().execute("SELECT COUNT(*) FROM post_likes WHERE post_id=?", (pid,)).fetchone()[0])

@bp.post("/api/posts/<int:pid>/comments")
@login_required
def add_comment(pid):
    r = visible_post(pid, approved=True)
    if not r:
        return err("Không tìm thấy bài viết", 404)
    content = ((request.get_json(silent=True) or {}).get("content") or "").strip()
    if not content or len(content) > 1000:
        return err("Bình luận trống hoặc quá dài (tối đa 1000 ký tự)", field="content")
    if not rate_limit(("comment", session["uid"]), 10, 10 * 60):
        return err("Bạn bình luận quá nhanh (tối đa 10 bình luận trong 10 phút)", 429, "content")
    m = ai_service.moderate(content, kind="comment")
    if m["decision"] == "reject":  # AI lỗi/không chắc vẫn đăng: bình luận ngắn, chủ bài và quản trị viên xóa được
        print(f"[ai] từ chối bình luận của {me_row()['username']}: {content[:80]!r} ({m['reason']})", flush=True)
        return err(f"Bình luận chưa phù hợp: {m['feedback'] or 'nội dung vi phạm tiêu chuẩn cộng đồng.'}", field="content")
    cid = db().execute("INSERT INTO comments(post_id,user_id,content,ai_decision) VALUES(?,?,?,?) RETURNING id",
                       (pid, session["uid"], content, m["decision"])).fetchone()[0]
    if r["user_id"] != session["uid"]:
        notify(r["user_id"], f"{me_row()['username']} đã bình luận về bài viết của bạn: “{content[:60]}”", f"#/p/{pid}")
    db().commit()
    c = db().execute("SELECT created FROM comments WHERE id=?", (cid,)).fetchone()
    return jsonify(comment=dict(id=cid, content=content, created=c["created"], username=me_row()["username"], can_delete=True)), 201

@bp.delete("/api/comments/<int:cid>")
@login_required
def delete_comment(cid):
    c = db().execute("SELECT c.user_id, p.user_id owner FROM comments c JOIN posts p ON p.id=c.post_id WHERE c.id=?", (cid,)).fetchone()
    if not c or session["uid"] not in (c["user_id"], c["owner"]) and not is_admin():
        return err("Không tìm thấy bình luận", 404)
    db().execute("DELETE FROM comments WHERE id=?", (cid,))
    db().commit()
    return jsonify(ok=True)

@bp.post("/api/posts/<int:pid>/share")
@login_required
def share_post(pid):
    """kind='link': gửi liên kết qua ứng dụng khác (chỉ đếm); kind='repost': chia sẻ lên trang của mình, có thể kèm lời."""
    r = visible_post(pid, approved=True)
    if not r:
        return err("Không tìm thấy bài viết", 404)
    if r["shared_post_id"]:  # chia sẻ một bài chia sẻ thì trỏ thẳng về bài gốc
        root = visible_post(r["shared_post_id"], approved=True)
        r = root or r
    j = request.get_json(silent=True) or {}
    uid, kind = session["uid"], j.get("kind")
    if kind == "link":
        db().execute("INSERT INTO post_shares(post_id,user_id,kind) VALUES(?,?,'link')", (r["id"], uid))
        db().commit()
        return jsonify(shares=db().execute("SELECT COUNT(*) FROM post_shares WHERE post_id=?", (r["id"],)).fetchone()[0])
    if kind != "repost":
        return err("Cách chia sẻ không hợp lệ")
    content = (j.get("content") or "").strip()
    if len(content) > 2000:
        return err("Nội dung tối đa 2000 ký tự", field="content")
    m = ai_service.moderate(content) if content else dict(decision="approve", reason="Chia sẻ lại bài đã duyệt, không kèm lời", feedback="")
    status, feedback = moderation_status(m)
    new_id = db().execute("INSERT INTO posts(user_id,content,status,ai_decision,ai_reason,feedback,shared_post_id) VALUES(?,?,?,?,?,?,?) RETURNING id",
                          (uid, content, status, m["decision"], m["reason"], feedback, r["id"])).fetchone()[0]
    if status != "rejected":
        db().execute("INSERT INTO post_shares(post_id,user_id,kind) VALUES(?,?,'repost')", (r["id"], uid))
    if status == "approved" and r["user_id"] != uid:
        notify(r["user_id"], f"{me_row()['username']} đã chia sẻ bài viết của bạn.", f"#/p/{r['id']}")
    return post_created(new_id, status, feedback)

# ---------- Thông báo ----------
@bp.get("/api/notifications")
@login_required
def notifications():
    rows = db().execute("SELECT id, content, link, read, created FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50", (session["uid"],)).fetchall()
    return jsonify([dict(r) for r in rows])

@bp.post("/api/notifications/read")
@login_required
def notifications_read():
    db().execute("UPDATE notifications SET read=1 WHERE user_id=?", (session["uid"],))
    db().commit()
    return jsonify(ok=True)

# ---------- Nhật ký điều trị và nhắc việc ----------
LOG_KINDS = ("phun", "tia", "tuoi", "kiemtra", "khac")  # phun thuốc, tỉa/vệ sinh, tưới/bón, kiểm tra, khác
MAX_REMINDERS = 30

def parse_when(s):
    """'2026-10-30T07:00:00.000Z' / '2026-10-30 07:00:00' (UTC, do giao diện đổi từ giờ địa phương) -> 'YYYY-MM-DD HH:MM:SS' hoặc None."""
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if d.tzinfo:
        d = d.astimezone(timezone.utc)
    return d.strftime("%Y-%m-%d %H:%M:%S")

def get_treatment(tid):
    r = db().execute("SELECT * FROM treatments WHERE id=? AND user_id=?", (tid, session["uid"])).fetchone()
    return dict(r) if r else None

def parse_reminder(j):
    """Kiểm tra một nhắc việc {content, due, repeat_days}; trả về ((nội dung, hạn UTC, lặp), None) hoặc (None, response lỗi)."""
    content = (j.get("content") or "").strip()
    if not content or len(content) > 200:
        return None, err("Nội dung nhắc việc 1-200 ký tự", field="content")
    when = parse_when(j.get("due"))
    if not when:
        return None, err("Thời điểm nhắc không hợp lệ", field="due")
    try:
        repeat_days = int(j.get("repeat_days") or 0)
    except (TypeError, ValueError):
        repeat_days = -1
    if not 0 <= repeat_days <= 60:
        return None, err("Lặp lại tối đa mỗi 60 ngày", field="repeat_days")
    return (content, when, repeat_days), None

def insert_reminder(tid, rm):
    db().execute("INSERT INTO reminders(treatment_id,user_id,content,due,repeat_days) VALUES(?,?,?,?,?)", (tid, session["uid"]) + rm)

def treatment_out(t):
    q = lambda sql, *a: db().execute(sql, (t["id"],) + a).fetchone()[0]
    nxt = db().execute("SELECT content, due FROM reminders WHERE treatment_id=? AND done=0 ORDER BY due LIMIT 1", (t["id"],)).fetchone()
    d = db().execute("SELECT id, image, confidence, healthy, plant_id, source FROM diagnoses WHERE id=?", (t["diagnosis_id"],)).fetchone() if t["diagnosis_id"] else None
    return dict(t, logs=q("SELECT COUNT(*) FROM treatment_logs WHERE treatment_id=?"),
                pending=q("SELECT COUNT(*) FROM reminders WHERE treatment_id=? AND done=0"),
                overdue=q("SELECT COUNT(*) FROM reminders WHERE treatment_id=? AND done=0 AND due<=?", utcnow()),
                next=dict(nxt) if nxt else None, diagnosis=dict(d, image_url=image_url(d["image"])) if d else None,
                last_log=q("SELECT MAX(created) FROM treatment_logs WHERE treatment_id=?"))

@bp.get("/api/treatments")
@login_required
def treatments():
    rows = db().execute("SELECT * FROM treatments WHERE user_id=? ORDER BY (status='active') DESC, id DESC LIMIT 200", (session["uid"],)).fetchall()
    return jsonify([treatment_out(dict(r)) for r in rows])

@bp.get("/api/care-plan")
@login_required
def care_plan():
    """Lịch nhắc việc gợi ý theo nhóm bệnh/sâu hại: ?diagnosis_id= (kết quả tra cứu) hoặc ?disease=&plant= (tự ghi)."""
    did = request.args.get("diagnosis_id", type=int)
    if did is not None:
        d = get_diag(did)
        if not d:
            return err("Không tìm thấy kết quả tra cứu", 404)
        det = json.loads(d["details"] or "{}")
        pest = d["plant_id"] == "pest" or det.get("kind") == "pest"
        return jsonify(care.plan(d["disease"], d["raw"], d["remedy"], bool(d["healthy"]), d["raw"] if pest else None, pest))
    return jsonify(care.plan((request.args.get("disease") or "")[:100]))

@bp.post("/api/treatments")
@login_required
def create_treatment():
    """Mở nhật ký theo dõi: từ một kết quả tra cứu (diagnosis_id) hoặc tự ghi (plant, disease); kèm nhắc việc ban đầu."""
    j = request.get_json(silent=True) or {}
    did, name = j.get("diagnosis_id"), (j.get("name") or "").strip()[:80]
    plant, disease = (j.get("plant") or "").strip()[:60], (j.get("disease") or "").strip()[:100]
    if did is not None:
        d = get_diag(did)
        if not d:
            return err("Không tìm thấy kết quả tra cứu", 404)
        plant, disease = plant or d["plant"], disease or d["disease"]
        if db().execute("SELECT 1 FROM treatments WHERE diagnosis_id=? AND user_id=? AND status='active'", (did, session["uid"])).fetchone():
            return err("Kết quả này đã có nhật ký đang theo dõi", 409)
    if not plant or not disease:
        return err("Cần tên cây và tên bệnh/sâu hại", field="plant")
    rms = []
    for item in (j.get("reminders") or [])[:MAX_REMINDERS]:
        rm, bad = parse_reminder(item if isinstance(item, dict) else {})
        if bad:
            return bad
        rms.append(rm)
    if not rate_limit(("treatment", session["uid"]), 30, 3600):
        return err(TOO_MANY, 429)
    tid = db().execute("INSERT INTO treatments(user_id,diagnosis_id,name,plant,disease) VALUES(?,?,?,?,?) RETURNING id",
                       (session["uid"], did, name or None, plant, disease)).fetchone()[0]
    for rm in rms:
        insert_reminder(tid, rm)
    db().commit()
    return jsonify(id=tid), 201

@bp.get("/api/treatments/<int:tid>")
@login_required
def treatment_detail(tid):
    t = get_treatment(tid)
    if not t:
        return err("Không tìm thấy nhật ký", 404)
    out = treatment_out(t)
    out["reminders"] =[dict(r) for r in db().execute("SELECT id, content, due, repeat_days, done, created FROM reminders WHERE treatment_id=? "
                                                      "ORDER BY done, due", (tid,)).fetchall()]
    # PostgreSQL: created là TIMESTAMP còn done_at là TEXT, COALESCE không tự đổi kiểu -> ép created sang chuỗi 'YYYY-MM-DD HH:MM:SS'
    out["entries"] = [dict(r, image_url=image_url(r["image"])) for r in db().execute(
        "SELECT id, kind, content, image, done_at, created FROM treatment_logs WHERE treatment_id=? ORDER BY COALESCE(done_at, CAST(created AS TEXT)) DESC, id DESC", (tid,)).fetchall()]
    if t["diagnosis_id"]:
        d = db().execute("SELECT remedy, details FROM diagnoses WHERE id=?", (t["diagnosis_id"],)).fetchone()
        out["remedy"] = d["remedy"] if d else None
    return jsonify(out)

@bp.put("/api/treatments/<int:tid>")
@login_required
def update_treatment(tid):
    t = get_treatment(tid)
    if not t:
        return err("Không tìm thấy nhật ký", 404)
    j = request.get_json(silent=True) or {}
    if "name" in j:
        db().execute("UPDATE treatments SET name=? WHERE id=?", ((j.get("name") or "").strip()[:80] or None, tid))
    if j.get("status") in ("active", "done"):
        db().execute("UPDATE treatments SET status=?, closed=? WHERE id=?", (j["status"], utcnow() if j["status"] == "done" else None, tid))
        if j["status"] == "done":  # khép nhật ký: bỏ các nhắc việc còn chờ
            db().execute("UPDATE reminders SET done=1 WHERE treatment_id=? AND done=0", (tid,))
    db().commit()
    return jsonify(ok=True)

@bp.delete("/api/treatments/<int:tid>")
@login_required
def delete_treatment(tid):
    t = get_treatment(tid)
    if not t:
        return err("Không tìm thấy nhật ký", 404)
    imgs = [r["image"] for r in db().execute("SELECT image FROM treatment_logs WHERE treatment_id=? AND image IS NOT NULL", (tid,)).fetchall()]
    for tb in ("reminders", "treatment_logs"):
        db().execute(f"DELETE FROM {tb} WHERE treatment_id=?", (tid,))
    db().execute("DELETE FROM treatments WHERE id=?", (tid,))
    db().commit()
    for i in imgs:
        remove_upload(i)
    return jsonify(ok=True)

@bp.post("/api/treatments/<int:tid>/logs")
@login_required
def add_log(tid):
    """Ghi việc đã làm (JSON hoặc multipart có ảnh): kind, content, done_at (tùy chọn), image."""
    t = get_treatment(tid)
    if not t:
        return err("Không tìm thấy nhật ký", 404)
    src = request.form if request.form else (request.get_json(silent=True) or {})
    kind, content = src.get("kind") or "khac", (src.get("content") or "").strip()
    if kind not in LOG_KINDS:
        return err("Loại việc không hợp lệ", field="kind")
    if len(content) > 1000:
        return err("Ghi chú tối đa 1000 ký tự", field="content")
    name = None
    if request.files.get("image"):
        name, _ = save_image(request.files["image"].read(), "treatments")
        if not name:
            return err("File không phải ảnh hợp lệ", field="image")
    if not content and not name:
        return err("Hãy ghi vài chữ hoặc thêm ảnh", field="content")
    if not rate_limit(("log", session["uid"]), 60, 3600):
        remove_upload(name)
        return err(TOO_MANY, 429)
    done_at = parse_when(src.get("done_at")) if src.get("done_at") else None
    lid = db().execute("INSERT INTO treatment_logs(treatment_id,user_id,kind,content,image,done_at) VALUES(?,?,?,?,?,?) RETURNING id",
                       (tid, session["uid"], kind, content, name, done_at)).fetchone()[0]
    db().commit()
    return jsonify(id=lid, image_url=image_url(name)), 201

@bp.delete("/api/logs/<int:lid>")
@login_required
def delete_log(lid):
    r = db().execute("SELECT image FROM treatment_logs WHERE id=? AND user_id=?", (lid, session["uid"])).fetchone()
    if not r:
        return err("Không tìm thấy mục nhật ký", 404)
    db().execute("DELETE FROM treatment_logs WHERE id=?", (lid,))
    db().commit()
    remove_upload(r["image"])
    return jsonify(ok=True)

@bp.post("/api/treatments/<int:tid>/reminders")
@login_required
def create_reminder(tid):
    t = get_treatment(tid)
    if not t:
        return err("Không tìm thấy nhật ký", 404)
    if t["status"] != "active":
        return err("Nhật ký đã khép, hãy mở lại để thêm nhắc việc")
    rm, bad = parse_reminder(request.get_json(silent=True) or {})
    if bad:
        return bad
    if db().execute("SELECT COUNT(*) FROM reminders WHERE treatment_id=? AND done=0", (tid,)).fetchone()[0] >= MAX_REMINDERS:
        return err(f"Mỗi nhật ký tối đa {MAX_REMINDERS} nhắc việc đang chờ")
    insert_reminder(tid, rm)
    db().commit()
    return jsonify(ok=True), 201

@bp.put("/api/reminders/<int:rid>")
@login_required
def update_reminder(rid):
    """done=1: đánh dấu đã làm (tự ghi vào nhật ký; nhắc lặp lại thì hẹn lần sau). done=0: mở lại."""
    r = db().execute("SELECT * FROM reminders WHERE id=? AND user_id=?", (rid, session["uid"])).fetchone()
    if not r:
        return err("Không tìm thấy nhắc việc", 404)
    j = request.get_json(silent=True) or {}
    if "due" in j:
        when = parse_when(j["due"])
        if not when:
            return err("Thời điểm nhắc không hợp lệ", field="due")
        db().execute("UPDATE reminders SET due=?, notified=0 WHERE id=?", (when, rid))
    if j.get("done"):
        db().execute("INSERT INTO treatment_logs(treatment_id,user_id,kind,content) VALUES(?,?,?,?)",
                     (r["treatment_id"], session["uid"], "kiemtra" if "kiểm tra" in r["content"].lower() else "phun" if "phun" in r["content"].lower() else "khac",
                      f"Đã làm: {r['content']}"))
        if r["repeat_days"]:
            base = max(datetime.strptime(r["due"], "%Y-%m-%d %H:%M:%S"), datetime.now(timezone.utc).replace(tzinfo=None))
            nxt = (base + timedelta(days=r["repeat_days"])).strftime("%Y-%m-%d %H:%M:%S")
            db().execute("UPDATE reminders SET due=?, notified=0 WHERE id=?", (nxt, rid))
        else:
            db().execute("UPDATE reminders SET done=1 WHERE id=?", (rid,))
    elif "done" in j:
        db().execute("UPDATE reminders SET done=0, notified=0 WHERE id=?", (rid,))
    db().commit()
    return jsonify(ok=True)

@bp.delete("/api/reminders/<int:rid>")
@login_required
def delete_reminder(rid):
    n = db().execute("DELETE FROM reminders WHERE id=? AND user_id=?", (rid, session["uid"])).rowcount
    db().commit()
    return jsonify(ok=True) if n else err("Không tìm thấy nhắc việc", 404)

@bp.get("/api/reminders")
@login_required
def reminders():
    """Việc cần làm: quá hạn và trong 7 ngày tới (cho trang chủ)."""
    until = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    rows = db().execute("SELECT r.id, r.content, r.due, r.repeat_days, r.treatment_id, t.name, t.plant, t.disease FROM reminders r "
                        "JOIN treatments t ON t.id=r.treatment_id WHERE r.user_id=? AND r.done=0 AND t.status='active' AND r.due<=? "
                        "ORDER BY r.due LIMIT 50", (session["uid"], until)).fetchall()
    return jsonify([dict(r, overdue=r["due"] <= utcnow()) for r in rows])

AGENDA_MAX_DAYS = 62

@bp.get("/api/agenda")
@login_required
def agenda():
    """Lịch việc trong khoảng ?from=&to= (thời điểm UTC, giao diện đổi từ đầu/cuối ngày giờ địa phương; tối đa 62 ngày) để xem theo ngày:
    tasks = việc cần làm (nhắc chưa xong của nhật ký đang theo dõi, kể cả các lần lặp lại sắp tới, đánh dấu projected);
    logs = việc đã làm (ghi chép nhật ký, gồm cả nhắc việc đã đánh dấu xong vì app tự ghi chúng vào nhật ký)."""
    start, end = parse_when(request.args.get("from")), parse_when(request.args.get("to"))
    if not start or not end or end < start:
        return err("Khoảng thời gian không hợp lệ")
    fmt = "%Y-%m-%d %H:%M:%S"
    if datetime.strptime(end, fmt) - datetime.strptime(start, fmt) > timedelta(days=AGENDA_MAX_DAYS):
        return err(f"Tối đa {AGENDA_MAX_DAYS} ngày mỗi lần")
    now, tasks = utcnow(), []
    for r in db().execute("SELECT r.id, r.content, r.due, r.repeat_days, r.treatment_id, t.name, t.plant, t.disease FROM reminders r "
                          "JOIN treatments t ON t.id=r.treatment_id WHERE r.user_id=? AND r.done=0 AND t.status='active' AND r.due<=? ORDER BY r.due",
                          (session["uid"], end)).fetchall():
        due, k = datetime.strptime(r["due"], fmt), 0
        while True:  # lần hẹn hiện tại rồi các lần lặp lại sau đó (chưa có trong CSDL, chỉ để xem trước)
            at = (due + timedelta(days=r["repeat_days"] * k)).strftime(fmt)
            if at > end or (k and not r["repeat_days"]):
                break
            if at >= start:
                tasks.append(dict(r, due=at, projected=k > 0, overdue=k == 0 and at <= now))
            k += 1
            if not r["repeat_days"] or k > AGENDA_MAX_DAYS:
                break
    logs = [dict(l, at=l["done_at"] or str(l["created"])[:19]) for l in db().execute(
        "SELECT l.id, l.kind, l.content, l.done_at, l.created, l.treatment_id, t.name, t.plant, t.disease FROM treatment_logs l "
        "JOIN treatments t ON t.id=l.treatment_id WHERE l.user_id=? AND ((l.done_at IS NOT NULL AND l.done_at BETWEEN ? AND ?) "
        "OR (l.done_at IS NULL AND l.created BETWEEN ? AND ?))", (session["uid"], start, end, start, end)).fetchall()]
    return jsonify(tasks=sorted(tasks, key=lambda x: x["due"]), logs=sorted(logs, key=lambda x: x["at"]))

# ---------- Cảnh báo sâu bệnh theo thời tiết, bản đồ ca bệnh ----------
NEARBY_KM = 30
MAP_DAYS = 60

def nearby_cases(lat, lon, days=14):
    """Ca bệnh (không khỏe) của mọi người dùng trong bán kính NEARBY_KM, gộp theo tên bệnh (không lộ danh tính)."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = db().execute("SELECT plant, disease, lat, lon FROM diagnoses WHERE lat IS NOT NULL AND healthy=0 AND created>=? "
                        "AND plant_id NOT IN ('unknown','background') AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
                        (since, lat - 0.3, lat + 0.3, lon - 0.3, lon + 0.3)).fetchall()
    agg = {}
    for r in rows:
        if weather.distance_km(lat, lon, r["lat"], r["lon"]) <= NEARBY_KM:
            a = agg.setdefault((r["plant"], r["disease"]), dict(plant=r["plant"], disease=r["disease"], count=0))
            a["count"] += 1
    return sorted(agg.values(), key=lambda a: -a["count"])[:8]

@bp.get("/api/weather")
@login_required
def weather_alerts():
    """Dự báo 7 ngày + cảnh báo sâu bệnh cho vị trí ?lat=&lon= (mặc định vị trí đã lưu trong hồ sơ)."""
    r = me_row()
    lat, lon = coords(request.args.get("lat", r["lat"]), request.args.get("lon", r["lon"]))
    if lat is None:
        return err("Chưa có vị trí: hãy bật định vị hoặc chọn địa danh", 400, field="location")
    try:
        rep = weather.report(lat, lon)
        days = rep["days"]
    except Exception as e:
        print("[weather] lỗi lấy dự báo:", repr(e), flush=True)
        return err("Không lấy được dự báo thời tiết (máy chủ cần kết nối Internet tới open-meteo.com), hãy thử lại sau", 503)
    plants = user_plants(db(), session["uid"])
    alerts = weather.assess(days, plants)
    for a in alerts:
        a["plant_names"] = [knowledge.PLANTS.get(p, p) for p in a["plants"]]
    nearby = nearby_cases(lat, lon)
    for n in nearby:
        n["level"] = "cao" if n["count"] >= 5 else "vua" if n["count"] >= 2 else "thap"
    return jsonify(location=dict(lat=lat, lon=lon, place=r["place"] if (lat, lon) == (r["lat"], r["lon"]) else None),
                   days=[dict(d, desc=weather.WMO.get(d["code"], "")) for d in days], alerts=alerts, nearby=nearby, nearby_km=NEARBY_KM,
                   current=dict(rep["current"], desc=weather.WMO.get(rep["current"]["code"], "")) if rep.get("current") else None,
                   hourly=[dict(h, desc=weather.WMO.get(h["code"], "")) for h in rep.get("hourly") or []],
                   parts=[dict(p, desc=weather.WMO.get(p["code"], "")) for p in rep.get("parts") or []],
                   my_plants=plant_names_vi(plants))

def plant_names_vi(ids):
    """Tên tiếng Việt của các mã cây (cây của mô hình hoặc cây AI đã học); bỏ mã không rõ tên (VD "cây không xác định được")."""
    names = {**learned_plants(), **knowledge.PLANTS}
    return sorted({names[p] for p in ids if p in names}, key=lambda s: unicodedata.normalize("NFD", s.lower()))  # xếp theo chữ cái, bỏ qua dấu

@bp.get("/api/geocode")
@login_required
def geocode():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])
    if not rate_limit(("geocode", session["uid"]), 30, 60):
        return err(TOO_MANY, 429)
    try:
        return jsonify(weather.geocode(q))
    except Exception as e:
        print("[weather] lỗi tìm địa danh:", repr(e), flush=True)
        return err("Không tìm được địa danh (máy chủ cần kết nối Internet)", 503)

# ---------- Gợi ý thuốc (AI + Google Search); cửa hàng gần nhất là bản đồ Google Maps nhúng ở giao diện ----------
PRODUCT_TTL_DAYS = 7    # cùng một bệnh dùng lại kết quả tìm kiếm (của mọi người dùng) trong 7 ngày: đỡ tốn lượt AI, trả lời ngay

def cache_get(key, max_age):
    r = db().execute("SELECT data, created FROM lookup_cache WHERE key=?", (key,)).fetchone()
    if not r:
        return None
    created = datetime.strptime(str(r["created"])[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return dict(json.loads(r["data"]), cached_at=str(r["created"])[:19]) if datetime.now(timezone.utc) - created <= max_age else None

def cache_put(key, data, uid=None):
    db().execute("DELETE FROM lookup_cache WHERE key=?", (key,))
    db().execute("INSERT INTO lookup_cache(key, data, user_id) VALUES(?,?,?)", (key, json.dumps(data, ensure_ascii=False), uid))
    db().commit()

def product_target(d):
    """(bệnh, cây, hướng xử lý, khóa cache) cần tìm thuốc cho một kết quả, hoặc None (lá khỏe, thiên địch, chưa xác định)."""
    det = json.loads(d["details"] or "{}")
    if d["healthy"] or d["plant_id"] in ("unknown", "background") or (det.get("pest") or {}).get("beneficial"):
        return None
    pest = det.get("kind") == "pest"
    plant = ((det.get("pest") or {}).get("hosts") or "cây trồng") if pest else d["plant"]
    key = "products:" + (d["raw"] or f"{d['plant']}|{d['disease']}").lower()[:200]
    return d["disease"], plant, d["remedy"] or "", key

@bp.get("/api/diagnoses/<int:did>/products")
@login_required
def diagnosis_products(did):
    """Gợi ý thuốc/chế phẩm cho kết quả tra cứu: AI (Gemini + Google Search) tìm sản phẩm đang bán, giá tham khảo, trang bán.
    Dùng lại kết quả đã tìm cho cùng bệnh trong PRODUCT_TTL_DAYS ngày; ?refresh=1 tìm lại (tính một lượt AI)."""
    d = get_diag(did)
    if not d:
        return err("Không tìm thấy kết quả chẩn đoán", 404)
    target = product_target(d)
    if not target:
        return err("Kết quả này không cần dùng thuốc (cây khỏe, thiên địch hoặc chưa xác định được bệnh)", 400)
    disease, plant, remedy, key = target
    if request.args.get("refresh") != "1":
        hit = cache_get(key, timedelta(days=PRODUCT_TTL_DAYS))
        if hit:
            return jsonify(hit)
    if not ai_service.gemini_available():  # tìm bằng Google Search của Gemini
        return err("Chưa cấu hình khóa Gemini nên chưa tìm được thuốc", 503)
    if not ai_quota_ok():
        return err(f"Bạn đã dùng hết {AI_DAILY_LIMIT} lượt AI hôm nay, hãy thử lại ngày mai", 429)
    if not rate_limit(("products", session["uid"]), 5, 600):
        return err(TOO_MANY, 429)
    try:
        data = shopping.find_products(disease, plant, remedy)
    except Exception as e:
        print("[ai] lỗi tìm thuốc:", repr(e), flush=True)
        return err(f"Chưa tìm được thuốc: {ai_service.reason(e)}.", 503)
    data.update(disease=disease, plant=plant)
    cache_put(key, data, session["uid"])
    return jsonify(dict(data, cached_at=utcnow()))

@bp.get("/api/map")
@login_required
def case_map():
    """Điểm bệnh MAP_DAYS ngày qua của mọi người dùng cho bản đồ: tọa độ làm tròn ~1 km, gộp theo ô và tên bệnh, không kèm danh tính."""
    since = (datetime.now(timezone.utc) - timedelta(days=MAP_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    # PostgreSQL: cột lat/lon thêm bằng migration là kiểu real, ROUND(real, 2) không có -> ép sang NUMERIC (qua DOUBLE PRECISION, vì
    # real -> numeric chỉ giữ 6 chữ số: 105.8549 thành 105.855 rồi làm tròn ra 105.86) và trả về số thực
    r2 = lambda c: f"CAST(ROUND(CAST(CAST({c} AS DOUBLE PRECISION) AS NUMERIC), 2) AS DOUBLE PRECISION)"
    rows = db().execute(f"SELECT plant, disease, {r2('lat')} lat, {r2('lon')} lon, COUNT(*) n, MAX(created) last FROM diagnoses "
                        "WHERE lat IS NOT NULL AND healthy=0 AND created>=? AND plant_id NOT IN ('unknown','background') "
                        f"GROUP BY plant, disease, {r2('lat')}, {r2('lon')} ORDER BY n DESC LIMIT 2000", (since,)).fetchall()
    return jsonify(days=MAP_DAYS, points=[dict(r) for r in rows])

# ---------- Báo kết quả sai (người dùng) và sửa nhãn (quản trị viên duyệt ở trang quản trị) ----------
def label_info(cls):
    """Nhãn đúng được chọn -> thông tin hiển thị như kết quả tra cứu, hoặc None nếu không phải lớp đã biết
    (bệnh lá: lớp của mô hình hoặc AI đã học; sâu hại: loài INSECT204)."""
    if not cls:
        return None
    if cls in pests.PESTS:
        e = pest_entry(cls, 0)
        return dict(kind="pest", raw=cls, plant_id="pest", plant=e["plant"], disease=e["disease"], healthy=e["healthy"],
                    remedy=(f"Cây bị hại: {e['hosts']}. " if e["hosts"] and not e["beneficial"] else "") + e["remedy"])
    mc = model_class(cls)
    if mc or db().execute("SELECT 1 FROM ai_classes WHERE class_name=?", (cls,)).fetchone():
        return dict(kind="leaf", raw=mc or cls, **class_info(mc or cls))
    return None

def move_sample(s, cls):
    """Đổi nhãn một mẫu AI: chuyển ảnh sang thư mục lớp mới trong dataset_ai, cập nhật số mẫu của các lớp AI."""
    root = current_app.config["AI_DATASET_DIR"]
    rel = f"{cls}/{os.path.basename(s['path'])}"
    try:
        os.makedirs(os.path.join(root, cls), exist_ok=True)
        os.replace(os.path.join(root, s["path"]), os.path.join(root, rel))
    except OSError:
        rel = s["path"]  # mất ảnh gốc: vẫn sửa nhãn trong CSDL
    db().execute("UPDATE ai_samples SET class_name=?, path=? WHERE id=?", (cls, rel, s["id"]))
    db().execute("UPDATE ai_classes SET samples=samples-1 WHERE class_name=?", (s["class_name"],))
    db().execute("UPDATE ai_classes SET samples=samples+1 WHERE class_name=?", (cls,))
    db().execute("DELETE FROM ai_classes WHERE samples<=0")

def apply_label(did, cls, note):
    """Quản trị viên xác nhận nhãn đúng cho một kết quả tra cứu: sửa kết quả, đổi nhãn và duyệt các mẫu AI của nó. Kết quả bệnh lá
    chưa có mẫu nào (VD mô hình đoán sai) thì thêm ảnh vào dataset_ai làm mẫu đã duyệt, để lần huấn luyện sau học được ảnh thực tế này."""
    info = label_info(cls)
    d = db().execute("SELECT * FROM diagnoses WHERE id=?", (did,)).fetchone()
    if not info or not d:
        return None
    det = json.loads(d["details"] or "{}")
    det["notes"] = [note] + [n for n in det.get("notes") or [] if not n.startswith("Quản trị viên đã sửa")]
    db().execute("UPDATE diagnoses SET plant_id=?, plant=?, disease=?, raw=?, healthy=?, remedy=?, details=? WHERE id=?",
                 (info["plant_id"], info["plant"], info["disease"], info["raw"], int(info["healthy"]), info["remedy"],
                  json.dumps(det, ensure_ascii=False), did))
    samples = db().execute("SELECT * FROM ai_samples WHERE diagnosis_id=?", (did,)).fetchall()
    for s in samples:
        if s["class_name"] != info["raw"]:
            move_sample(s, info["raw"])
    db().execute("UPDATE ai_samples SET status='approved', reviewed=? WHERE diagnosis_id=?", (utcnow(), did))
    if not samples and info["kind"] == "leaf" and d["image"]:
        data = read_upload(image_url(d["image"]))
        if data:
            rel = f"{info['raw']}/{uuid.uuid4().hex}.jpg"
            path = os.path.join(current_app.config["AI_DATASET_DIR"], rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
            db().execute("INSERT INTO ai_samples(user_id,diagnosis_id,class_name,path,confidence,embedding,embed_key,status,reviewed) "
                         "VALUES(?,?,?,?,?,?,?,'approved',?)",
                         (d["user_id"], did, info["raw"], rel, 1.0, current_app.model.embed(data).astype(np.float32).tobytes(),
                          current_app.model.embed_key, utcnow()))
            db().execute("UPDATE ai_classes SET samples=samples+1 WHERE class_name=?", (info["raw"],))
    return info

@bp.get("/api/diagnoses/<int:did>/report")
@login_required
def get_report(did):
    if not get_diag(did):
        return err("Không tìm thấy kết quả chẩn đoán", 404)
    r = db().execute("SELECT id, class_name, plant, disease, note, status, answer, created, reviewed FROM reports "
                     "WHERE diagnosis_id=? AND user_id=? ORDER BY id DESC LIMIT 1", (did, session["uid"])).fetchone()
    return jsonify(dict(r) if r else None)

@bp.post("/api/diagnoses/<int:did>/report")
@login_required
def report_wrong(did):
    """Người dùng báo kết quả sai: chọn bệnh/loài đúng trong danh sách đã biết (class_name), hoặc ghi tên cây, tên bệnh nếu không có
    trong danh sách. Mỗi kết quả giữ một báo cáo đang chờ (báo lại thì sửa báo cáo đó)."""
    d = get_diag(did)
    if not d:
        return err("Không tìm thấy kết quả chẩn đoán", 404)
    j = request.get_json(silent=True) or {}
    cls = (j.get("class_name") or "").strip()[:200] or None
    plant, disease, note = ((j.get(k) or "").strip() for k in ("plant", "disease", "note"))
    if cls:
        info = label_info(cls)
        if not info:
            return err("Bệnh / loài đã chọn không có trong danh sách", field="class_name")
        if cls == d["raw"]:
            return err("Bệnh bạn chọn trùng với kết quả hiện tại", field="class_name")
        plant, disease = info["plant"], info["disease"]
    elif not disease:
        return err("Hãy chọn bệnh đúng trong danh sách hoặc ghi tên bệnh / sâu hại", field="disease")
    if len(plant) > 80 or len(disease) > 120 or len(note) > 500:
        return err("Nội dung quá dài (tên cây 80, tên bệnh 120, ghi chú 500 ký tự)", field="note")
    if not rate_limit(("report", session["uid"]), 10, 600):
        return err(TOO_MANY, 429)
    old = db().execute("SELECT id FROM reports WHERE diagnosis_id=? AND user_id=? AND status='open'", (did, session["uid"])).fetchone()
    vals = (cls, plant or None, disease, note or None)
    if old:
        db().execute("UPDATE reports SET class_name=?, plant=?, disease=?, note=?, created=CURRENT_TIMESTAMP WHERE id=?", vals + (old["id"],))
    else:
        db().execute("INSERT INTO reports(user_id,diagnosis_id,class_name,plant,disease,note,old_label) VALUES(?,?,?,?,?,?,?)",
                     (session["uid"], did) + vals + (f"{d['plant']}: {d['disease']}",))
    db().commit()
    return jsonify(ok=True)

# ---------- Thư viện bệnh lá và sâu hại (tra cứu không cần ảnh) ----------
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEAF_DATASET = os.getenv("LEAF_DATASET_DIR", os.path.join(PROJECT_DIR, "dataset", "Plant_leave_diseases_dataset_without_augmentation"))
PEST_DATASET = os.getenv("PEST_DATASET_DIR", os.path.join(PROJECT_DIR, "dataset", "INSECT204-A Novel Large-Scale Benchmark Dataset fo", "INSECT204"))

@bp.get("/api/library")
@login_required
def library():
    """Bệnh lá: mọi lớp của bộ dữ liệu bệnh lá mô hình đã học (kể cả lá khỏe, như tab sâu hại có cả thiên địch), cộng bệnh AI học thêm
    đã có ảnh được quản trị viên duyệt (lớp AI chỉ có ảnh người dùng gửi thử, chưa duyệt thì không hiện). Sâu hại: 204 loài INSECT204."""
    approved = {r[0] for r in db().execute("SELECT DISTINCT class_name FROM ai_samples WHERE status='approved'")}
    leaf = []
    for c in known_classes():
        cls, mc = c["class_name"], model_class(c["class_name"])
        if vague_class(cls) or not (mc or cls in approved):
            continue
        i = class_info(cls)
        leaf.append(dict(class_name=cls, plant_id=i["plant_id"], plant=i["plant"], disease=i["disease"], healthy=i["healthy"], remedy=i["remedy"],
                         source="model" if mc else "ai"))
    plants = sorted({(d["plant_id"], d["plant"]) for d in leaf}, key=lambda p: p[1])
    pest = [dict(class_name=raw, name=e["disease"], group=pests.PESTS[raw]["group"], group_name=e["group_name"], hosts=e["hosts"],
                 beneficial=e["beneficial"], remedy=e["remedy"]) for raw in sorted(pests.PESTS) for e in [pest_entry(raw, 0)]]
    groups = [dict(id=k, name=v[0]) for k, v in pests.GROUPS.items() if any(p["group"] == k for p in pest)]
    return jsonify(plants=[dict(id=k, name=v) for k, v in plants], diseases=leaf, pests=pest, groups=groups)

@bp.get("/api/library/image")
@login_required
def library_image():
    """Ảnh minh họa một lớp (?c=<tên lớp>): ảnh đầu tiên trong dataset (bệnh lá / INSECT204) hoặc mẫu AI đã được duyệt (không lấy ảnh
    người dùng gửi chưa duyệt), thu nhỏ một lần rồi lưu ở instance/library/. Không có ảnh -> 404 (giao diện hiện biểu tượng)."""
    cls = request.args.get("c") or ""
    if not label_info(cls):
        abort(404)
    out_dir = os.path.join(current_app.instance_path, "library")
    folder = os.path.join(PEST_DATASET if cls in pests.PESTS else LEAF_DATASET, cls)
    if os.path.isdir(folder):
        key, src = cls, lambda: next((os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.lower().endswith((".jpg", ".jpeg", ".png"))), None)
    else:  # lớp AI học thêm: ảnh đệm đặt tên theo mẫu đang dùng, mẫu bị xóa / đổi nhãn thì không còn hiện
        s = db().execute("SELECT path FROM ai_samples WHERE class_name=? AND status='approved' ORDER BY id DESC LIMIT 1", (cls,)).fetchone()
        if not s:
            abort(404)
        key, src = f"{cls}|{s['path']}", lambda: os.path.join(current_app.config["AI_DATASET_DIR"], s["path"])
    name = hashlib.sha1(key.encode()).hexdigest()[:20] + ".jpg"
    if not os.path.exists(os.path.join(out_dir, name)):
        src = src()
        if not src or not os.path.exists(src):
            abort(404)
        from PIL import Image
        os.makedirs(out_dir, exist_ok=True)
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((360, 360))
            im.save(os.path.join(out_dir, name), "JPEG", quality=82)
    return send_from_directory(out_dir, name, max_age=7 * 86400)

# ---------- Thông báo đẩy (Web Push) ----------
@bp.get("/api/push/key")
@login_required
def push_key():
    return jsonify(key=push.public_key())

@bp.post("/api/push/subscribe")
@login_required
def push_subscribe():
    j = request.get_json(silent=True) or {}
    ep, keys = (j.get("endpoint") or "").strip(), j.get("keys") or {}
    if not re.fullmatch(r"https://\S{10,1000}", ep) or not keys.get("p256dh") or not keys.get("auth"):
        return err("Thông tin đăng ký thông báo không hợp lệ")
    db().execute("DELETE FROM push_subs WHERE endpoint=?", (ep,))  # thiết bị chuyển sang tài khoản khác
    db().execute("INSERT INTO push_subs(user_id,endpoint,p256dh,auth) VALUES(?,?,?,?)",
                 (session["uid"], ep, str(keys["p256dh"])[:200], str(keys["auth"])[:100]))
    db().commit()
    return jsonify(ok=True)

@bp.post("/api/push/unsubscribe")
@login_required
def push_unsubscribe():
    ep = ((request.get_json(silent=True) or {}).get("endpoint") or "").strip()
    db().execute("DELETE FROM push_subs WHERE endpoint=? AND user_id=?", (ep, session["uid"]))
    db().commit()
    return jsonify(ok=True)

@bp.post("/api/push/test")
@login_required
def push_test():
    n = db().execute("SELECT COUNT(*) FROM push_subs WHERE user_id=?", (session["uid"],)).fetchone()[0]
    if not n:
        return err("Thiết bị này chưa bật thông báo", 400)
    if not rate_limit(("push-test", session["uid"]), 5, 600):
        return err(TOO_MANY, 429)
    push.send(db(), current_app.config["DATABASE"], [session["uid"]], "Thông báo thử: thiết bị của bạn đã nhận được thông báo.", "/notifications")
    return jsonify(ok=True, devices=n)
