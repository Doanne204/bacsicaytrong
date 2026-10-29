"""Thông báo đẩy (Web Push): báo về trình duyệt / điện thoại đã bật thông báo, kể cả khi không mở app (nhắc việc, cảnh báo thời tiết,
duyệt bài, trả lời báo kết quả sai...). Mỗi thông báo trong app (core.notify) cũng được đẩy tới các thiết bị của người đó.
Khóa VAPID tự tạo lần đầu, lưu ở instance/vapid_private.pem (không có trong git; đổi khóa thì mọi thiết bị phải bật lại thông báo).
Gửi ở luồng nền để không làm chậm yêu cầu; thiết bị đã hủy đăng ký (dịch vụ đẩy trả 404/410) thì xóa khỏi bảng push_subs.
Trình duyệt chỉ cho đăng ký khi trang chạy trên HTTPS hợp lệ hoặc localhost."""
import base64, json, os, re, threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

ROOT = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.getenv("VAPID_KEY_FILE") or os.path.join(ROOT, "instance", "vapid_private.pem")
_lock, _vapid = threading.Lock(), [None]
_pool = ThreadPoolExecutor(4)

def vapid():
    with _lock:
        if _vapid[0] is None:
            from py_vapid import Vapid01
            if os.path.exists(KEY_FILE):
                v = Vapid01.from_file(KEY_FILE)
            else:
                v = Vapid01()
                v.generate_keys()
                os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
                v.save_key(KEY_FILE)
            _vapid[0] = v
    return _vapid[0]

def public_key():
    """Khóa công khai VAPID (base64url, điểm EC không nén) cho PushManager.subscribe ở trình duyệt."""
    from cryptography.hazmat.primitives import serialization
    raw = vapid().public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")

def subject():
    """Liên hệ của máy chủ gửi kèm thông báo (dịch vụ đẩy yêu cầu): VAPID_SUBJECT, hoặc email MAIL_FROM / SMTP_USER."""
    if os.getenv("VAPID_SUBJECT"):
        return os.getenv("VAPID_SUBJECT")
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", os.getenv("MAIL_FROM") or os.getenv("SMTP_USER") or "")
    return f"mailto:{m.group(0)}" if m else "https://github.com/Doanne204/bacsicaytrong"

def send(c, target, user_ids, content, link=""):
    """Đẩy một thông báo tới mọi thiết bị đã đăng ký của user_ids. c: kết nối CSDL đang dùng (đọc danh sách thiết bị);
    target: CSDL (đường dẫn / URL) để luồng nền mở kết nối riêng khi cần xóa thiết bị hỏng."""
    ids = list(user_ids)
    if not ids:
        return 0
    subs = c.execute(f"SELECT id, endpoint, p256dh, auth FROM push_subs WHERE user_id IN ({','.join('?' * len(ids))})", ids).fetchall()
    payload = json.dumps(dict(title="Bác sĩ cây trồng", body=content, url=(link or "/notifications").lstrip("#") or "/"), ensure_ascii=False)
    for s in subs:
        _pool.submit(_deliver, target, dict(s), payload)
    return len(subs)

def _deliver(target, s, payload):
    from pywebpush import WebPushException, webpush
    try:
        webpush(dict(endpoint=s["endpoint"], keys=dict(p256dh=s["p256dh"], auth=s["auth"])), payload,
                vapid_private_key=vapid(), vapid_claims={"sub": subject()}, ttl=24 * 3600, timeout=10)
    except WebPushException as e:
        code = getattr(e.response, "status_code", None)
        if code in (404, 410):  # thiết bị đã hủy đăng ký hoặc hết hạn
            from core import connect
            with closing(connect(target)) as c:
                c.execute("DELETE FROM push_subs WHERE id=?", (s["id"],))
                c.commit()
        else:
            print(f"[push] lỗi gửi thông báo ({code}):", str(e)[:200], flush=True)
    except Exception as e:  # mất mạng, dịch vụ đẩy quá tải: bỏ qua, thông báo trong app vẫn còn
        print("[push] lỗi gửi thông báo:", repr(e)[:200], flush=True)
