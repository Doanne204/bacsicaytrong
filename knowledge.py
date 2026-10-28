"""Cơ sở tri thức: 38 lớp PlantVillage -> tên tiếng Việt + hướng xử lý (dùng làm dữ liệu gốc cho AI)."""
import re

HEALTHY = "Lá khỏe mạnh. Duy trì tưới nước hợp lý, bón phân cân đối, vệ sinh vườn và kiểm tra lá định kỳ 5-7 ngày/lần."

# (tên lớp gốc trong dataset, id cây, tên cây, tên bệnh, hướng xử lý)
RAW = [
 ("Apple___Apple_scab","apple","Táo","Bệnh ghẻ táo","Tỉa và thu gom lá/quả bệnh đem tiêu hủy; tỉa cành cho thông thoáng; phun thuốc gốc đồng hoặc mancozeb theo nhãn từ lúc nhú lá."),
 ("Apple___Black_rot","apple","Táo","Bệnh thối đen","Cắt bỏ cành chết, quả khô mốc; vệ sinh vườn; phun thuốc trừ nấm captan hoặc thiophanate-methyl theo hướng dẫn."),
 ("Apple___Cedar_apple_rust","apple","Táo","Bệnh gỉ sắt","Loại bỏ cây ký chủ (loài bách) gần vườn; phun thuốc trừ nấm myclobutanil khi ra lá non."),
 ("Apple___healthy","apple","Táo","Khỏe mạnh",HEALTHY),
 ("Blueberry___healthy","blueberry","Việt quất","Khỏe mạnh",HEALTHY),
 ("Cherry_(including_sour)___Powdery_mildew","cherry","Anh đào","Bệnh phấn trắng","Tỉa cành tăng thông thoáng, tránh tưới lên lá; phun lưu huỳnh hoặc thuốc trừ nấm nhóm triazole theo nhãn."),
 ("Cherry_(including_sour)___healthy","cherry","Anh đào","Khỏe mạnh",HEALTHY),
 ("Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot","corn","Ngô","Bệnh đốm lá xám","Luân canh, vùi tàn dư cây vụ trước; chọn giống kháng; phun azoxystrobin hoặc propiconazole khi bệnh xuất hiện sớm."),
 ("Corn_(maize)___Common_rust_","corn","Ngô","Bệnh gỉ sắt","Trồng giống kháng, gieo đúng thời vụ; phun thuốc trừ nấm nhóm triazole khi gỉ sắt xuất hiện nhiều trước trỗ cờ."),
 ("Corn_(maize)___Northern_Leaf_Blight","corn","Ngô","Bệnh cháy lá lớn","Luân canh, xử lý tàn dư; giống kháng; phun thuốc trừ nấm (azoxystrobin, propiconazole) khi vết bệnh xuất hiện trên lá dưới."),
 ("Corn_(maize)___healthy","corn","Ngô","Khỏe mạnh",HEALTHY),
 ("Grape___Black_rot","grape","Nho","Bệnh thối đen","Cắt bỏ chùm quả, lá bệnh; giữ giàn thông thoáng; phun mancozeb hoặc myclobutanil từ giai đoạn nhú chồi."),
 ("Grape___Esca_(Black_Measles)","grape","Nho","Bệnh Esca (sởi đen)","Cắt tỉa phần thân bệnh vào mùa khô và sát trùng vết cắt; tiêu hủy cành bệnh; hiện chưa có thuốc đặc trị, cần phòng ngừa."),
 ("Grape___Leaf_blight_(Isariopsis_Leaf_Spot)","grape","Nho","Bệnh cháy lá (đốm lá)","Thu gom lá rụng, tỉa lá già; phun thuốc gốc đồng hoặc mancozeb theo nhãn; tránh ẩm kéo dài."),
 ("Grape___healthy","grape","Nho","Khỏe mạnh",HEALTHY),
 ("Orange___Haunglongbing_(Citrus_greening)","orange","Cam","Bệnh vàng lá gân xanh (Greening)","Nhổ bỏ cây nhiễm nặng, trồng cây giống sạch bệnh; phòng trừ rầy chổng cánh bằng thuốc đặc trị theo khuyến cáo; liên hệ cán bộ bảo vệ thực vật."),
 ("Peach___Bacterial_spot","peach","Đào","Bệnh đốm vi khuẩn","Chọn giống kháng, tỉa cành thông thoáng; phun thuốc gốc đồng vào đầu mùa; tránh tưới phun lên tán."),
 ("Peach___healthy","peach","Đào","Khỏe mạnh",HEALTHY),
 ("Pepper,_bell___Bacterial_spot","pepper","Ớt chuông","Bệnh đốm vi khuẩn","Dùng hạt giống sạch bệnh, luân canh; phun thuốc gốc đồng kết hợp mancozeb; tránh làm việc khi lá còn ướt."),
 ("Pepper,_bell___healthy","pepper","Ớt chuông","Khỏe mạnh",HEALTHY),
 ("Potato___Early_blight","potato","Khoai tây","Bệnh mốc sương sớm (đốm vòng)","Luân canh, bón cân đối đạm-kali; phun mancozeb hoặc chlorothalonil khi thấy vết bệnh đầu tiên."),
 ("Potato___Late_blight","potato","Khoai tây","Bệnh mốc sương (sương mai)","Bệnh lây rất nhanh khi ẩm mát: nhổ tiêu hủy cây bệnh, phun metalaxyl/mancozeb hoặc dimethomorph ngay, lặp lại 5-7 ngày."),
 ("Potato___healthy","potato","Khoai tây","Khỏe mạnh",HEALTHY),
 ("Raspberry___healthy","raspberry","Mâm xôi","Khỏe mạnh",HEALTHY),
 ("Soybean___healthy","soybean","Đậu nành","Khỏe mạnh",HEALTHY),
 ("Squash___Powdery_mildew","squash","Bí","Bệnh phấn trắng","Tỉa lá già, tăng thông thoáng; phun lưu huỳnh, dầu neem hoặc thuốc trừ nấm nhóm triazole theo nhãn."),
 ("Strawberry___Leaf_scorch","strawberry","Dâu tây","Bệnh cháy lá","Cắt bỏ lá bệnh, tránh tưới lên lá; tăng khoảng cách trồng; phun thuốc gốc đồng hoặc captan theo nhãn."),
 ("Strawberry___healthy","strawberry","Dâu tây","Khỏe mạnh",HEALTHY),
 ("Tomato___Bacterial_spot","tomato","Cà chua","Bệnh đốm vi khuẩn","Dùng giống sạch bệnh, luân canh; phun thuốc gốc đồng; tránh tưới phun mưa, không chạm cây khi ướt."),
 ("Tomato___Early_blight","tomato","Cà chua","Bệnh đốm vòng (mốc sương sớm)","Ngắt lá gốc bệnh, phủ gốc, luân canh; phun mancozeb hoặc chlorothalonil định kỳ 7-10 ngày."),
 ("Tomato___Late_blight","tomato","Cà chua","Bệnh mốc sương (sương mai)","Nhổ tiêu hủy cây bệnh nặng; phun metalaxyl, dimethomorph hoặc mancozeb ngay; giữ ruộng thoáng, tránh ẩm kéo dài."),
 ("Tomato___Leaf_Mold","tomato","Cà chua","Bệnh mốc lá","Giảm ẩm độ, thông gió nhà lưới; tỉa lá dưới; phun chlorothalonil hoặc thuốc gốc đồng theo nhãn."),
 ("Tomato___Septoria_leaf_spot","tomato","Cà chua","Bệnh đốm lá Septoria","Ngắt bỏ lá bệnh, phủ gốc chống bắn nước; phun chlorothalonil hoặc mancozeb; luân canh 2-3 năm."),
 ("Tomato___Spider_mites Two-spotted_spider_mite","tomato","Cà chua","Nhện đỏ hai chấm","Phun nước rửa mặt dưới lá, dùng dầu khoáng/xà phòng trừ sâu hoặc thuốc trừ nhện (abamectin) theo nhãn; giữ ẩm hợp lý, tránh khô nóng."),
 ("Tomato___Target_Spot","tomato","Cà chua","Bệnh đốm đích","Tỉa lá bệnh, tăng thông thoáng; phun azoxystrobin hoặc chlorothalonil theo nhãn; luân canh."),
 ("Tomato___Tomato_Yellow_Leaf_Curl_Virus","tomato","Cà chua","Virus xoăn vàng lá (TYLCV)","Không có thuốc chữa: nhổ cây bệnh, diệt bọ phấn trắng (môi giới) bằng bẫy vàng, lưới chắn côn trùng; dùng giống kháng."),
 ("Tomato___Tomato_mosaic_virus","tomato","Cà chua","Virus khảm lá (ToMV)","Không có thuốc chữa: nhổ tiêu hủy cây bệnh, khử trùng dụng cụ, rửa tay; dùng hạt giống sạch virus và giống kháng."),
 ("Tomato___healthy","tomato","Cà chua","Khỏe mạnh",HEALTHY),
]

def norm(s: str) -> str:
    # bỏ phần trong ngoặc để "Corn_(maize)___Common_rust_" khớp với "Corn___Common_rust" (2 cách đặt tên của PlantVillage)
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", s.lower()))

CLASSES = {norm(r[0]): dict(raw=r[0], plant_id=r[1], plant=r[2], disease=r[3], remedy=r[4], healthy=r[3] == "Khỏe mạnh") for r in RAW}
# Lớp ảnh nền (không có lá) trong bộ 39 lớp: không thuộc cây nào, dùng để phát hiện ảnh không phải lá
BACKGROUND = dict(raw="Background_without_leaves", plant_id="background", plant="Không phải lá cây", disease="Không nhận ra lá cây",
                  remedy="Hãy chụp cận cảnh một chiếc lá, đủ sáng, nền đơn giản.", healthy=False)
CLASSES[norm(BACKGROUND["raw"])] = BACKGROUND
CLASS_NAMES = sorted(r[0] for r in RAW)   # thứ tự alphabet, trùng với image_dataset_from_directory
PLANTS = {}
for r in RAW:
    PLANTS[r[1]] = r[2]

def _limit(plant_id: str) -> str:
    """Cây chỉ có 1 lớp trong dữ liệu -> mô hình không phân biệt được khỏe/bệnh, cần cảnh báo người dùng."""
    rows = [r for r in RAW if r[1] == plant_id]
    if len(rows) != 1:
        return ""
    plant, disease = rows[0][2].lower(), rows[0][3]
    if disease == "Khỏe mạnh":
        return f"Dữ liệu huấn luyện chỉ có lá {plant} khỏe mạnh, nên mô hình không phát hiện được bệnh trên cây này."
    return f"Dữ liệu huấn luyện chỉ có lá {plant} bị {disease[0].lower() + disease[1:]}, nên mô hình không phân biệt được với lá khỏe hay bệnh khác."

LIMITS = {p: _limit(p) for p in PLANTS}

def info(raw_class: str) -> dict:
    return CLASSES.get(norm(raw_class), dict(raw=raw_class, plant_id="?", plant="Không rõ", disease=raw_class, remedy="Chưa có dữ liệu xử lý.", healthy=False))
