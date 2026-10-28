"""Trợ lý AI: gọi Gemini (nhiều khóa quản lý ở trang quản trị, xoay vòng khi hết hạn mức; chưa có khóa nào thì dùng
GEMINI_API_KEY trong .env), rồi tới Claude nếu có ANTHROPIC_API_KEY, nếu không (hoặc gọi lỗi) dùng chế độ ngoại tuyến.
Gemini còn dùng để phân tích ảnh cây mà mô hình chưa chắc chắn/chưa có (analyze_image) và kiểm duyệt bài đăng (moderate)."""
import base64, json, os, re, time, urllib.error, urllib.request

# finishReason của Gemini khi nội dung bị chặn vì vi phạm chính sách an toàn
BLOCKED = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT"}

class AIBlocked(Exception):
    """Gemini từ chối xử lý nội dung (vi phạm chính sách an toàn)."""

# SYSTEM = ("Bạn là chuyên gia bảo vệ thực vật hỗ trợ nông dân Việt Nam. Trả lời bằng tiếng Việt, rõ ràng, ngắn gọn, "
#           "ưu tiên biện pháp canh tác/sinh học trước, nêu thuốc BVTV theo hoạt chất kèm lưu ý đọc nhãn, thời gian cách ly và an toàn. "
#           "Nhắc kết quả AI nhận diện chỉ mang tính tham khảo; nếu bệnh nặng hãy liên hệ cán bộ khuyến nông. Không bịa thông tin. "
#           "Viết văn bản thuần, không dùng định dạng Markdown (không dùng **, #); liệt kê thì dùng gạch đầu dòng '-'.")
SYSTEM = (
    "Bạn là chuyên gia bảo vệ thực vật hỗ trợ nông dân Việt Nam. "
    "PHẠM VI (bắt buộc): CHỈ trả lời câu hỏi liên quan đến cây trồng, nông nghiệp. "
    "Nếu người dùng hỏi bất kỳ chủ đề nào khác, từ chối ngay bằng một câu ngắn gọn, hài hước, lầy lội và từ chối trả lời.\n"
    "PHONG CÁCH: Trả lời bằng tiếng Việt, siêu lầy lội, hài hước, thêm icon, ngắn gọn, súc tích; "
    "ưu tiên biện pháp canh tác/sinh học trước, nêu thuốc BVTV theo hoạt chất kèm lưu ý đọc nhãn, thời gian cách ly và an toàn. Không bịa thông tin.\n"
    "ĐỘ DÀI: Tối đa khoảng 60-80 từ. Câu đầu trả lời thẳng vào câu hỏi; sau đó nhiều nhất 3 gạch đầu dòng '-', "
    "mỗi dòng một câu ngắn. Không chào hỏi, không nhắc lại câu hỏi, không lặp ý, không mở bài/kết bài dài dòng. "
    "Chỉ khi người dùng xin giải thích chi tiết mới được dài hơn, nhưng không quá 150 từ. "
    "Lời nhắc kết quả AI chỉ để tham khảo / hỏi cán bộ khuyến nông: chỉ thêm khi bệnh nặng hoặc nói về thuốc, gói trong nửa câu cuối.\n"
    "ĐỊNH DẠNG: Văn bản thuần, không dùng tiêu đề '#'; in đậm 1-3 từ khóa quan trọng nhất (tên bệnh, tên hoạt chất) bằng **...**."
)

def _context(d):
    if not d:
        return "Người dùng chưa chọn kết quả chẩn đoán nào."
    details = json.loads(d["details"]) if d.get("details") else {}
    symptoms, p = details.get("symptoms"), details.get("pest")
    if details.get("kind") == "pest":
        who = (f"'{d['disease']}' (tên khoa học {p['sci']}, nhóm {p['group_name']}, "
               + (f"thiên địch có ích: {p['hosts']})" if p["beneficial"] else f"hại {p['hosts']})")) if p else "chưa xác định được loài"
        return f"Kết quả nhận diện sâu hại từ ảnh: {who}, độ tin cậy {d['confidence']*100:.0f}%. Gợi ý nền: {d['remedy']}"
    return (f"Kết quả chẩn đoán: cây {d['plant']}, tình trạng '{d['disease']}', độ tin cậy {d['confidence']*100:.0f}%. "
            + (f"Triệu chứng quan sát được: {symptoms} " if symptoms else "") + f"Gợi ý nền: {d['remedy']}")

def _call_claude(key, message, history, d):
    msgs = [{"role": h["role"], "content": h["content"]} for h in history[-10:]] + [{"role": "user", "content": message}]
    body = json.dumps({"model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"), "max_tokens": 450,
                       "system": SYSTEM + "\n" + _context(d), "messages": msgs}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", body, {
        "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text").strip()

# Thứ tự model thử lần lượt; mỗi model có hạn mức miễn phí riêng (VD gemini-2.5-flash chỉ 20 lượt/ngày)
DEFAULT_MODELS = "gemini-2.5-flash,gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite"
# Kiểm duyệt bài/bình luận cần nhanh hơn cần mạnh: bản lite trả lời ~1-3 giây, gemini-3.5-flash có lúc mất 40-60 giây
FAST_MODELS = "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash"
SLOW_COOLDOWN = 300  # model quá thời gian chờ thì bỏ qua 5 phút
_cooldown = {}  # (id khóa, model hoặc "*") -> thời điểm (time.time) được gọi lại sau khi hết hạn mức, quá chậm hoặc khóa lỗi
_store = None   # app gắn vào (app.KeyStore): danh sách khóa Gemini, danh sách model, ghi nhận lượt dùng
_turn = 0       # vị trí khóa bắt đầu của lần gọi kế tiếp (xoay vòng để chia đều lượt dùng)

class AIQuotaExceeded(Exception):
    """Mọi khóa/model Gemini đều đang hết hạn mức."""

def configure(store):
    """store có keys() -> [{id, label, key, cooldowns}] (None = chưa có khóa nào, dùng GEMINI_API_KEY trong .env),
    models(fast) -> chuỗi model hoặc None, report(id, model, kết quả, lỗi, hết hạn mức đến)."""
    global _store
    _store = store

def _keys():
    if _store:
        try:
            keys = _store.keys()
            if keys is not None:
                return keys
        except Exception as e:
            print("[ai] không đọc được danh sách khóa:", e, flush=True)
    env = os.getenv("GEMINI_API_KEY")
    return [dict(id="env", label=".env", key=env, cooldowns={})] if env else []

def _report(k, model, outcome, error=None, until=None):
    if _store:
        try:
            _store.report(k["id"], model, outcome, error, until)
        except Exception as e:
            print("[ai] không ghi được lượt dùng khóa:", e, flush=True)

def _models(fast=False):
    names = _store.models(fast) if _store else None
    names = names or ((os.getenv("GEMINI_FAST_MODEL") or FAST_MODELS) if fast else (os.getenv("GEMINI_MODEL") or DEFAULT_MODELS))
    return [m.strip() for m in names.split(",") if m.strip()]

def _retry_after(body):
    """Số giây Gemini yêu cầu chờ (RetryInfo.retryDelay, VD '77405s'); mặc định 60 giây."""
    try:
        for d in json.loads(body)["error"].get("details", []):
            if d.get("retryDelay"):
                return float(d["retryDelay"].rstrip("s"))
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return 60.0

def _post(req, timeout, retries=1):
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if attempt == retries or e.code < 500:
                raise
            time.sleep(1.5 * (attempt + 1))

def _bad_key(code, detail):
    return code in (401, 403) or "API_KEY_INVALID" in detail or "API key not valid" in detail or "API key expired" in detail

def _cooling(k, model, now):
    c = k.get("cooldowns") or {}
    return max(c.get(model, 0), c.get("*", 0), _cooldown.get((k["id"], model), 0), _cooldown.get((k["id"], "*"), 0)) > now

def _cool(k, model, until, error):
    """Tạm bỏ qua khóa k với model ("*" = mọi model) tới until. Khóa trong CSDL: lưu qua store để mọi tiến trình
    cùng thấy và quản trị viên mở lại được; khóa .env: nhớ trong tiến trình."""
    k.setdefault("cooldowns", {})[model] = until
    if not isinstance(k["id"], int):
        _cooldown[(k["id"], model)] = until
    _report(k, model, "quota" if error.startswith("Hết hạn mức") else "error", error, until)

def _gemini(contents, system, schema=None, max_tokens=2048, timeout=30, fast=False):
    """Gọi Gemini generateContent; có schema thì yêu cầu trả JSON và trả về dict. fast=True: dùng chuỗi model nhanh.
    Xoay vòng khóa: mỗi lần gọi bắt đầu từ khóa kế tiếp; khóa hết hạn mức (429) với một model thì thử khóa khác cùng model,
    mọi khóa đều hết mới xuống model kế tiếp. Khóa sai/bị chặn thì bỏ qua 1 giờ; model quá chậm thì bỏ qua 5 phút."""
    global _turn
    cfg = {"maxOutputTokens": max_tokens}  # model có "thinking" tính cả token suy nghĩ
    if schema:
        cfg.update(responseMimeType="application/json", responseSchema=schema)
    body = json.dumps({"system_instruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": cfg}).encode()
    keys = _keys()
    if not keys:
        raise RuntimeError("Chưa có khóa Gemini nào đang bật")
    start = _turn % len(keys)
    _turn += 1
    keys = keys[start:] + keys[:start]
    err, tried = None, False
    for model in _models(fast):
        for k in keys:
            now = time.time()
            if _cooling(k, model, now):
                continue
            tried = True
            req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", body, {
                "content-type": "application/json", "x-goog-api-key": k["key"]})
            try:
                data = _post(req, timeout)
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")
                if e.code == 429:
                    _cool(k, model, now + _retry_after(detail), f"Hết hạn mức {model}")
                elif e.code == 404:
                    _cool(k, model, now + 3600, f"Model {model} không còn dùng được")
                elif _bad_key(e.code, detail):
                    _cool(k, "*", now + 3600, f"Khóa không hợp lệ hoặc bị chặn (lỗi {e.code})")
                elif e.code >= 500:
                    _report(k, model, "error", f"Gemini quá tải (lỗi {e.code})")
                else:
                    raise
                print(f"[ai] khóa {k['label']} / {model}: lỗi {e.code}, thử khóa/model khác", flush=True)
                err = e
                continue
            except (TimeoutError, urllib.error.URLError) as e:
                if isinstance(e, TimeoutError) or isinstance(getattr(e, "reason", None), TimeoutError):
                    _cool(k, model, now + SLOW_COOLDOWN, f"{model} không phản hồi")
                else:
                    _report(k, model, "error", "Không kết nối được tới Gemini")
                print(f"[ai] khóa {k['label']} / {model} không phản hồi ({e}), thử khóa/model khác", flush=True)
                err = e
                continue
            _report(k, model, "ok")
            return _parse(data, schema)
    if not tried:
        raise AIQuotaExceeded("mọi khóa Gemini đang hết hạn mức")
    raise err

def _parse(data, schema):
    cand = (data.get("candidates") or [{}])[0]
    blocked = (data.get("promptFeedback") or {}).get("blockReason") or (cand.get("finishReason") in BLOCKED and cand["finishReason"])
    if blocked:
        raise AIBlocked(blocked)
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought")).strip()
    if not text or (schema and cand.get("finishReason") == "MAX_TOKENS"):
        raise ValueError(f"Gemini không trả lời đủ: {cand.get('finishReason') or data}")
    return json.loads(text) if schema else text

def _image_part(image_bytes):
    return {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image_bytes).decode()}}

def _call_gemini(message, history, d, image=None):
    contents = [{"role": "model" if h["role"] == "assistant" else "user", "parts": [{"text": h["content"]}]} for h in history[-10:]]
    parts = ([_image_part(image)] if image else []) + [{"text": message}]
    contents.append({"role": "user", "parts": parts})
    system = SYSTEM + "\n" + _context(d)
    if image:
        system += ("\nNgười dùng vừa gửi kèm một ảnh (thường là lá, cây, quả hoặc côn trùng). Trong câu đầu: điều thấy trong ảnh và bệnh/sâu hại "
                   "có khả năng nhất (thêm 1 khả năng dễ nhầm nếu có), rồi trả lời câu hỏi; vẫn giữ đúng giới hạn độ dài. "
                   "Ảnh không liên quan cây trồng thì nói rõ trong một câu.")
    return _gemini(contents, system, max_tokens=4096, timeout=60)

def vision_available():
    return bool(_keys())

def test_key(key, model):
    """Thử một khóa với một model (trang quản trị) -> (True, '') hoặc (False, lý do)."""
    body = json.dumps({"contents": [{"parts": [{"text": "Trả lời đúng một chữ: OK"}]}], "generationConfig": {"maxOutputTokens": 512}}).encode()
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", body, {
        "content-type": "application/json", "x-goog-api-key": key})
    try:
        _post(req, 30, retries=0)
        return True, ""
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        if e.code == 429:
            return False, f"Khóa đúng nhưng đang hết hạn mức với {model}"
        if _bad_key(e.code, detail):
            return False, "Khóa không hợp lệ hoặc bị chặn"
        return False, f"Gemini báo lỗi {e.code}"
    except OSError as e:
        return False, reason(e)

def reason(e):
    """Lý do AI lỗi, viết cho người dùng."""
    if isinstance(e, AIQuotaExceeded) or (isinstance(e, urllib.error.HTTPError) and e.code == 429):
        return "AI đã hết lượt dùng miễn phí (Gemini giới hạn số lần gọi), hãy thử lại sau"
    if isinstance(e, urllib.error.HTTPError):
        return f"AI báo lỗi {e.code}"
    if isinstance(e, TimeoutError):
        return "AI phản hồi quá lâu"
    if isinstance(e, OSError):
        return "không kết nối được tới AI"
    return "AI gặp lỗi khi phân tích"

# Không gửi danh sách lớp đã biết cho AI: thử nghiệm cho thấy AI bị "neo" vào lớp có sẵn (lúa chỉ có lớp đạo ôn -> ảnh đốm nâu
# cũng thành đạo ôn; bỏ danh sách thì nhận đúng đốm nâu). Việc ghép tên bệnh với lớp đã có do app làm (app.match_class).
VISION_SYSTEM = ("Bạn là chuyên gia bệnh hại cây trồng ở Việt Nam. Quan sát kỹ ảnh và tự chẩn đoán: mô tả triệu chứng nhìn thấy "
                 "(hình dạng, màu, kích thước, cách phân bố vết bệnh), cân nhắc các bệnh dễ nhầm rồi mới kết luận. "
                 "Chỉ kết luận theo dấu hiệu nhìn thấy trong ảnh; không chắc thì hạ confidence. Viết tiếng Việt, văn bản thuần.")
VISION_SCHEMA = {"type": "OBJECT", "properties": {
    "is_plant": {"type": "BOOLEAN", "description": "Ảnh có chụp cây trồng hoặc lá cây không"},
    "symptoms": {"type": "STRING", "description": "Triệu chứng nhìn thấy trong ảnh, 1-3 câu"},
    "plant_vi": {"type": "STRING", "description": "Tên cây tiếng Việt, VD: Xoài"},
    "plant_en": {"type": "STRING", "description": "Tên cây tiếng Anh thông dụng, VD: Mango"},
    "differential": {"type": "STRING", "description": "Các bệnh dễ nhầm đã cân nhắc và vì sao loại trừ, 1-2 câu"},
    "healthy": {"type": "BOOLEAN", "description": "Cây khỏe, không có bệnh hay sâu hại"},
    "disease_vi": {"type": "STRING", "description": "Tên bệnh/sâu hại tiếng Việt; để trống nếu khỏe"},
    "disease_en": {"type": "STRING", "description": "Tên bệnh/sâu hại tiếng Anh thông dụng, ngắn gọn, VD: Anthracnose; để trống nếu khỏe"},
    "confidence": {"type": "NUMBER", "description": "Mức chắc chắn từ 0 đến 1"},
    "remedy": {"type": "STRING", "description": "Hướng xử lý: biện pháp canh tác/sinh học trước, thuốc BVTV theo hoạt chất, nhắc đọc nhãn và thời gian cách ly; 2-4 câu"}},
    "required": ["is_plant", "symptoms", "plant_vi", "plant_en", "differential", "healthy", "disease_vi", "disease_en", "confidence", "remedy"]}
# Mặc định Gemini sinh thuộc tính theo thứ tự chữ cái; ép quan sát -> cân nhắc -> kết luận
VISION_SCHEMA["propertyOrdering"] = VISION_SCHEMA["required"]

def analyze_image(image_bytes, plant_hint=None, model_plant=None):
    """Gemini tự chẩn đoán ảnh lá cây (không đưa danh sách lớp có sẵn để tránh AI bị dẫn dắt).
    image_bytes: một ảnh, hoặc danh sách 2-3 ảnh cùng một cây (gửi chung một lần gọi, AI đưa ra một chẩn đoán).
    plant_hint: cây người dùng đã chọn. model_plant: loại cây mô hình nhận diện đoán (chỉ là gợi ý, chưa chắc chắn) khi người dùng
    để Tự nhận diện, giúp AI không trả lời "không xác định được loại cây" với ảnh cận cảnh một phần lá."""
    if not _keys():
        raise RuntimeError("Chưa có khóa Gemini nào đang bật")
    images = list(image_bytes) if isinstance(image_bytes, (list, tuple)) else [image_bytes]
    if plant_hint:
        prompt = f"Người dùng cho biết đây là cây {plant_hint}. "
    elif model_plant:
        prompt = (f"Người dùng chưa cho biết loại cây. Mô hình nhận diện của hệ thống cho rằng có thể là lá {model_plant} "
                  "(chưa chắc chắn, hãy tự kiểm tra hình dạng lá, mép lá, gân lá). ")
    else:
        prompt = "Người dùng chưa cho biết loại cây. "
    prompt += ("Hãy chẩn đoán ảnh này." if len(images) == 1 else
               f"Đây là {len(images)} ảnh chụp cùng một cây (các lá hoặc góc chụp khác nhau): xem hết các ảnh rồi đưa ra một chẩn đoán chung, "
               "triệu chứng tổng hợp từ các ảnh.")
    a = _gemini([{"role": "user", "parts": [_image_part(x) for x in images] + [{"text": prompt}]}], VISION_SYSTEM, VISION_SCHEMA,
                max_tokens=8192, timeout=60)
    out = {k: str(a.get(k) or "").strip() for k in ("plant_vi", "plant_en", "disease_vi", "disease_en", "differential", "symptoms", "remedy")}
    try:
        conf = float(a.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    conf = conf / 100 if conf > 1 else conf  # đôi khi model trả theo phần trăm
    return dict(out, is_plant=bool(a.get("is_plant")), healthy=bool(a.get("healthy")), confidence=min(max(conf, 0.0), 1.0))

MOD_SYSTEM = ("Bạn kiểm duyệt bài đăng cho cộng đồng nông dân Việt Nam trao đổi về trồng trọt, sâu bệnh và kinh nghiệm canh tác. "
              "Từ chối (reject) khi bài có: ngôn từ thô tục, xúc phạm, kỳ thị; bạo lực, máu me; nội dung hoặc hình ảnh khiêu dâm, nhạy cảm; "
              "lừa đảo, cờ bạc, quảng cáo spam; kích động chính trị; lộ thông tin cá nhân của người khác; "
              "hướng dẫn dùng thuốc BVTV bị cấm hoặc dùng hóa chất gây nguy hiểm; chữ và ảnh hoàn toàn không liên quan đến nông nghiệp. "
              "Duyệt (approve) khi bài phù hợp. Chọn review khi không chắc chắn để quản trị viên xem lại. "
              "feedback: lời nhắn lịch sự gửi người đăng, nêu rõ phần nào chưa phù hợp và cách sửa (để trống nếu duyệt). "
              "reason: ghi chú ngắn cho quản trị viên.")
MOD_COMMENT_SYSTEM = ("Bạn kiểm duyệt bình luận trong cộng đồng nông dân Việt Nam trao đổi về trồng trọt. "
                      "Bình luận giao tiếp thông thường (cảm ơn, hỏi thêm, chúc, đồng tình, góp ý) là phù hợp dù không nói về nông nghiệp. "
                      "Chỉ từ chối (reject) khi có: ngôn từ thô tục, xúc phạm, kỳ thị; bạo lực; nội dung khiêu dâm; lừa đảo, cờ bạc, "
                      "quảng cáo spam hoặc đường link rác; kích động chính trị; lộ thông tin cá nhân của người khác; "
                      "hướng dẫn dùng thuốc BVTV bị cấm. Không chắc chắn thì chọn review. "
                      "feedback: lời nhắn lịch sự gửi người viết, nêu rõ phần nào chưa phù hợp (để trống nếu duyệt). reason: ghi chú ngắn.")
MOD_SCHEMA = {"type": "OBJECT", "properties": {
    "decision": {"type": "STRING", "format": "enum", "enum": ["approve", "reject", "review"]},
    "reason": {"type": "STRING"}, "feedback": {"type": "STRING"}}, "required": ["decision", "reason", "feedback"]}

def moderate(text, image_bytes=None, kind="post"):
    """AI kiểm duyệt bài đăng (kind='post') hoặc bình luận (kind='comment')
    -> dict(decision='approve'|'reject'|'review', reason, feedback, source). Không có AI hoặc AI lỗi -> 'review'."""
    if not _keys():
        return dict(decision="review", reason="Chưa có khóa Gemini để AI kiểm duyệt", feedback="", source="none")
    label = "Nội dung bình luận:\n" if kind == "comment" else "Nội dung bài đăng:\n"
    parts = [{"text": label + (text or "(không có chữ, chỉ có ảnh)")}]
    if image_bytes:
        parts.insert(0, _image_part(image_bytes))
    try:
        m = _gemini([{"role": "user", "parts": parts}], MOD_COMMENT_SYSTEM if kind == "comment" else MOD_SYSTEM, MOD_SCHEMA,
                    max_tokens=8192, timeout=15 if kind == "comment" else 30, fast=True)
    except AIBlocked as e:
        return dict(decision="reject", reason=f"Gemini chặn nội dung ({e})",
                    feedback="Nội dung hoặc hình ảnh vi phạm tiêu chuẩn cộng đồng nên không thể đăng.", source="gemini")
    except Exception as e:
        print("[ai] lỗi kiểm duyệt, chuyển quản trị viên duyệt:", e, flush=True)
        return dict(decision="review", reason=f"Lỗi gọi AI: {e}"[:300], feedback="", source="error")
    decision = m.get("decision") if m.get("decision") in ("approve", "reject", "review") else "review"
    return dict(decision=decision, reason=str(m.get("reason") or "")[:500], feedback=str(m.get("feedback") or "")[:500], source="gemini")

def _offline(message, d):
    m = message.lower()
    if not d:
        return "Hãy tra cứu một chiếc lá trước để tôi có thể tư vấn cụ thể. (Chế độ ngoại tuyến: chưa cấu hình GEMINI_API_KEY hoặc ANTHROPIC_API_KEY)"
    if d.get("plant_id") == "pest" or d.get("plant") in ("Sâu hại", "Thiên địch"):
        return f"{d['plant']}: {d['disease']}. {d['remedy']}"
    if d.get("healthy"):
        return f"Cây {d['plant']} của bạn có vẻ khỏe mạnh. {d['remedy']}"
    if any(k in m for k in ["thuốc", "phun", "trị"]):
        return f"Về thuốc cho {d['disease']} ({d['plant']}): {d['remedy']} Luôn đọc kỹ nhãn, tuân thủ liều lượng và thời gian cách ly."
    if any(k in m for k in ["phòng", "ngừa", "tránh"]):
        return "Phòng bệnh: chọn giống kháng, luân canh, tỉa cành thông thoáng, tưới gốc thay vì tưới lên lá, vệ sinh tàn dư và dụng cụ."
    if any(k in m for k in ["lây", "lan"]):
        return "Nhiều bệnh lây qua bào tử theo gió/nước và dụng cụ. Hãy cách ly, loại bỏ lá bệnh, khử trùng dụng cụ và theo dõi cây lân cận."
    return f"Cây {d['plant']} có dấu hiệu {d['disease'][:1].lower() + d['disease'][1:]}. Gợi ý: {d['remedy']}"

def clean_reply(text):
    """Bỏ dấu ngoặc kép (thẳng, cong, « ») trong câu trả lời; dòng bắt đầu bằng "* " đổi thành gạch đầu dòng "- ".
    Giữ cặp dấu *...* / **...** để giao diện hiển thị phần bên trong thành chữ in đậm. Gom khoảng trắng thừa do việc bỏ dấu để lại."""
    text = re.sub(r"(?m)^(\s*)\*\s+", r"\1- ", text or "")
    text = re.sub(r'["“”„«»]', "", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()

def ask(message, history, diagnosis, image=None):
    """image: bytes JPEG người dùng gửi kèm trong chat (chỉ Gemini xem được ảnh; Claude/ngoại tuyến trả lời theo chữ)."""
    reply, src = _ask(message, history, diagnosis, image)
    return clean_reply(reply), src

def _ask(message, history, diagnosis, image=None):
    if _keys():
        try:
            return _call_gemini(message, history, diagnosis, image), "gemini"
        except Exception as e:
            print("[ai] lỗi gọi gemini, chuyển cách khác:", e, flush=True)
    note = "(Hiện không gọi được AI xem ảnh, nên tôi chỉ trả lời theo chữ.) " if image else ""
    key = os.getenv("ANTHROPIC_API_KEY")
    if key:
        try:
            return note + _call_claude(key, message, history, diagnosis), "claude"
        except Exception as e:
            print("[ai] lỗi gọi claude, chuyển cách khác:", e, flush=True)
    return note + _offline(message, diagnosis), "offline"
