# Bác sĩ cây trồng: phát hiện sâu bệnh từ ảnh lá (PlantVillage + MobileNetV3Large, INSECT204 + YOLO11m + Gemini)

## Tính năng
- **Đăng ký / đăng nhập**: tên đăng nhập, email, số điện thoại (không trùng, kiểm tra định dạng di động Việt Nam), mật khẩu. Đăng nhập bằng tên, email hoặc SĐT.
- **Trang chủ**: bài viết cộng đồng, lối tắt quét lá, đăng bài, lịch sử, đánh giá, hỏi trợ lý AI; hồ sơ cá nhân và thông báo ở thanh trên.
- **Tra cứu**: chụp trực tiếp bằng camera hoặc chọn ảnh có sẵn; chọn loại cây hoặc để hệ thống tự nhận diện. Thứ tự xử lý:
  1. Mô hình MobileNetV3 dự đoán; đồng thời so vector đặc trưng của ảnh với tâm các lớp đã học (`models/class_centroids.npz`).
     Ảnh khác xa mọi lớp (VD lá lúa: mô hình vẫn "tự tin" 80% là ngô) hoặc độ tin cậy < 60% -> coi là chưa chắc chắn.
  2. Chưa chắc chắn -> so với các ảnh AI đã xác định trước đó (bộ nhớ); giống >= 88% thì dùng lại kết quả, không tốn lượt gọi AI.
     (Ngưỡng 88% / gợi ý 80% và ngưỡng "ảnh lạ" 0,65 đo lại cho mô hình bản 2; đổi mô hình thì đo lại, xem chú thích trong client/routes.py.)
  3. Không khớp bộ nhớ -> Gemini phân tích; ảnh AI đủ chắc chắn (>= 60%) được lưu vào `dataset_ai/<Lớp>/` (cùng cấu trúc PlantVillage),
     cây mới hiện trong danh sách chọn cây, và ảnh vào bộ nhớ để nhận lại ngay lần sau.
  4. AI lỗi/hết lượt -> báo "Chưa xác định" kèm lý do và các khả năng mô hình đưa ra (không đoán bừa); có nút "Phân tích lại bằng AI".
- **Nhận diện sâu hại** (mô hình thứ hai **YOLO11m-cls**, 204 loài côn trùng, nhện, ốc hại và thiên địch của bộ INSECT204): chọn
  "Sâu hại, côn trùng" khi tra cứu, hoặc để "Tự nhận diện": ảnh mà mô hình bệnh lá thấy lạ sẽ được thử bằng mô hình sâu hại (chỉ chuyển
  khi rất chắc: độ giống tâm loài >= 0,60 và độ tin cậy >= 90%, không thì nhờ AI). Kết quả có tên tiếng Việt, tên khoa học, nhóm, cây bị
  hại, hướng phòng trừ theo IPM; thiên địch (bọ rùa, bọ ngựa, bọ xít bắt mồi...) được đánh dấu "có ích, đừng phun".
  Ảnh khác xa các loài đã học (`models/pest_centroids.npz`, độ giống < 0,50) hoặc độ tin cậy dưới 70% -> "Chưa xác định được loài" kèm
  3 loài gần nhất. Mô hình chạy trong app bằng ONNX (`models/pest_model.onnx`, `onnxruntime`, CPU ~18 ms/ảnh), không cần PyTorch.
- **Đăng bài**: chữ + ảnh; Gemini kiểm duyệt cả chữ và ảnh. Vi phạm -> từ chối, báo lý do ngay và gửi thông báo; không chắc chắn -> chờ quản trị viên duyệt.
- **Thuốc nên dùng và nơi mua** (trang kết quả, bệnh lá và sâu hại; bấm mới tìm): Gemini có Google Search tìm sản phẩm đang bán ở Việt
  Nam (tên, hoạt chất, sinh học/hóa học, cách dùng, giá tham khảo, trang bán). Đường dẫn AI đưa ra được mở thử, chỉ giữ trang thật
  (hoặc trang cùng cửa hàng trong danh sách nguồn Google), ảnh lấy từ og:image của trang đó; mở trang ngoài có chặn địa chỉ nội bộ
  (`shopping.py`). Kết quả dùng chung cho cùng bệnh 7 ngày (`lookup_cache`), mỗi lần tìm mới tính một lượt AI.
  Dưới danh sách thuốc (và cuối trang Bản đồ sâu bệnh) là bản đồ Google Maps nhúng tìm sẵn "cửa hàng thuốc bảo vệ thực vật" quanh
  vị trí vườn: Google tự ghim cửa hàng, bấm ghim xem địa chỉ, giờ mở cửa, chỉ đường; không tốn lượt AI (trước đây Gemini + Google Maps
  tìm rồi viết danh sách, hay lỗi và tọa độ đổi từ địa chỉ bị lệch nên đã bỏ).
- **Bản đồ sâu bệnh** (`/map`): vườn của tôi, bán kính 5/10/30/60 km, ca bệnh 60 ngày qua (làm tròn ~1 km, không lộ danh tính),
  danh sách bệnh đang có quanh vườn, bản đồ Google Maps các cửa hàng thuốc BVTV gần vườn.
- **Tra cứu nhiều ảnh** (trang Tra cứu, ô "Ảnh thêm"): 1 ảnh bắt buộc + tối đa 2 ảnh thêm của cùng cây / cùng con sâu (lá bệnh khác,
  góc khác). Mỗi ảnh dự đoán riêng, ảnh không phải lá hoặc khác xa dữ liệu đã học bị loại, xác suất các ảnh còn lại lấy trung bình;
  các ảnh kết luận khác nhau thì ghi chú và nhờ AI xem lại; AI nhận cả 3 ảnh trong một lần gọi. Ảnh thêm lưu `<ảnh chính>-p2.jpg`,
  `-p3.jpg` (cùng quyền xem, cùng bị xóa), `details.photos` giữ kết quả từng ảnh; mức độ bệnh lấy trung bình các ảnh.
  Đo lợi ích trên tập test: `python eval_multiphoto.py` -> `results/multiphoto.json`.
- **Vết bệnh** (trang kết quả, nút Ảnh gốc / Vết bệnh / Cạnh nhau): tô hồng phần lá không còn xanh (nâu, vàng, đen, trắng), tìm theo màu,
  không dùng mô hình; chỉ cho lá có bệnh (không cho lá khỏe, sâu hại). Vẽ lúc tra cứu (`details.lesion_url`), kết quả cũ thì vẽ khi mở tab
  (`/api/diagnoses/<id>/lesion`). Trang kết quả đã bỏ Grad-CAM vì vùng mô hình chú ý thường không trùng vết bệnh (trên 56 ảnh lá bệnh
  test, điểm nóng nhất nằm trên vết bệnh 27% với lớp 7x7, 41% với lớp 14x14), người dùng dễ hiểu nhầm là bản đồ bệnh. Grad-CAM chỉ còn
  trong hình báo cáo: `python gradcam_examples.py` -> `results/gradcam_examples.png` (ca đúng) và `gradcam_errors.png` (ca sai: lớp đoán
  và lớp đúng), hiện trong trang quản trị "Đánh giá mô hình".
- **Mức độ bệnh**: ước lượng mức độ
  bệnh (% diện tích lá đổi màu, đúng phần tô hồng ở tab Vết bệnh) xếp nhẹ / trung bình / nặng kèm lời khuyên. Phiếu chẩn đoán in ra giấy hoặc
  lưu PDF, có mã QR mở lại kết quả. Đọc kết quả thành tiếng, hỏi chatbot bằng giọng nói (Web Speech API, Chrome).
- **Đăng ký / đăng nhập bằng Google** (`google_login.py`, nút Google ở trang Đăng ký và Đăng nhập, chỉ hiện khi có `GOOGLE_CLIENT_ID`):
  máy chủ kiểm tra ID token qua Google (đúng mã ứng dụng, chưa hết hạn, email đã xác minh). Email đã có tài khoản thì đăng nhập vào đó
  và gắn Google; chưa có thì tạo tài khoản mới (tên đăng nhập lấy từ email, chưa có SĐT, bổ sung trong hồ sơ; muốn đăng nhập bằng mật
  khẩu thì dùng Quên mật khẩu). Cấu hình: Google Cloud Console -> APIs & Services -> Credentials -> Create credentials -> OAuth client ID
  -> Web application; Authorized JavaScript origins thêm `http://localhost:5000` (và địa chỉ HTTPS nếu chạy cho máy khác, Google không
  nhận `http://<IP LAN>`); chép Client ID vào `.env`: `GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com`, khởi động lại máy chủ.
- **Tài khoản**: đăng ký phải xác thực email bằng mã 6 số (15 phút); quên mật khẩu qua email. Gửi mail bằng SMTP cấu hình trong `.env`
  (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `MAIL_FROM`; Gmail dùng mật khẩu ứng dụng, cổng 587). Chưa cấu hình SMTP thì mã in ra
  log và hiện ngay trên giao diện (chỉ để thử). Giới hạn tần suất: 10 lần đăng nhập sai / 15 phút, 10 tài khoản / giờ mỗi IP, 10 bình
  luận và 5 bài / 10 phút, `AI_DAILY_LIMIT` (mặc định 40) lượt AI mỗi người mỗi ngày (quản trị viên không giới hạn).
- **Nhật ký điều trị và nhắc việc** (`/journal`): mở nhật ký từ kết quả tra cứu (nút "Theo dõi điều trị") hoặc tự ghi cây/bệnh. Nhắc việc
  ban đầu gợi ý theo nhóm bệnh (`care.py`, `GET /api/care-plan`): nấm phấn trắng phun cách 7-10 ngày, mốc sương kiểm tra 2-3 ngày/lần và
  phun lại sau 5 ngày, gỉ sắt phun lại sau 10 ngày, vi khuẩn cắt bỏ phần bệnh và phun gốc đồng, virus nhổ cây và diệt côn trùng môi giới
  (không phun thuốc trừ bệnh), nhện phun lần 2 diệt lứa trứng mới nở, từng nhóm sâu hại INSECT204, bệnh do môi trường / thiếu dinh dưỡng
  (không phun); tên thuốc trong lời nhắc lấy từ hướng xử lý của chính bệnh đó. Ghi việc đã làm (phun thuốc, tỉa, tưới bón, kiểm tra, kèm ảnh) theo
  dòng thời gian; nhắc việc có hạn, lặp lại theo chu kỳ, đánh dấu "đã làm" thì tự ghi vào nhật ký. Đến hạn -> thông báo trong ứng dụng
  (kiểm tra mỗi khi mở app) và email nếu chạy `flask --app app remind` theo lịch (xem "Chạy thật"). Trang chủ có mục "Việc cần làm".
- **Thời tiết** (`/weather`): khung kiểu ứng dụng thời tiết với bầu trời động theo thời tiết hiện tại (nắng, mây trôi, mưa, mưa to,
  dông có chớp, sương mù, tuyết, trời đêm có sao, trăng; tắt hiệu ứng khi hệ điều hành bật "giảm chuyển động"): thẻ hiện tại (nhiệt độ,
  cảm giác như, độ ẩm, gió, UV, khả năng mưa, mặt trời mọc/lặn), hôm nay/ngày mai, 24 giờ tới, sáng/chiều/tối, 7 ngày. Xem thử từng
  hiệu ứng: `/weather?wx=61` (mưa), `wx=65` (mưa to), `wx=95` (dông), `wx=45` (sương mù), `wx=71` (tuyết), `wx=0&dem=1` (đêm).
- **Cảnh báo sâu bệnh theo thời tiết** (`/weather`): lưu vị trí vườn (GPS của điện thoại hoặc tìm tên tỉnh/huyện); máy chủ lấy dự báo 7 ngày
  của Open-Meteo (miễn phí, không cần khóa; `weather.py`) rồi đối chiếu 13 quy tắc (mốc sương: mát + ẩm >= 90% nhiều giờ; phấn trắng: ấm,
  khô; nhện đỏ: nắng nóng khô hạn; đốm vi khuẩn: mưa + gió; mưa to, nắng nóng...). Số ngày thuận lợi trong 5 ngày tới quyết định mức:
  1 = theo dõi, 2 = vừa, >= 3 = cao; cảnh báo liên quan đến cây người dùng đã tra cứu / đang theo dõi xếp trước. Kèm ca bệnh của bà con
  trong 30 km / 14 ngày và bản đồ ca bệnh 60 ngày (Leaflet + OpenStreetMap, tọa độ làm tròn ~1 km, không kèm danh tính; kết quả tra cứu
  được ghim theo vị trí đã lưu). Lệnh `remind` mỗi sáng gửi thông báo/email cho cảnh báo mức cao (mỗi người một lần/ngày).
- **Báo kết quả sai và duyệt nhãn** (trang kết quả, mục "Kết quả sai?"): người dùng chọn bệnh / loài đúng trong danh sách (bệnh lá của
  mô hình và AI đã học, lá khỏe của từng cây, 204 loài sâu hại) hoặc tự ghi tên cây, tên bệnh. Trang quản trị "Dữ liệu AI":
  - Chờ duyệt: ảnh Gemini gán nhãn được lưu vào `dataset_ai/` ở trạng thái chờ duyệt (bảng `ai_samples.status`; mẫu có từ trước khi có
    bước này cũng là chờ duyệt). Quản trị viên duyệt (từng ảnh hoặc cả trang), sửa nhãn (ảnh chuyển sang thư mục lớp mới, kết quả tra cứu
    gốc sửa theo) hoặc xóa.
  - Báo kết quả sai: chấp nhận nhãn người dùng chọn hoặc chọn nhãn khác -> sửa kết quả, mẫu AI của kết quả đó đổi nhãn và được duyệt;
    kết quả do mô hình đoán sai thì ảnh được thêm vào `dataset_ai/` làm mẫu đã duyệt (ảnh thực tế ngoài đồng cho lần huấn luyện sau).
    Từ chối kèm lý do. Người báo nhận thông báo kết quả.
  - Huấn luyện lại chỉ với ảnh đã duyệt: `flask --app app export-dataset dataset_ai_duyet` (chép ảnh đã duyệt theo lớp, xuất lại từ đầu
    mỗi lần) rồi `python train.py --data ... --extra dataset_ai_duyet`.
- **Thư viện sâu bệnh** (`/library`): xem không cần chụp ảnh đủ 38 lớp bệnh lá của mô hình (kể cả lá khỏe) và 204 loài sâu hại /
  thiên địch; bệnh AI học thêm chỉ hiện khi đã có ảnh được quản trị viên duyệt (ảnh người dùng gửi thử chưa duyệt không hiện ra).
  Tìm không dấu, lọc theo cây hoặc nhóm sâu; ảnh minh họa lấy ảnh đầu tiên của lớp trong `dataset/` (hoặc mẫu AI đã duyệt), thu nhỏ
  lưu ở `instance/library/` (`LEAF_DATASET_DIR`, `PEST_DATASET_DIR` nếu dataset để chỗ khác). Bấm một bệnh: cách xử lý, nút hỏi trợ lý AI
  (câu hỏi soạn sẵn qua `/chat?q=`).
- **Cài lên điện thoại (PWA) và thông báo đẩy**: service worker `frontend/public/sw.js` (Flask phục vụ ở `/sw.js`): có mạng thì luôn lấy
  bản mới, mất mạng vẫn mở được app và xem dữ liệu đã mở trước đó (lịch sử, kết quả, nhật ký, thư viện...), thanh trên báo "Đang ngoại
  tuyến"; đăng xuất thì xóa dữ liệu đã lưu trên máy. Hồ sơ -> "Ứng dụng trên điện thoại": nút Cài đặt (khi trình duyệt cho phép) và bật
  thông báo đẩy cho thiết bị (`push.py`, thư viện `pywebpush`): mọi thông báo trong app (nhắc việc, cảnh báo thời tiết của lệnh `remind`,
  duyệt bài, trả lời báo cáo, thông báo của quản trị viên) cũng được đẩy tới điện thoại / máy tính, kể cả khi không mở app. Khóa VAPID tự
  tạo ở `instance/vapid_private.pem` (hoặc `VAPID_KEY_FILE`; liên hệ gửi kèm: `VAPID_SUBJECT`, mặc định email `MAIL_FROM`). Cần HTTPS
  (điện thoại dùng `https://<IP>:5443`; chứng chỉ tự ký có thể bị trình duyệt từ chối đăng ký thông báo, khi đó cần tên miền có HTTPS thật);
  iPhone phải "Thêm vào MH chính" rồi mở từ đó mới bật được.
- **Lịch sử tra cứu**: nhóm theo ngày, có ảnh, lọc theo ngày.
- **Đánh giá**: chấm 1-5 sao cho kết quả tra cứu của mình; trang tổng hợp điểm trung bình, phân bố sao, đánh giá gần đây.
- **Chatbot**: theo từng kết quả tra cứu hoặc hỏi chung; giữ lịch sử, gợi ý câu hỏi, hiển thị nguồn trả lời (Gemini / Claude / ngoại tuyến).
  Gửi kèm ảnh (chụp, chọn, kéo thả hoặc dán Ctrl+V) để Gemini xem ảnh và nhận xét ngay trong cuộc trò chuyện; ảnh lưu ở
  `instance/uploads/chats/`, chỉ chủ cuộc trò chuyện xem được. Trang tra cứu cũng nhận ảnh kéo thả và dán.
- **Trang quản trị riêng** (`/admin`, VD http://localhost:5000/admin), tách khỏi giao diện người dùng: khung riêng (thanh bên trên máy tính,
  dải mục trên điện thoại) và màn hình đăng nhập riêng; tài khoản thường đăng nhập ở đây bị từ chối (`/api/admin/login`).
  Quản trị viên vẫn thấy lối vào "Trang quản trị" trong ứng dụng (thanh bên trái và Hồ sơ). Hai trang dùng chung phiên đăng nhập.
  - Tổng quan: số liệu, biểu đồ lượt tra cứu 14 ngày, bệnh gặp nhiều nhất, gửi thông báo cho mọi người.
  - Bài viết (duyệt/từ chối kèm lý do, tìm kiếm), bình luận (lọc bình luận AI chưa duyệt, xóa), đánh giá (lọc theo sao, xóa).
  - Người dùng: tìm kiếm, khóa/mở khóa, cấp/bỏ quyền quản trị, đặt lại mật khẩu (mật khẩu tạm hiện một lần), xóa tài khoản kèm dữ liệu.
  - Thống kê: tra cứu 12 tháng theo nguồn, bảng bệnh theo tháng, độ chính xác suy từ đánh giá sao (4-5 sao = đúng), lượt AI 30 ngày.
  - Đánh giá mô hình: ma trận nhầm lẫn, precision/recall/F1 từng lớp đọc từ `results/` (train.py, yolo/export_pest.py); tab "So sánh kiến trúc"
    đọc `results/compare/summary.csv` do `compare_models.py` ghi ra (xem "So sánh kiến trúc").
  - Dữ liệu AI: duyệt / sửa nhãn / xóa mẫu AI, xử lý báo kết quả sai của người dùng (xem "Báo kết quả sai và duyệt nhãn").
  - Khóa Gemini: thêm nhiều khóa (lưu mã hóa bằng khóa suy ra từ `SECRET_KEY`, chỉ hiện 4 ký tự đầu/cuối), kiểm tra, bật/tắt,
    đổi tên, xóa, mở lại khóa đang tạm hết lượt; sửa thứ tự model. Xoay vòng: mỗi lần gọi bắt đầu từ khóa kế tiếp; khóa hết hạn mức
    với một model thì thử khóa khác cùng model, mọi khóa đều hết mới xuống model sau; khóa sai bị bỏ qua 1 giờ.
    Khóa trong `.env` được chuyển vào đây ở lần chạy đầu. Đổi `SECRET_KEY` thì phải nhập lại các khóa.

## Cấu trúc
```
frontend/               Giao diện React + Vite + TypeScript + Tailwind CSS + shadcn/ui (Radix), build ra frontend/dist cho Flask phục vụ
  src/client/           Ứng dụng người dùng: trang giới thiệu, đăng nhập/đăng ký, trang chủ, tra cứu, kết quả, lịch sử, chat, đánh giá,
                        hồ sơ, bài viết (thanh tab dưới trên điện thoại, thanh bên trái trên máy tính, sáng/tối)
  src/admin/            Ứng dụng quản trị riêng (/admin): bảng dữ liệu có tìm kiếm/sắp xếp/phân trang, biểu đồ Recharts, hộp thoại xác nhận
  src/shared/           Thành phần shadcn/ui, token màu (globals.css), gọi API và kiểu dữ liệu, hook đăng nhập/giao diện sáng tối
  index.html, admin.html   Hai điểm vào, vite.config.ts build cả hai; lúc phát triển proxy /api sang Flask
client/routes.py        API người dùng: tài khoản, tra cứu, lịch sử, chat AI, đánh giá, bài viết, thông báo; trả index.html cho mọi đường dẫn giao diện
client/static/          manifest.json (PWA)
admin/routes.py         API /api/admin/*: duyệt bài, người dùng, bình luận, đánh giá, dữ liệu AI, khóa Gemini; /admin trả admin.html
shared/                 Tài nguyên tĩnh phục vụ ở /static/: img/ (logo, biểu tượng, intro/ ảnh giới thiệu)
core.py                 Phần dùng chung phía máy chủ: CSDL, khóa Gemini mã hóa, đăng nhập/phân quyền, thông báo, ảnh tải lên, bài viết
app.py                  Tạo ứng dụng Flask, gắn 2 blueprint client và admin, phục vụ /assets của bản build, lệnh make-admin / build-centroids
tools/node/             Node.js portable (không có trong git) dùng để build giao diện; hoặc cài Node.js LTS vào máy
```
- CSDL **PostgreSQL** (CSDL `bacsicaytrong`, cấu hình bằng `DATABASE_URL` trong `.env`; lần chạy đầu tự tạo CSDL và bảng).
  Không có `DATABASE_URL` thì dùng file SQLite `instance/app.db` (kiểm thử mặc định cũng dùng SQLite tạm). Câu SQL viết một lần,
  `core.py` (`PgConn`) đổi cú pháp khi chạy PostgreSQL. Ảnh tải lên ở `instance/uploads/` (không lưu trong CSDL).
- `model_service.py` nạp `plant_model.keras` (hoặc `best_plant_model.keras`) **cùng** `class_names.json`; thiếu thì chạy **chế độ DEMO**
- `ai_service.py` Gemini: chat, phân tích ảnh, kiểm duyệt bài; chat dự phòng Claude rồi ngoại tuyến
- `knowledge.py` 38 lớp -> tên tiếng Việt + hướng xử lý (+ lớp nền `Background_without_leaves`)
- `pests.py` 204 loài sâu hại INSECT204 -> tên tiếng Việt, nhóm (13 nhóm), cây bị hại, hướng phòng trừ theo nhóm
- `weather.py` gọi Open-Meteo (dự báo, tìm địa danh), gộp theo ngày, 13 quy tắc cảnh báo sâu bệnh theo thời tiết (cache 1 giờ)
- `train.py` huấn luyện mô hình bệnh lá (bản 2: học lớp phân loại 3 epoch, rồi tinh chỉnh toàn bộ MobileNetV3Large tối đa 15 epoch với
  LR khởi động + giảm cosine, AdamW, label smoothing 0.1, augmentation mạnh hơn, dừng sớm theo val_accuracy; ghi thêm
  `results/train_summary.json` gồm accuracy train/val/test). Muốn thử mà không đè mô hình đang dùng:
  `python train.py --data dataset/... --models_dir models/candidate --results_dir results/candidate` rồi chép sang `models/`, `results/`
  khi tốt hơn và chạy lại `flask --app app build-centroids dataset/...`. CPU i5-14600KF: khoảng 2-3 giờ; Colab T4: khoảng 30-40 phút.
  `yolo/train_yolo.py` + `yolo/export_pest.py` huấn luyện và đưa mô hình sâu hại YOLO11m-cls vào app (xem "Chạy", bước 3);
  `train_pests.py` là mô hình sâu hại cũ (MobileNetV3Large), chỉ giữ để so sánh; `tests/test_app.py` kiểm thử
- `compare_models.py` + `notebooks/so_sanh_kien_truc.ipynb` so sánh MobileNetV3Large / EfficientNet-B0 / ViT-B/16 (xem bên dưới)
- `evaluate_leaf.py` đánh giá lại mô hình bệnh lá đang dùng khi không còn số liệu lúc huấn luyện (chia tập giống train.py, đo cả
  train/val/test, ghi `results/overall_metrics.csv`, `classification_report.csv`, `confusion_matrix.png`, `class_metrics.png`, `leaf_eval.json`):
  `python evaluate_leaf.py` (~3 phút trên CPU). Trang quản trị ghi rõ đây là số liệu đánh giá lại.

## So sánh kiến trúc (MobileNetV3Large, EfficientNet-B0, ViT-B/16)
`compare_models.py` huấn luyện ba kiến trúc trên **cùng** dữ liệu, cùng cách chia 70/15/15 (seed 42, trùng với `train.py` khi có scikit-learn),
cùng augmentation và quy trình 2 giai đoạn (học lớp phân loại LR 1e-3 -> tinh chỉnh một phần backbone LR 1e-5, EarlyStopping theo val_loss),
rồi đánh giá trên cùng tập test: accuracy, top-3, macro-F1, ma trận nhầm lẫn, số tham số, dung lượng file, thời gian suy luận CPU (ms/ảnh)
và thời gian huấn luyện. ViT-B/16 lấy từ `keras-hub` (preset `vit_base_patch16_224_imagenet`, ~86M tham số, trọng số ~330 MB).
- Nên chạy trên Google Colab (GPU T4, 1,5-2,5 giờ cho toàn bộ dữ liệu): mở `notebooks/so_sanh_kien_truc.ipynb`, làm theo các ô
  (tải `compare_models.py` lên, giải nén dataset từ Drive hoặc Kaggle, chạy, tải `compare_results.zip` về).
- Chạy tại máy (cần `pip install scikit-learn matplotlib keras-hub`): `python compare_models.py --all --data dataset/Plant_leave_diseases_dataset_without_augmentation`;
  thử nhanh: `--arch efficientnetb0 --limit_per_class 60 --epochs 1 --fine_tune_epochs 0`.
- Kết quả: `results/compare/<kiến trúc>/` (overall_metrics.csv, classification_report.csv, confusion_matrix.png/csv, training_history.csv)
  và `results/compare/summary.csv`, `summary.png`. Giải nén từ Colab vào đúng chỗ này -> trang quản trị "Đánh giá mô hình" hiện tab "So sánh kiến trúc".

## Chạy
1. `pip install -r requirements.txt`
2. Tải dataset (https://data.mendeley.com/datasets/tywbtsjrjv/1), giải nén vào `dataset/` (39 thư mục lớp, gồm `Background_without_leaves`).
3. Huấn luyện: `python train.py --data dataset/Plant_leave_diseases_dataset_without_augmentation --epochs 8`
   (nên dùng GPU / Google Colab, sau đó chép thư mục `models/` về, nhớ chép cả `class_names.json`).
   Gộp ảnh AI đã được duyệt: `flask --app app export-dataset dataset_ai_duyet` rồi thêm `--extra dataset_ai_duyet` (lớp dưới `--min_images`
   ảnh, mặc định 20, sẽ bị bỏ qua).
   Sau khi có mô hình (hoặc mỗi lần huấn luyện lại), tính tâm các lớp để nhận ra ảnh cây lạ:
   `flask --app app build-centroids dataset/Plant_leave_diseases_dataset_without_augmentation`
   Mô hình sâu hại YOLO11m-cls (bộ INSECT204 giải nén vào `dataset/`, mỗi loài một thư mục; cần GPU NVIDIA và môi trường riêng
   `.venv-yolo` có PyTorch CUDA + `ultralytics` + `onnx`):
   - `python yolo/make_yolo_dataset.py`: chép ảnh theo phép chia train/val/test 6:1:3 trong `results/pest_split.csv` (đã bỏ ảnh trùng,
     như bài báo INSECT204) sang `yolo/insect204/`, thu nhỏ cạnh ngắn 256 px.
   - `.venv-yolo\Scripts\python.exe yolo\train_yolo.py --epochs 30`: YOLO11m-cls khởi đầu từ trọng số ImageNet, ảnh 224, AdamW,
     LR cosine, dừng sớm (RTX 3060: ~55 phút); ra `yolo/runs/yolo11m-cls/weights/best.pt`, `results/yolo/yolo11m-cls/metrics.json`.
   - `.venv-yolo\Scripts\python.exe yolo\export_pest.py`: xuất ONNX (xác suất + vector đặc trưng) ra `models/pest_model.onnx`,
     `pest_class_names.json`, tâm vector mỗi loài `pest_centroids.npz`, đánh giá lại bằng đúng đường xử lý của app ra
     `results/pest_metrics.json` (kèm bảng ngưỡng và độ quen của ảnh lá để chọn `PEST_*` trong `client/routes.py`); mô hình cũ sao lưu
     vào `backups/`.
   So sánh trên cùng 31.312 ảnh test (28-29/10/2026):

   | Mô hình | Accuracy | Top-5 | Macro-F1 | Tham số | CPU ms/ảnh |
   |---|---|---|---|---|---|
   | **YOLO11m-cls (đang dùng)** | **76,3%** | **92,6%** | **0,748** | 10,6 M | 18 |
   | YOLO11s-cls | 75,5% | 91,7% | 0,743 | 5,7 M | 9 |
   | YOLO11n-cls | 73,2% | 90,7% | 0,713 | 1,8 M | 5 |
   | MobileNetV3Large tinh chỉnh (`train_pests.py`, mô hình cũ) | 71,0% | 90,0% | 0,696 | 3,6 M | 79 |

   Đo tốc độ CPU: `yolo/bench_cpu.py`. Huấn luyện lại thì chạy lại `export_pest.py` và đo lại các ngưỡng `PEST_*`.
4. Tạo file `.env` (đã có trong `.gitignore`): `GEMINI_API_KEY=...` (lấy ở https://aistudio.google.com/apikey), `SECRET_KEY=chuoi-bi-mat`.
   Tuỳ chọn `GEMINI_MODEL=gemini-2.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite` (mặc định): model hết hạn mức (gói miễn phí
   gemini-2.5-flash chỉ 20 lượt/ngày) thì tự chuyển sang model kế tiếp.
   CSDL PostgreSQL (đã cài PostgreSQL, dịch vụ đang chạy): `DATABASE_URL=postgresql://postgres:<mật khẩu>@localhost:5432/bacsicaytrong`.
   Chuyển dữ liệu từ file SQLite cũ sang (chỉ chép vào CSDL chưa có tài khoản nào): `flask --app app import-sqlite instance/app.db`
5. Build giao diện (cần Node.js 22; nếu dùng bản portable trong `tools/node` thì thêm vào PATH trước):
   `cd frontend`, `npm install`, `npm run build` -> ra `frontend/dist/`. Lúc sửa giao diện: `npm run dev` rồi mở http://localhost:5173
   (Vite tự tải lại khi sửa, chuyển tiếp API sang Flask ở cổng 5000); xong thì `npm run build` để Flask phục vụ bản mới.
6. `flask --app app run` -> mở http://localhost:5000 (chưa build giao diện thì trang báo cách build)
7. Cấp quyền quản trị cho một tài khoản đã đăng ký: `flask --app app make-admin <tên đăng nhập>`, rồi mở http://localhost:5000/admin
8. Kiểm thử: `python -m unittest discover -s tests -v` (SQLite tạm). Chạy trên PostgreSQL: đặt thêm biến môi trường
   `TEST_DATABASE_URL=postgresql://postgres:<mật khẩu>@localhost:5432/bacsicaytrong_test` (mỗi test một schema riêng, tự xóa).

## Chạy thật và sao lưu
- Máy chủ WSGI đa luồng (thay `flask run`): `python serve.py` (cổng 5000) và `python serve.py --port 5443 --cert certs/lan.crt --key certs/lan.key`.
  Có tên miền thật thì đặt sau Nginx/Caddy để có HTTPS hợp lệ (Caddy tự xin chứng chỉ Let's Encrypt), khi đó không cần `--cert`.
- Sao lưu CSDL và ảnh: `python backup_db.py` -> `backups/<ngày-giờ>/` (PostgreSQL: `pg_dump` dạng `.dump`; SQLite: chép file), giữ 14 bản.
  Đặt lịch hằng ngày trên Windows (PowerShell quyền Administrator, sửa đường dẫn cho đúng):
  `schtasks /Create /SC DAILY /ST 02:00 /TN "BacSiCayTrong-Backup" /TR "D:\phathiensaubenh\.venv\Scripts\python.exe D:\phathiensaubenh\backup_db.py"`
  Khôi phục PostgreSQL: `pg_restore -h localhost -U postgres -d bacsicaytrong --clean --if-exists backups/<thư mục>/bacsicaytrong.dump`.
- Nhắc việc và cảnh báo thời tiết mỗi sáng (email cần SMTP trong `.env`; không có SMTP vẫn tạo thông báo trong ứng dụng):
  `schtasks /Create /SC DAILY /ST 06:30 /TN "BacSiCayTrong-Remind" /TR "cmd /c cd /d D:\phathiensaubenh && .venv\Scripts\python.exe -m flask --app app remind"`
  (thêm `--no-weather` nếu máy chủ không có Internet). Nhắc việc đến hạn vẫn hiện trong ứng dụng ngay khi người dùng mở app, không cần lệnh này.

## Dùng trên điện thoại qua mạng LAN
1. Đặt `SECRET_KEY` ngẫu nhiên trong `.env` (mở ra mạng thì không dùng khóa mặc định, người khác có thể giả mạo phiên đăng nhập).
2. Tạo chứng chỉ HTTPS tự ký cho IP hiện tại (chạy lại khi IP máy tính đổi): `python make_cert.py`
3. Chạy (máy tính dùng http://localhost:5000, điện thoại dùng https://<IP máy tính>:5443):
   - `flask --app app run --host 0.0.0.0 --port 5000`
   - `flask --app app run --host 0.0.0.0 --port 5443 --cert certs/lan.crt --key certs/lan.key`
4. Mở cổng trên tường lửa Windows (PowerShell chạy với quyền Administrator):
   `New-NetFirewallRule -DisplayName "Bac si cay trong (5000, 5443)" -Direction Inbound -Protocol TCP -LocalPort 5000,5443 -RemoteAddress LocalSubnet -Action Allow -Profile Private,Public`
5. Trên điện thoại (cùng Wi-Fi) mở `https://<IP>:5443`, chấp nhận cảnh báo chứng chỉ một lần (Nâng cao -> Tiếp tục).
   Trình duyệt chỉ cho mở camera trực tiếp trong trang khi dùng HTTPS; qua `http://<IP>:5000` nút Chụp ảnh mở ứng dụng camera của máy.

## Gợi ý cho báo cáo
Chia train/val/test 70/15/15 theo từng ảnh, stratified theo lớp (danh sách ảnh của từng tập lưu ở `results/split.csv`); báo cáo accuracy, precision/recall/F1 từng lớp, ma trận nhầm lẫn (train.py in sẵn).
Lưu ý: PlantVillage chụp nền đơn giản trong phòng lab, nên ảnh thực tế ngoài đồng có thể kém chính xác hơn -> nên nêu rõ hạn chế này và thử nghiệm thêm ảnh thực địa.
Với Cam, Việt quất, Mâm xôi, Đậu nành, Bí, dữ liệu chỉ có 1 lớp nên mô hình không phân biệt được lá khỏe/bệnh; app chuyển sang AI phân tích cho các cây này.
Nhãn do AI gán có thể sai (VD: nhầm mốc sương với đốm vòng), nên chỉ ảnh quản trị viên đã duyệt mới được xuất ra để huấn luyện lại (`export-dataset`).
