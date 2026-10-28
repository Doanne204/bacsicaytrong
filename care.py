"""Lịch chăm sóc gợi ý cho nhật ký điều trị: mỗi nhóm bệnh/sâu hại có nhịp kiểm tra, phun nhắc lại khác nhau (nấm phấn trắng phun
cách 7-10 ngày, mốc sương lây nhanh phải kiểm tra 2-3 ngày/lần, virus không có thuốc chữa nên nhổ cây và diệt côn trùng môi giới,
bệnh do môi trường không cần phun...). Nhận nhóm theo tên bệnh / tên lớp / hướng xử lý (tiếng Việt hoặc tiếng Anh) hoặc nhóm sâu hại
của INSECT204; tên thuốc trong lời nhắc lấy từ hướng xử lý của chính bệnh đó."""
import re, unicodedata

import pests


def fold(s):
    """Chữ thường, bỏ dấu tiếng Việt ('Bệnh phấn trắng' -> 'benh phan trang') để so khớp từ khóa."""
    s = unicodedata.normalize("NFD", (s or "").lower().replace("đ", "d"))
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn"))


def has(text, *words):
    return any(re.search(rf"(?<![a-z]){w}", text) for w in words)


# Hoạt chất / loại thuốc hay gặp trong hướng xử lý: (từ khóa đã bỏ dấu, tên hiển thị)
ACTIVES = [("luu huynh", "lưu huỳnh"), ("goc dong", "thuốc gốc đồng"), ("mancozeb", "mancozeb"), ("chlorothalonil", "chlorothalonil"),
           ("metalaxyl", "metalaxyl"), ("dimethomorph", "dimethomorph"), ("azoxystrobin", "azoxystrobin"), ("propiconazole", "propiconazole"),
           ("myclobutanil", "myclobutanil"), ("captan", "captan"), ("thiophanate", "thiophanate-methyl"), ("triazole", "thuốc nhóm triazole"),
           ("hexaconazole", "hexaconazole"), ("difenoconazole", "difenoconazole"), ("abamectin", "abamectin"), ("dau neem", "dầu neem"),
           ("dau khoang", "dầu khoáng"), ("trichoderma", "Trichoderma"), ("kasugamycin", "kasugamycin"), ("streptomycin", "streptomycin")]


def actives(remedy, n=2):
    """Tối đa n thuốc được nhắc trong hướng xử lý, theo thứ tự xuất hiện."""
    t = fold(remedy)
    found = sorted((t.find(k), name) for k, name in ACTIVES if k in t)
    return [name for _, name in found[:n]]


def spray(nth, remedy, default, extra=""):
    names = actives(remedy)
    return f"Phun lần {nth}: {' hoặc '.join(names) if names else default}{extra}"


def step(content, days, repeat_days=0, on=True):
    return dict(content=content, days=days, repeat_days=repeat_days, on=on)


# Sâu hại theo nhóm của pests.GROUPS: (tên lịch, ghi chú, các bước)
PEST_PLANS = {
    "chich_hut": ("Côn trùng chích hút", "Rầy, rệp, bọ phấn sinh sản rất nhanh: soi mặt dưới lá 5-7 ngày/lần, chỉ phun khi mật độ cao, giữ thiên địch.",
                  [step("Soi mặt dưới lá, ngọn non; xem bẫy dính vàng", 3, 5), step("Phun lần 2 nếu mật độ còn cao (ưu tiên dầu khoáng, nấm xanh)", 6, on=False),
                   step("Nhổ bỏ cây bị xoăn, khảm (côn trùng đã truyền virus)", 7, 7, on=False)]),
    "nhen": ("Nhện hại", "Trứng nhện nở sau 3-5 ngày và không chết với lần phun đầu: cần phun lần 2 để diệt lứa mới nở, phun kỹ mặt dưới lá.",
             [step("Soi mặt dưới lá, xem còn nhện, trứng", 3, 5), step("Phun lần 2 thuốc đặc trị nhện, diệt lứa vừa nở", 6),
              step("Tưới, phun nước rửa mặt dưới lá khi trời khô nóng", 1, 3, on=False)]),
    "sau_an_la": ("Sâu ăn lá", "Trị sâu non tuổi nhỏ là hiệu quả nhất: ngắt ổ trứng, bắt sâu, phun chế phẩm Bt chiều mát khi lứa mới nở.",
                  [step("Ngắt ổ trứng, bắt sâu non", 2, 3), step("Kiểm tra lứa sâu mới nở, phun Bt nếu mật độ cao", 7),
                   step("Đánh giá mức hại, cây đã ra lá mới chưa", 14, on=False)]),
    "duc_than": ("Sâu đục thân, cành, quả", "Sâu nằm bên trong nên phun ít tác dụng: cắt bỏ phần bị đục, theo dõi lỗ đục mới.",
                 [step("Cắt, tiêu hủy cành, quả bị đục", 1), step("Kiểm tra lỗ đục mới, mùn sâu đùn ra", 7, 7),
                  step("Vệ sinh tàn dư, cày lật đất sau thu hoạch", 30, on=False)]),
    "duc_la": ("Sâu, ruồi đục lá", "Ngắt lá bị đục và bắt ruồi trưởng thành bằng bẫy vàng; chỉ phun khi lứa sâu non mới nở.",
               [step("Ngắt bỏ lá, đọt bị đục", 2), step("Thay bẫy dính vàng, kiểm tra lứa mới", 7, 7)]),
    "ruoi_qua": ("Ruồi đục quả", "Ruồi đẻ trứng liên tục: nhặt quả rụng 2 ngày/lần và thay bả dẫn dụ mỗi tuần.",
                 [step("Nhặt, tiêu hủy quả rụng, quả bị đục", 2, 2), step("Thay bả, bẫy dẫn dụ ruồi", 7, 7), step("Bao quả còn non", 3, on=False)]),
    "bo_canh_cung": ("Bọ cánh cứng", "Bắt bọ lúc sáng sớm khi chúng chậm chạp; luân canh và che lưới cho rau.",
                     [step("Rung cây, bắt bọ vào chậu nước xà phòng lúc sáng sớm", 1, 3), step("Kiểm tra lại mật độ bọ", 7)]),
    "bo_xit": ("Bọ xít", "Bọ xít tập trung lúc sáng sớm: bắt bằng vợt, ngắt ổ trứng; theo dõi kỹ lúc trỗ, quả non.",
               [step("Bắt bọ xít, ngắt ổ trứng lúc sáng sớm", 1, 3), step("Theo dõi lúc trỗ bông, quả non", 7, 7)]),
    "chau_chau": ("Châu chấu", "Bắt khi châu chấu non chưa bay được; nếu thành đàn hãy báo cán bộ bảo vệ thực vật.",
                  [step("Bắt châu chấu non bằng vợt", 1, 3), step("Kiểm tra mật độ, báo cán bộ BVTV nếu thành đàn", 7)]),
    "dat": ("Sâu hại trong đất", "Sâu xám, dế cắn cây con ban đêm: bới bắt quanh gốc lúc sáng sớm, kiểm tra cây con mỗi 5 ngày.",
            [step("Bới bắt sâu quanh gốc cây bị cắn lúc sáng sớm", 1, 2), step("Kiểm tra cây con bị cắn mới, trồng dặm", 5, 5)]),
    "oc_sen": ("Ốc hại", "Ốc hoạt động lúc chiều tối, sáng sớm và sau mưa: nhặt ốc, thu ổ trứng 2 ngày/lần.",
               [step("Nhặt ốc, thu ổ trứng lúc chiều tối hoặc sáng sớm", 1, 2), step("Rải lại vôi, tro quanh luống sau mưa", 5, on=False)]),
    "thien_dich": ("Thiên địch", "Đây là côn trùng có ích: không cần phun thuốc, chỉ theo dõi để chắc sâu hại đang bị khống chế.",
                   [step("Thăm vườn, xem thiên địch có khống chế được sâu hại", 7, 7)]),
    "khac": ("Côn trùng khác", "Loài này ít gây hại trực tiếp: theo dõi thêm, chỉ xử lý khi cây bị hại rõ.",
             [step("Theo dõi xem cây có bị hại thêm", 3, 7)]),
}


def disease_kind(text):
    """Nhóm bệnh theo từ khóa (text đã fold). Thứ tự quan trọng: 'mốc sương sớm' là đốm vòng chứ không phải sương mai."""
    if has(text, "virus", "kham", "xoan", "mosaic", "curl", "greening", "huanglongbing", "haunglongbing", "vang la gan xanh", "vang lun", "lun xoan"):
        return "virus"
    if has(text, "nhen", "spider mite", "mite"):
        return "nhen"
    if has(text, "ray", "rep", "bo phan", "bo tri", "whitefly", "aphid", "thrip"):
        return "chich_hut"
    # Sâu hại do AI gọi tên trong luồng ảnh lá (không qua mô hình INSECT204)
    if has(text, "duc than", "duc vo", "duc canh", "duc qua", "duc goc", "borer"):
        return "duc_than"
    if has(text, "sau an la", "sau non", "sau xanh", "sau to", "sau keo", "sau cuon la", "sau ve bua", "caterpillar"):
        return "sau_an_la"
    if has(text, "oc sen", "oc buou", "snail", "slug"):
        return "oc_sen"
    if has(text, "bo xit", "stink bug"):
        return "bo_xit"
    if has(text, "thieu dam", "thieu kali", "thieu lan", "thieu magie", "thieu sat", "thieu canxi", "thieu vi luong", "thieu dinh duong",
           "thieu phan", "deficien"):
        return "dinh_duong"
    if has(text, "moi truong", "thieu nuoc", "ung nuoc", "ngap ung", "chay nang", "sun scorch", "sunburn", "ngo doc", "sinh ly", "thoi tiet",
           "nhiet do", "kho han", "tuoi qua", "bat loi", "physiolog", "abiotic"):
        return "moi_truong"
    if has(text, "thoi re", "thoi goc", "thoi than", "heo ru", "root rot", "chet nhanh"):
        return "thoi_re"
    if has(text, "vi khuan", "bacteria", "loet", "heo xanh", "chay bia la", "bac la"):
        return "vi_khuan"
    if has(text, "phan trang", "powdery"):
        return "phan_trang"
    if has(text, "gi sat", "rust"):
        return "gi_sat"
    if has(text, "suong mai", "moc suong", "late blight", "downy") and not has(text, "som", "early"):
        return "suong_mai"
    if has(text, "dom", "chay la", "thoi", "ghe", "moc", "nam", "than thu", "dao on", "kho van", "lem lep", "spot", "blight", "scab", "rot", "mold",
           "mildew", "anthracnose", "esca", "scorch", "blast"):
        return "nam"
    return "chung"


def disease_plan(kind, remedy):
    """(tên lịch, ghi chú, các bước) cho một nhóm bệnh; tên thuốc phun nhắc lại lấy từ hướng xử lý."""
    if kind == "virus":
        if has(fold(remedy), "khu trung dung cu", "rua tay"):  # virus khảm lây qua dụng cụ, tay người khi chạm cây
            return ("Bệnh virus, lây khi tiếp xúc", "Không có thuốc chữa: nhổ cây bệnh sớm, khử trùng dụng cụ và rửa tay để không mang virus sang cây khác.",
                    [step("Nhổ, tiêu hủy cây bệnh (không ủ phân, không để trong vườn)", 1),
                     step("Khử trùng kéo, dao; rửa tay trước khi chạm cây khác", 1, 7),
                     step("Soi các cây xung quanh tìm lá khảm, biến dạng mới", 7, 7)])
        vector = "rầy chổng cánh" if has(fold(remedy), "ray chong canh") else "bọ phấn, rầy, rệp"
        return ("Bệnh lây qua côn trùng, không có thuốc chữa", f"Không có thuốc chữa: nhổ cây bệnh sớm và diệt côn trùng truyền bệnh ({vector}), phun thuốc trừ bệnh không có tác dụng.",
                [step("Nhổ, tiêu hủy cây bệnh (không ủ phân, không để trong vườn)", 1),
                 step(f"Xem bẫy dính vàng, diệt {vector} môi giới", 3, 7),
                 step("Soi các cây xung quanh tìm lá xoăn, khảm, vàng mới", 7, 7)])
    if kind == "suong_mai":
        return ("Mốc sương, sương mai", "Lây rất nhanh khi trời ẩm mát: kiểm tra 2-3 ngày/lần, phun nhắc lại cách 5-7 ngày.",
                [step("Kiểm tra vết bệnh lan rộng, nhổ cây bị nặng", 2, 3), step(spray(2, remedy, "thuốc đặc trị mốc sương"), 5),
                 step(spray(3, remedy, "thuốc đặc trị mốc sương", " (nếu trời còn ẩm mát)"), 10, on=False)])
    if kind == "phan_trang":
        return ("Nấm phấn trắng", "Phấn trắng phát triển khi ngày khô, đêm ẩm: ngắt lá phủ phấn, phun cách 7-10 ngày, thường 2-3 lần.",
                [step("Ngắt lá phủ phấn trắng, kiểm tra lá non", 3), step(spray(2, remedy, "lưu huỳnh hoặc thuốc trừ nấm"), 7),
                 step(spray(3, remedy, "lưu huỳnh hoặc thuốc trừ nấm", " (nếu còn vết phấn mới)"), 14, on=False),
                 step("Tỉa cành, lá cho tán thông thoáng", 1, on=False)])
    if kind == "gi_sat":
        return ("Nấm gỉ sắt", "Gỉ sắt phát triển chậm hơn: soi mặt dưới lá mỗi tuần, phun nhắc lại cách 10-14 ngày.",
                [step("Soi mặt dưới lá tìm ổ bào tử màu gỉ mới", 4, 7), step(spray(2, remedy, "thuốc nhóm triazole"), 10),
                 step("Đánh giá kết quả, ngừng phun nếu không có ổ mới", 21, on=False)])
    if kind == "vi_khuan":
        return ("Bệnh do vi khuẩn", "Vi khuẩn lây qua nước bắn và dụng cụ: cắt bỏ phần bệnh khi cây khô, không tưới lên lá; thuốc trừ nấm thông thường không trị được.",
                [step("Cắt bỏ lá, cành bệnh khi cây khô ráo; khử trùng dụng cụ", 1),
                 step("Kiểm tra vết bệnh mới, nhất là sau mưa", 3, 5), step(spray(2, remedy, "thuốc gốc đồng"), 7),
                 step("Đánh giá kết quả điều trị", 14, on=False)])
    if kind == "thoi_re":
        return ("Thối rễ, thối gốc", "Thối rễ do đất úng: giảm tưới, làm thoát nước, tưới gốc thuốc trừ nấm hoặc Trichoderma.",
                [step("Kiểm tra độ ẩm đất, chỉ tưới khi đất mặt đã khô", 2, 3), step("Tưới gốc thuốc trừ nấm lần 2", 7),
                 step("Xem cây đã ra lá non, rễ mới chưa", 14, on=False)])
    if kind == "moi_truong":
        return ("Do điều kiện môi trường", "Không do nấm, vi khuẩn nên không cần phun thuốc: điều chỉnh tưới, nắng, phân rồi theo dõi lá mới (lá cũ đã hỏng không hồi phục).",
                [step("Kiểm tra độ ẩm đất trước khi tưới", 1, 2), step("Theo dõi lá non mới ra có còn bị không", 7),
                 step("Đánh giá cây sau khi điều chỉnh chăm sóc", 14, on=False)])
    if kind == "dinh_duong":
        return ("Thiếu dinh dưỡng", "Bón bổ sung theo hướng xử lý rồi theo dõi lá non mới ra: lá già đã vàng thường không xanh lại.",
                [step("Bón bổ sung phân theo hướng xử lý", 1), step("Theo dõi màu lá non mới ra", 7, 7),
                 step("Bón nhắc lại nếu lá non vẫn vàng", 14, on=False)])
    if kind == "nam" and has(fold(remedy), "chua co thuoc", "khong co thuoc"):  # VD Esca trên nho: chỉ cắt tỉa, sát trùng vết cắt
        return ("Bệnh nấm chưa có thuốc đặc trị", "Chưa có thuốc đặc trị: cắt bỏ phần bệnh, sát trùng vết cắt và theo dõi cành mới, không cần phun định kỳ.",
                [step("Cắt tỉa phần bệnh, sát trùng vết cắt, tiêu hủy cành bệnh", 3), step("Theo dõi cành, lá mới có triệu chứng", 14, 14)])
    if kind == "nam":
        return ("Bệnh nấm hại lá", "Bệnh nấm: ngắt lá bệnh, thu gom lá rụng, phun nhắc lại cách 7-10 ngày khi còn vết bệnh mới.",
                [step("Ngắt lá bệnh mới, thu gom lá rụng", 3), step(spray(2, remedy, "thuốc trừ nấm", " (nếu đã phun lần 1)"), 7),
                 step("Đánh giá kết quả, ngừng phun nếu không có vết mới", 14, on=False)])
    return ("Theo dõi chung", "Chưa rõ nhóm bệnh: kiểm tra lại cây sau vài ngày, có thể hỏi thêm trợ lý AI hoặc cán bộ khuyến nông.",
            [step("Kiểm tra lại cây, ngắt lá bệnh mới", 3), step("Đánh giá kết quả điều trị", 14, on=False)])


def plan(disease="", raw="", remedy="", healthy=False, pest_raw=None, pest=False):
    """Lịch gợi ý {kind, label, note, steps:[{content, days, repeat_days, on}]}.
    pest_raw: tên lớp INSECT204 khi kết quả là sâu hại (nhóm lấy từ pests.py); pest=True mà không có pest_raw: chưa xác định được loài."""
    if pest and not pest_raw:
        return dict(kind="sau_chung", label="Sâu hại chưa rõ loài", note="Chưa biết loài nên chưa nên phun thuốc: theo dõi mức hại và chụp lại con sâu rõ hơn để tra cứu.",
                    steps=[step("Thăm vườn, soi mặt dưới lá, ngọn non, xem mức hại", 2, 3), step("Chụp lại con sâu thật gần, rõ nét để tra cứu lại", 1)])
    if pest_raw:
        info = pests.info(pest_raw)
        kind = info["group"]
        label, note, steps = PEST_PLANS[kind]
        return dict(kind=kind, label=label, note=note, steps=steps)
    if healthy:
        return dict(kind="khoe", label="Cây khỏe", note="Cây đang khỏe: kiểm tra lá mỗi tuần để phát hiện sớm sâu bệnh.",
                    steps=[step("Kiểm tra lá định kỳ", 7, 7)])
    kind = disease_kind(fold(f"{disease} {(raw or '').replace('_', ' ')}"))
    if kind == "chung" and remedy:
        # Tên bệnh không rõ nhóm (thường do AI đặt): chỉ tin hướng xử lý ở các nhóm có dấu hiệu rõ, vì hướng xử lý nào cũng nhắc "nấm", "phun"
        guess = disease_kind(fold(remedy))
        kind = guess if guess in ("virus", "moi_truong", "dinh_duong", "thoi_re") else kind
    if kind in PEST_PLANS:
        label, note, steps = PEST_PLANS[kind]
    else:
        label, note, steps = disease_plan(kind, remedy)
    return dict(kind=kind, label=label, note=note, steps=steps)
