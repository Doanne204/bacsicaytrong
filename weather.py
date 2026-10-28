"""Cảnh báo sâu bệnh theo thời tiết: lấy dự báo 7 ngày từ Open-Meteo (miễn phí, không cần khóa), tính thống kê từng ngày
(nhiệt độ, ẩm độ, số giờ ẩm >= 90%, mưa, gió) rồi đối chiếu với điều kiện phát sinh của từng nhóm bệnh / sâu hại.
Ngưỡng lấy theo tài liệu bảo vệ thực vật: mốc sương 10-25°C ẩm kéo dài, phấn trắng ấm khô, nhện đỏ nắng nóng khô hạn..."""
import json, math, time, urllib.parse, urllib.request

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
TZ = "Asia/Ho_Chi_Minh"
CACHE_TTL = 3600  # dự báo đổi theo giờ; cùng ô 0.1° (~10 km) dùng chung
_cache = {}

def _get(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "BacSiCayTrong/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def fetch_forecast(lat, lon):
    """Dự báo thô của Open-Meteo: thời tiết hiện tại, 2 ngày đã qua + 7 ngày tới theo giờ và theo ngày (giờ địa phương Việt Nam)."""
    q = dict(latitude=round(lat, 3), longitude=round(lon, 3), timezone=TZ, past_days=2, forecast_days=7,
             current="temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m,is_day",
             hourly="temperature_2m,relative_humidity_2m,precipitation,precipitation_probability,weather_code,is_day",
             daily="weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,"
                   "sunshine_duration,uv_index_max,sunrise,sunset")
    return _get(f"{FORECAST_URL}?{urllib.parse.urlencode(q)}")

def geocode(name, count=6):
    """Tìm tọa độ theo tên địa danh (tỉnh, huyện, xã) bằng dịch vụ địa danh của Open-Meteo."""
    q = dict(name=name, count=count, language="vi", format="json")
    j = _get(f"{GEOCODE_URL}?{urllib.parse.urlencode(q)}")
    out = []
    for r in j.get("results") or []:
        parts = [r.get(k) for k in ("name", "admin2", "admin1") if r.get(k)]
        label = ", ".join(dict.fromkeys(parts))  # bỏ trùng (VD "Hà Nội, Hà Nội")
        if r.get("country_code") and r["country_code"] != "VN":
            label += f" ({r.get('country') or r['country_code']})"
        out.append(dict(name=label, lat=r["latitude"], lon=r["longitude"]))
    return out

def day_stats(raw):
    """Gộp dữ liệu theo giờ thành từng ngày: tmin/tmax/tmean, rh (ẩm độ trung bình), wet_hours (số giờ ẩm >= 90%), rain (mm), wind (km/h)."""
    h, d = raw.get("hourly") or {}, raw.get("daily") or {}
    days = {}
    for t, temp, rh, rain in zip(h.get("time", []), h.get("temperature_2m", []), h.get("relative_humidity_2m", []), h.get("precipitation", [])):
        s = days.setdefault(t[:10], dict(date=t[:10], temps=[], rhs=[], wet_hours=0, rain=0.0))
        if temp is not None:
            s["temps"].append(temp)
        if rh is not None:
            s["rhs"].append(rh)
            s["wet_hours"] += rh >= 90
        s["rain"] += rain or 0
    daily = {t: i for i, t in enumerate(d.get("time", []))}
    out = []
    for date, s in sorted(days.items()):
        if not s["temps"]:
            continue
        i = daily.get(date)
        pick = lambda k: (d.get(k) or [None] * (i + 1))[i] if i is not None else None
        out.append(dict(date=date, tmin=round(min(s["temps"]), 1), tmax=round(max(s["temps"]), 1), tmean=round(sum(s["temps"]) / len(s["temps"]), 1),
                        rh=round(sum(s["rhs"]) / len(s["rhs"])) if s["rhs"] else None, wet_hours=s["wet_hours"], rain=round(s["rain"], 1),
                        wind=pick("wind_speed_10m_max"), code=pick("weather_code"),
                        sun=round((pick("sunshine_duration") or 0) / 3600, 1),
                        rain_prob=pick("precipitation_probability_max"), uv=pick("uv_index_max"),
                        sunrise=(pick("sunrise") or "")[11:16] or None, sunset=(pick("sunset") or "")[11:16] or None))
    return out

def _rank(code):
    """Mức "nặng" của mã thời tiết WMO, để chọn thời tiết đại diện cho một buổi (có dông trong buổi thì cả buổi là dông)."""
    c = code or 0
    return 8 if c >= 95 else 7 if c in (71, 73, 75, 77, 85, 86) else 6 if 61 <= c <= 67 or 80 <= c <= 82 else 5 if 51 <= c <= 57 \
        else 4 if c in (45, 48) else c and min(c, 3)

def hours(raw):
    """Danh sách từng giờ: time 'YYYY-MM-DDTHH:MM', temp, rh, rain, rain_prob, code, is_day."""
    h = raw.get("hourly") or {}
    keys = [("temp", "temperature_2m"), ("rh", "relative_humidity_2m"), ("rain", "precipitation"), ("rain_prob", "precipitation_probability"),
            ("code", "weather_code"), ("is_day", "is_day")]
    return [dict(time=t, **{k: (h.get(src) or [None] * (i + 1))[i] for k, src in keys}) for i, t in enumerate(h.get("time", []))]

PARTS = [("sang", "Buổi sáng", 6, 11), ("chieu", "Buổi chiều", 12, 17), ("toi", "Buổi tối", 18, 23)]

def day_parts(hrs, date):
    """Sáng (6-11h) / chiều (12-17h) / tối (18-23h) của một ngày: nhiệt độ trung bình, thời tiết đại diện, tổng mưa, khả năng mưa cao nhất."""
    out = []
    for key, name, a, b in PARTS:
        hs = [x for x in hrs if x["time"][:10] == date and a <= int(x["time"][11:13]) <= b and x["temp"] is not None]
        if hs:
            out.append(dict(key=key, name=name, temp=round(sum(x["temp"] for x in hs) / len(hs), 1),
                            code=max((x["code"] for x in hs), key=_rank), rain=round(sum(x["rain"] or 0 for x in hs), 1),
                            rain_prob=max((x["rain_prob"] or 0 for x in hs)), is_day=key != "toi"))
    return out

def report(lat, lon):
    """Toàn bộ dữ liệu cho trang thời tiết (cache 1 giờ theo ô 0.1°): days (theo ngày, dùng cho cảnh báo), current (hiện tại),
    hourly (24 giờ tới), parts (sáng/chiều/tối hôm nay)."""
    key = (round(lat, 1), round(lon, 1))
    hit = _cache.get(key)
    if hit and hit[0] > time.time() - CACHE_TTL:
        return hit[1]
    raw = fetch_forecast(lat, lon)
    days = day_stats(raw)
    if not days:
        raise RuntimeError("Dịch vụ thời tiết không trả về dữ liệu")
    hrs = hours(raw)
    c = raw.get("current") or {}
    now = (c.get("time") or time.strftime("%Y-%m-%dT%H:%M"))[:13]  # giờ hiện tại theo giờ Việt Nam
    current = dict(time=c.get("time"), temp=c.get("temperature_2m"), feels=c.get("apparent_temperature"), rh=c.get("relative_humidity_2m"),
                   rain=c.get("precipitation"), code=c.get("weather_code"), wind=c.get("wind_speed_10m"), is_day=c.get("is_day")) if c else None
    rep = dict(days=days, current=current, hourly=[x for x in hrs if x["time"][:13] >= now][:24], parts=day_parts(hrs, now[:10]))
    _cache[key] = (time.time(), rep)
    return rep

# ---------- Quy tắc: điều kiện một ngày thuận lợi cho từng nhóm bệnh / sâu hại ----------
# (mã, tên, loại, điều kiện(ngày) -> bool, cây bị hại (id trong knowledge.PLANTS; [] = mọi cây), bệnh/sâu liên quan, lời khuyên)
RULES = [
    ("moc_suong", "Mốc sương (sương mai)", "benh",
     lambda s: 10 <= s["tmean"] <= 25 and (s["wet_hours"] >= 8 or s["rain"] >= 5),
     ["tomato", "potato"], ["Bệnh mốc sương (sương mai)"],
     "Mát và ẩm kéo dài là điều kiện bùng phát mốc sương: thăm cây mỗi ngày, ngắt lá có vết úng nước; phun phòng mancozeb/metalaxyl "
     "trước đợt mưa, không tưới lên lá vào chiều tối."),
    ("dom_vong", "Đốm vòng, cháy lá (Alternaria)", "benh",
     lambda s: 22 <= s["tmean"] <= 30 and (s["rh"] or 0) >= 75 and s["rain"] >= 1,
     ["tomato", "potato"], ["Bệnh đốm vòng (mốc sương sớm)", "Bệnh mốc sương sớm (đốm vòng)"],
     "Nóng ẩm xen mưa thuận lợi cho đốm vòng: tỉa lá gốc, phủ gốc chống bắn nước, bón cân đối đạm-kali; phun mancozeb hoặc "
     "chlorothalonil khi thấy vết bệnh đầu tiên."),
    ("dom_la", "Đốm lá, thán thư, cháy lá do nấm", "benh",
     lambda s: 20 <= s["tmean"] <= 30 and s["rain"] >= 2,
     ["tomato", "corn", "grape", "strawberry", "apple"],
     ["Bệnh đốm lá Septoria", "Bệnh đốm lá xám", "Bệnh cháy lá lớn", "Bệnh cháy lá (đốm lá)", "Bệnh cháy lá", "Bệnh ghẻ táo", "Bệnh đốm đích", "Bệnh thối đen"],
     "Mưa nhiều ngày làm bào tử nấm lan theo nước: thu gom lá bệnh, không làm việc trong vườn khi lá ướt; phun thuốc gốc đồng hoặc "
     "mancozeb ngay sau mưa tạnh."),
    ("dom_vi_khuan", "Đốm vi khuẩn", "benh",
     lambda s: 24 <= s["tmean"] <= 32 and s["rain"] >= 2 and (s["wind"] or 0) >= 20,
     ["tomato", "pepper", "peach"], ["Bệnh đốm vi khuẩn"],
     "Mưa kèm gió làm vi khuẩn bắn từ lá bệnh sang lá lành: không tưới phun mưa, không chạm cây khi ướt; phun thuốc gốc đồng phòng ngừa."),
    ("phan_trang", "Phấn trắng", "benh",
     lambda s: 20 <= s["tmean"] <= 28 and 55 <= (s["rh"] or 0) <= 80 and s["rain"] < 1 and s["sun"] >= 4,
     ["squash", "cherry", "grape"], ["Bệnh phấn trắng"],
     "Ấm, ẩm vừa phải và không mưa là lúc phấn trắng phát triển mạnh: tỉa lá già cho thông thoáng, tránh bón thừa đạm; phun lưu huỳnh "
     "hoặc thuốc nhóm triazole khi thấy đốm phấn trắng đầu tiên."),
    ("gi_sat", "Gỉ sắt", "benh",
     lambda s: 15 <= s["tmean"] <= 26 and (s["rh"] or 0) >= 80 and s["rain"] < 10,
     ["corn", "apple"], ["Bệnh gỉ sắt"],
     "Mát, ẩm, sương đêm nhiều thuận lợi cho gỉ sắt: kiểm tra mặt dưới lá, phun thuốc nhóm triazole khi gỉ sắt xuất hiện nhiều."),
    ("moc_la", "Mốc lá cà chua", "benh",
     lambda s: 20 <= s["tmean"] <= 26 and (s["rh"] or 0) >= 85,
     ["tomato"], ["Bệnh mốc lá"],
     "Ẩm độ trên 85% kéo dài: thông gió nhà lưới, tỉa lá dưới, giãn mật độ; phun chlorothalonil hoặc thuốc gốc đồng."),
    ("nhen_do", "Nhện đỏ, nhện hại", "sau",
     lambda s: s["tmax"] >= 31 and (s["rh"] or 100) < 65 and s["rain"] < 1,
     ["tomato", "orange", "strawberry", "pepper"], ["Nhện đỏ hai chấm"],
     "Nắng nóng, khô hạn làm nhện đỏ bùng phát: tưới đủ ẩm, phun nước rửa mặt dưới lá vào sáng sớm; mật độ cao mới dùng thuốc trừ nhện "
     "(abamectin) và luân phiên hoạt chất."),
    ("chich_hut", "Rầy, rệp, bọ phấn, bọ trĩ", "sau",
     lambda s: s["tmax"] >= 28 and s["rain"] < 1,
     [], ["Virus xoăn vàng lá (TYLCV)", "Bệnh vàng lá gân xanh (Greening)", "Virus khảm lá (ToMV)"],
     "Nắng nóng, ít mưa là lúc bọ phấn, bọ trĩ, rầy phát triển nhanh và truyền virus: treo bẫy dính vàng, soi mặt dưới lá và ngọn non "
     "5 ngày/lần, không bón thừa đạm; nhổ sớm cây có triệu chứng xoăn vàng."),
    ("sau_an_la", "Sâu ăn lá, sâu đục quả", "sau",
     lambda s: 26 <= s["tmean"] <= 32 and (s["rh"] or 0) >= 75 and s["rain"] < 20,
     [], [],
     "Ấm và ẩm thuận lợi cho bướm đẻ trứng: thăm đồng tìm ổ trứng và sâu non tuổi nhỏ, ngắt bỏ; đặt bẫy đèn, bẫy pheromone; "
     "ưu tiên thuốc sinh học (Bt, NPV) khi sâu còn nhỏ."),
    ("oc", "Ốc bươu vàng, ốc sên", "sau",
     lambda s: s["rain"] >= 15,
     [], [],
     "Mưa lớn, ruộng ngập là lúc ốc di chuyển và đẻ trứng: thu ốc và ổ trứng hồng trên thân cây, bờ ruộng; đặt lưới chắn ở cửa nước, "
     "giữ mực nước thấp sau khi sạ."),
    ("mua_gio", "Mưa to, gió mạnh", "thoi_tiet",
     lambda s: s["rain"] >= 30 or (s["wind"] or 0) >= 45,
     [], [],
     "Không phun thuốc trước và trong lúc mưa to (thuốc bị rửa trôi); khơi rãnh thoát nước, chằng chống cây, cắt bớt cành yếu; "
     "sau mưa tạnh kiểm tra lá và phun phòng nấm bệnh."),
    ("nang_nong", "Nắng nóng gay gắt", "thoi_tiet",
     lambda s: s["tmax"] >= 36,
     [], [],
     "Nhiệt độ trên 36°C làm cây héo, cháy lá và rụng hoa: tưới vào sáng sớm hoặc chiều mát, phủ gốc giữ ẩm, che lưới cho cây con; "
     "không phun thuốc lúc trưa nắng."),
]
LEVELS = {0: None, 1: "thap", 2: "vua", 3: "cao"}

def assess(days, my_plants=(), horizon=5):
    """Đối chiếu dự báo với từng quy tắc trong `horizon` ngày tới (kể từ hôm nay). Số ngày thuận lợi: 1 -> thấp, 2 -> vừa, >= 3 -> cao.
    `my_plants`: id cây người dùng đã tra cứu / đang theo dõi, để xếp cảnh báo liên quan lên trước."""
    today = time.strftime("%Y-%m-%d")
    coming = [s for s in days if s["date"] >= today][:horizon]
    out = []
    for key, name, kind, cond, plants, diseases, advice in RULES:
        hit = [s["date"] for s in coming if cond(s)]
        if not hit:
            continue
        level = LEVELS[min(3, len(hit))]
        mine = not plants or any(p in my_plants for p in plants)
        out.append(dict(key=key, name=name, kind=kind, level=level, days=hit, plants=plants, diseases=diseases, advice=advice,
                        mine=bool(my_plants) and mine))
    order = {"cao": 0, "vua": 1, "thap": 2}
    out.sort(key=lambda a: (order[a["level"]], not a["mine"]))  # mức cao trước; cùng mức thì cây của người dùng trước
    return out

def forecast(lat, lon):
    """Dự báo theo ngày (có cache 1 giờ theo ô 0.1°), dùng cho cảnh báo sâu bệnh."""
    return report(lat, lon)["days"]

def distance_km(lat1, lon1, lat2, lon2):
    """Khoảng cách đường chim bay (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))

# Mã thời tiết WMO -> mô tả ngắn tiếng Việt (để hiển thị)
WMO = {0: "Trời quang", 1: "Ít mây", 2: "Có mây", 3: "Nhiều mây", 45: "Sương mù", 48: "Sương muối", 51: "Mưa phùn nhẹ", 53: "Mưa phùn",
       55: "Mưa phùn dày", 56: "Mưa phùn lạnh", 57: "Mưa phùn lạnh", 61: "Mưa nhỏ", 63: "Mưa vừa", 65: "Mưa to", 66: "Mưa lạnh", 67: "Mưa lạnh",
       71: "Tuyết nhẹ", 73: "Tuyết", 75: "Tuyết dày", 77: "Hạt tuyết", 80: "Mưa rào nhẹ", 81: "Mưa rào", 82: "Mưa rào to", 85: "Mưa tuyết",
       86: "Mưa tuyết", 95: "Dông", 96: "Dông kèm mưa đá", 99: "Dông kèm mưa đá"}
