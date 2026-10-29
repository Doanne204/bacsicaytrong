"""Gợi ý thuốc / chế phẩm cho một bệnh (Gemini có Google Search: sản phẩm đang bán ở Việt Nam, giá tham khảo, nơi bán).
Cửa hàng gần người dùng không tìm ở đây: giao diện nhúng bản đồ Google Maps tìm sẵn quanh vị trí vườn.

Chống bịa: AI chỉ được dùng thông tin tìm thấy trên web; đường dẫn AI đưa ra được mở thử, chỉ giữ trang thật (hoặc trang cùng tên miền trong
danh sách nguồn Google Search trả về); ảnh lấy từ thẻ og:image của chính trang đó. Mọi lần mở trang ngoài đều chặn địa chỉ nội bộ (SSRF)."""
import ipaddress, json, re, socket, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from html import unescape

import ai_service

UA = "BacSiCayTrong/1.0 (do an tot nghiep; lien he qua GitHub Doanne204/bacsicaytrong)"
MAX_PRODUCTS = 5


# ---------- Mở trang ngoài an toàn ----------
def _public_host(host):
    """Tên miền chỉ trỏ tới địa chỉ IP công khai (không phải mạng nội bộ, localhost, link-local...)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return bool(infos)


def _safe_url(url):
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return u.scheme in ("http", "https") and u.hostname and (u.port in (None, 80, 443)) and _public_host(u.hostname)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _open(url, max_bytes=600_000, timeout=6, hops=4):
    """GET url (tự theo chuyển hướng, kiểm tra từng bước) -> (địa chỉ cuối, content-type, nội dung) hoặc None."""
    opener = urllib.request.build_opener(_NoRedirect)
    for _ in range(hops):
        if not _safe_url(url):
            return None
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 " + UA, "Accept-Language": "vi,en;q=0.8"})
        try:
            with opener.open(req, timeout=timeout) as r:
                return r.geturl(), r.headers.get("content-type", ""), r.read(max_bytes)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("location"):
                url = urllib.parse.urljoin(url, e.headers["location"])
                continue
            return None
        except (OSError, ValueError):
            return None
    return None


def _redirect_target(url, timeout=6):
    """Địa chỉ thật sau một bước chuyển hướng (nguồn Google Search là link chuyển hướng của vertexaisearch)."""
    if not _safe_url(url):
        return None
    try:
        with urllib.request.build_opener(_NoRedirect).open(urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA}), timeout=timeout):
            return url
    except urllib.error.HTTPError as e:
        loc = e.headers.get("location")
        return urllib.parse.urljoin(url, loc) if loc else None
    except (OSError, ValueError):
        return None


def _meta(html, prop):
    m = re.search(rf'<meta[^>]+(?:property|name)=["\']{prop}["\'][^>]*content=["\']([^"\']+)', html, re.I) or \
        re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']{prop}["\']', html, re.I)
    return unescape(m.group(1)).strip() if m else None


def page_info(url):
    """Mở trang sản phẩm: (địa chỉ cuối, tiêu đề, ảnh og:image) hoặc None nếu không mở được / không phải trang HTML."""
    got = _open(url)
    if not got or "html" not in got[1].lower():
        return None
    final, _, body = got
    html = body.decode("utf-8", errors="replace")
    img = _meta(html, "og:image") or _meta(html, "twitter:image")
    img = urllib.parse.urljoin(final, img) if img else None
    title = _meta(html, "og:title") or (re.search(r"<title[^>]*>([^<]+)", html, re.I) or [None, None])[1]
    return final, unescape(title).strip() if title else None, img if img and img.startswith(("http://", "https://")) else None


def _domain(url):
    h = (urllib.parse.urlsplit(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


# ---------- Gợi ý thuốc bằng AI ----------
SYSTEM = ("Bạn là kỹ sư bảo vệ thực vật ở Việt Nam. Dùng Google Search tìm sản phẩm (thuốc bảo vệ thực vật, chế phẩm sinh học) ĐANG BÁN tại "
          "Việt Nam phù hợp để trị bệnh/sâu hại được hỏi. Chỉ dùng thông tin tìm thấy trên web, không bịa tên, giá hay đường dẫn. "
          "Chỉ chọn hoạt chất có trong Danh mục thuốc bảo vệ thực vật được phép sử dụng tại Việt Nam; ưu tiên chế phẩm sinh học, thuốc ít độc. "
          "Không đưa sản phẩm chứa hoạt chất đã bị cấm.")
PROMPT = """Bệnh/sâu hại: {disease} trên cây {plant}.
Hướng xử lý đã biết: {remedy}

Tìm tối đa {n} sản phẩm phù hợp nhất. Với mỗi sản phẩm ghi: tên thương mại, hoạt chất và hàm lượng, loại (sinh học hoặc hóa học), mô tả ngắn
công dụng với bệnh này, cách dùng tóm tắt theo nhãn, quy cách (VD chai 100 ml), giá bán tham khảo bằng đồng (số, không có thì null),
tên cửa hàng/trang bán và đường dẫn tới trang sản phẩm bạn đã thấy trên web.
Chỉ trả về một khối ```json``` duy nhất theo mẫu:
{{"products":[{{"name":"","active_ingredient":"","kind":"sinh_hoc|hoa_hoc","description":"","usage":"","pack":"","price_vnd":null,
"shop":"","url":""}}],"note":"lưu ý an toàn ngắn (1-2 câu)"}}"""


def _parse_json(text):
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S) or re.search(r"(\{.*\})", text, re.S)
    if not m:
        raise ValueError("AI không trả về danh sách sản phẩm")
    return json.loads(m.group(1))


def _price(v):
    try:
        p = int(float(str(v).replace(".", "").replace(",", "").replace("đ", "").strip()))
    except (TypeError, ValueError):
        return None
    return p if 1_000 <= p <= 50_000_000 else None


def find_products(disease, plant, remedy=""):
    """Gọi Gemini + Google Search -> dict(products=[...], sources=[{title, url}], note). Sản phẩm không có đường dẫn mở được vẫn giữ
    (để người dùng tìm theo tên) nhưng url=None. Lỗi AI/hết hạn mức thì ném ngoại lệ cho nơi gọi xử lý."""
    text, meta = ai_service._gemini([{"role": "user", "parts": [{"text": PROMPT.format(disease=disease, plant=plant or "chưa rõ",
                                                                                         remedy=remedy or "chưa có", n=MAX_PRODUCTS)}]}],
                                    SYSTEM, max_tokens=8192, timeout=90, tools=[{"google_search": {}}], meta=True)
    data = _parse_json(text)
    chunks = [c.get("web") or {} for c in meta.get("groundingChunks") or []][:10]
    with ThreadPoolExecutor(8) as ex:  # nguồn Google Search: link chuyển hướng -> địa chỉ trang thật
        real = list(ex.map(lambda c: _redirect_target(c.get("uri", "")), chunks))
    sources = [dict(title=c.get("title") or _domain(u), url=u) for c, u in zip(chunks, real) if u]
    raw = [p for p in (data.get("products") or []) if isinstance(p, dict) and str(p.get("name") or "").strip()][:MAX_PRODUCTS]

    def check(p):
        info = page_info(p["url"]) if str(p.get("url") or "").startswith(("http://", "https://")) else None
        if not info:  # đường dẫn AI đưa không mở được: thử nguồn Google Search cùng tên miền hoặc cùng tên cửa hàng
            want = _domain(p.get("url")) or ""
            shop = re.sub(r"\W", "", str(p.get("shop") or "").lower())
            for s in sources:
                if (want and _domain(s["url"]) == want) or (shop and shop in re.sub(r"\W", "", _domain(s["url"]) + s["title"].lower())):
                    info = page_info(s["url"])
                    if info:
                        break
        url, title, img = info or (None, None, None)
        kind = "sinh_hoc" if "sinh" in str(p.get("kind", "")).lower() else "hoa_hoc"
        return dict(name=str(p["name"]).strip()[:120], active_ingredient=str(p.get("active_ingredient") or "").strip()[:160], kind=kind,
                    description=str(p.get("description") or "").strip()[:400], usage=str(p.get("usage") or "").strip()[:300],
                    pack=str(p.get("pack") or "").strip()[:60], price_vnd=_price(p.get("price_vnd")),
                    shop=str(p.get("shop") or "").strip()[:80] or (_domain(url) if url else ""), url=url, page_title=title, image=img)
    with ThreadPoolExecutor(5) as ex:
        products = list(ex.map(check, raw))
    # sản phẩm có trang bán thật lên trước
    products.sort(key=lambda p: (p["url"] is None, p["kind"] != "sinh_hoc"))
    return dict(products=products, sources=sources[:8], note=str(data.get("note") or "").strip()[:300])
