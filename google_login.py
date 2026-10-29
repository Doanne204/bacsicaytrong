"""Đăng nhập / đăng ký bằng tài khoản Google (Google Identity Services). Trình duyệt hiện nút của Google và nhận một ID token (JWT do
Google ký); máy chủ gửi token cho Google kiểm tra (endpoint tokeninfo: chữ ký, hạn dùng) rồi tự kiểm tra thêm: token cấp cho đúng
GOOGLE_CLIENT_ID của app, do Google phát hành, email đã được Google xác minh. Không cần thư viện ngoài.
Cấu hình: GOOGLE_CLIENT_ID=<mã>.apps.googleusercontent.com trong .env (tạo ở Google Cloud Console, xem README)."""
import json, os, time, urllib.error, urllib.parse, urllib.request

TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
ISSUERS = ("accounts.google.com", "https://accounts.google.com")


class GoogleTokenError(ValueError):
    """Token Google không hợp lệ (sai ứng dụng, hết hạn, email chưa xác minh...)."""


def client_id():
    return (os.getenv("GOOGLE_CLIENT_ID") or "").strip() or None


def verify(id_token):
    """ID token -> dict(sub, email, name, picture). Ném GoogleTokenError nếu không hợp lệ, OSError nếu không kết nối được Google."""
    cid = client_id()
    if not cid:
        raise GoogleTokenError("Máy chủ chưa cấu hình đăng nhập Google")
    if not id_token or len(id_token) > 4096:
        raise GoogleTokenError("Thiếu mã đăng nhập Google")
    url = f"{TOKENINFO}?{urllib.parse.urlencode({'id_token': id_token})}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            info = json.load(r)
    except urllib.error.HTTPError as e:  # Google trả 400 khi chữ ký sai hoặc token hết hạn
        raise GoogleTokenError("Mã đăng nhập Google không hợp lệ hoặc đã hết hạn, hãy thử lại") from e
    if info.get("aud") != cid:
        raise GoogleTokenError("Mã đăng nhập Google không dành cho ứng dụng này")
    if info.get("iss") not in ISSUERS:
        raise GoogleTokenError("Mã đăng nhập không do Google phát hành")
    if int(info.get("exp") or 0) < time.time():
        raise GoogleTokenError("Mã đăng nhập Google đã hết hạn, hãy thử lại")
    if str(info.get("email_verified")).lower() != "true" or not info.get("email") or not info.get("sub"):
        raise GoogleTokenError("Email Google chưa được xác minh")
    return dict(sub=str(info["sub"]), email=info["email"].strip().lower(), name=(info.get("name") or "").strip(), picture=info.get("picture"))
