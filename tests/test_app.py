import io, json, os, sqlite3, sys, tempfile, time, unittest, urllib.error, urllib.parse, uuid
from contextlib import closing
from unittest import mock
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# Để trống (không xóa) để .env không nạp giá trị thật khi chạy test: không gọi AI thật, không gửi email thật qua SMTP của người dùng
for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "SMTP_HOST", "SMTP_USER", "SMTP_PASS", "MAIL_FROM", "APP_URL", "GOOGLE_CLIENT_ID"):
    os.environ[k] = ""
os.environ["MODEL_PATH"] = os.path.join(ROOT, "khong_co_mo_hinh.keras")  # test chạy ở chế độ DEMO, không nạp TensorFlow
os.environ["PEST_MODEL_PATH"] = os.path.join(ROOT, "khong_co_mo_hinh_sau.onnx")  # mô hình sâu hại thay bằng FakePests
os.environ["VAPID_KEY_FILE"] = os.path.join(tempfile.mkdtemp(), "vapid.pem")  # không ghi khóa thông báo đẩy vào instance/ thật
import numpy as np
from PIL import Image
from werkzeug.security import generate_password_hash
import knowledge, ai_service, care, weather
from app import create_app
import core
from core import connect, create_pg_database
from model_service import pest_entry, thumb_embedding
import pests
import pywebpush
import push as push_mod

# Mặc định chạy trên file SQLite tạm. Đặt TEST_DATABASE_URL=postgresql://.../bacsicaytrong_test để chạy toàn bộ trên PostgreSQL
# (mỗi test một schema riêng, xóa khi xong).
PG_TEST = os.getenv("TEST_DATABASE_URL")
if PG_TEST:
    create_pg_database(PG_TEST)

def leaf(color=(40, 160, 60), size=(128, 128)):
    b = io.BytesIO(); Image.new("RGB", size, color).save(b, "JPEG"); b.seek(0); return b

def ai_answer(**kw):
    """Kết quả giả lập của ai_service.analyze_image (Gemini)."""
    a = dict(is_plant=True, plant_vi="Xoài", plant_en="Mango", healthy=False, disease_vi="Bệnh thán thư", disease_en="Anthracnose",
             differential="", confidence=0.9, symptoms="Đốm đen lõm trên lá", remedy="Tỉa cành, phun thuốc gốc đồng theo nhãn.")
    a.update(kw)
    return a

def gemini_response(obj):
    """Giả lập phản hồi HTTP của Gemini chứa obj (chuỗi hoặc JSON)."""
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    cm = mock.MagicMock()
    cm.__enter__.return_value = io.BytesIO(json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}).encode())
    return cm

class Base(unittest.TestCase):
    def setUp(self):
        core._hits.clear()  # giới hạn tần suất (theo IP) không kéo từ test này sang test khác
        self.tmp = tempfile.TemporaryDirectory()
        self.schemas = []
        self.app = create_app(self.config())
        self.c = self.app.test_client()
    def config(self, db="t.db"):
        target = os.path.join(self.tmp.name, db)
        if PG_TEST:
            schema = f"t_{id(self):x}_{db.replace('.', '_')}"
            if schema not in self.schemas:
                with closing(connect(PG_TEST)) as c:
                    c.executescript(f"DROP SCHEMA IF EXISTS {schema} CASCADE; CREATE SCHEMA {schema}")
                self.schemas.append(schema)
            target = f"{PG_TEST}?options=-csearch_path%3D{schema}"
        return {"TESTING": True, "DATABASE": target, "UPLOAD_DIR": os.path.join(self.tmp.name, "uploads"),
                "AI_DATASET_DIR": os.path.join(self.tmp.name, "dataset_ai")}
    def tearDown(self):
        if self.schemas:
            with closing(connect(PG_TEST)) as c:
                c.executescript("; ".join(f"DROP SCHEMA IF EXISTS {s} CASCADE" for s in self.schemas))
        self.tmp.cleanup()
    def signup(self, u="nguyenvan", e="a@b.vn", p="matkhau123", ph="0912345678", verify=True):
        r = self.c.post("/api/register", json={"username": u, "email": e, "password": p, "phone": ph})
        if verify and r.status_code == 201:  # chưa cấu hình SMTP: mã trả về trong phản hồi; xác thực bằng client riêng để không đổi phiên đang có
            self.app.test_client().post("/api/verify", json={"email": e, "code": r.get_json()["debug_code"]})
        return r
    def login(self, u="nguyenvan", p="matkhau123"):
        return self.c.post("/api/login", json={"username": u, "password": p})
    def authed(self): self.signup(); self.login()
    def as_user2(self):
        self.c.post("/api/logout"); self.signup("user2", "u2@b.vn", ph="0987654321"); self.login("user2")
    def make_admin(self, u="nguyenvan"):
        self.app.test_cli_runner().invoke(args=["make-admin", u])
    def predict(self, plant="tomato", img=None):
        return self.c.post("/api/predict", data={"plant": plant, "image": (img or leaf(), "l.jpg")}, content_type="multipart/form-data")
    def new_post(self, content="Lá cà chua bị đốm nâu, bà con tư vấn giúp", img=None):
        data = {"content": content}
        if img:
            data["image"] = (img, "p.jpg")
        return self.c.post("/api/posts", data=data, content_type="multipart/form-data")
    def get_status(self, url):
        return self.c.get(url, buffered=True).status_code  # buffered: đóng file ảnh ngay (Windows không xóa được file đang mở)
    def sql(self, q, *a):
        with closing(connect(self.app.config["DATABASE"])) as c: return [tuple(r) for r in c.execute(q, a).fetchall()]
    def run_sql(self, q, *a):
        with closing(connect(self.app.config["DATABASE"])) as c: c.execute(q, a); c.commit()
    def mark_sick(self, plant_id="tomato", plant="Cà chua", disease="Bệnh mốc sương (sương mai)"):
        """Chế độ DEMO không nhận ra bệnh: gán kết quả tra cứu thành một bệnh thật để thử bản đồ / cảnh báo."""
        self.run_sql("UPDATE diagnoses SET plant_id=?, plant=?, disease=?, healthy=0", plant_id, plant, disease)
    def dataset_files(self):
        d = self.app.config["AI_DATASET_DIR"]
        return sorted(os.path.relpath(os.path.join(r, f), d).replace(os.sep, "/").split("/")[0] for r, _, fs in os.walk(d) for f in fs)

class KnowledgeTests(unittest.TestCase):
    def test_38_classes_full_info(self):
        self.assertEqual(len(knowledge.CLASS_NAMES), 38)
        for c in knowledge.CLASS_NAMES:
            i = knowledge.info(c); self.assertNotEqual(i["plant_id"], "?"); self.assertTrue(i["remedy"])
    def test_14_plants(self): self.assertEqual(len(knowledge.PLANTS), 14)
    def test_dataset_names_without_parentheses(self):
        for c, p in [("Cherry___healthy", "cherry"), ("Cherry___Powdery_mildew", "cherry"), ("Corn___Common_rust", "corn"),
                     ("Corn___Cercospora_leaf_spot Gray_leaf_spot", "corn"), ("Background_without_leaves", "background")]:
            self.assertEqual(knowledge.info(c)["plant_id"], p, c)
    def test_single_class_plants_have_limit(self):
        self.assertEqual({p for p, n in knowledge.LIMITS.items() if n}, {"blueberry", "orange", "raspberry", "soybean", "squash"})

class ModelFilesTests(unittest.TestCase):
    path = os.path.join(ROOT, "models", "class_names.json")
    @unittest.skipUnless(os.path.exists(path), "chưa có models/class_names.json")
    def test_class_names_map_to_knowledge(self):
        with open(self.path, encoding="utf-8") as f: names = json.load(f)
        ids = [knowledge.info(c)["plant_id"] for c in names]
        self.assertNotIn("?", ids)
        self.assertTrue(set(knowledge.PLANTS) <= set(ids))

class PestModelTests(unittest.TestCase):
    """Mô hình sâu hại YOLO11m-cls chạy bằng onnxruntime (models/pest_model.onnx do yolo/export_pest.py xuất)."""
    def test_preprocess_like_ultralytics(self):
        from model_service import pest_preprocess
        b = io.BytesIO(); im = Image.new("RGB", (448, 300), (255, 0, 0)); im.paste((0, 0, 255), (0, 0, 40, 300)); im.save(b, "PNG")
        x = pest_preprocess(b.getvalue())
        self.assertEqual((x.shape, x.dtype), ((3, 224, 224), np.float32))
        self.assertAlmostEqual(float(x[0].mean()), 1.0, places=2)  # cạnh ngắn về 224 rồi cắt giữa: dải xanh bên trái bị cắt bỏ
        self.assertEqual(float(x[2].max()), 0.0)
    path = os.path.join(ROOT, "models", "pest_model.onnx")
    @unittest.skipUnless(os.path.exists(path), "chưa có models/pest_model.onnx")
    def test_real_model_predicts(self):
        import model_service
        with mock.patch.object(model_service, "PEST_MODEL_PATH", self.path):
            svc = model_service.PestService()
        self.assertTrue(svc.available)
        self.assertEqual(len(svc.class_names), 204)
        self.assertIsNotNone(svc.centroids)  # tâm vector khớp đúng file mô hình
        b = io.BytesIO(); Image.new("RGB", (300, 300), (40, 160, 60)).save(b, "JPEG")
        top, fam = svc.predict(b.getvalue())
        self.assertEqual(len(top), 3)
        self.assertAlmostEqual(sum(t["prob"] for t in svc.predict(b.getvalue(), top_k=204)[0]), 1.0, places=3)
        self.assertLess(fam, 0.9)  # ảnh màu trơn không giống loài nào

class EmailTemplateTests(unittest.TestCase):
    def test_code_and_list_mails(self):
        import emails
        subject, text, html = emails.code_mail("verify", "042917")
        self.assertIn("Mã xác thực", subject); self.assertIn("042917", text)
        self.assertIn("cid:" + emails.LOGO_CID, html); self.assertIn("042917", "".join(__import__("re").sub(r"<[^>]+>", "", html).split()))  # mã tách từng chữ số trong HTML
        subject, text, html = emails.reminders_mail([("Phun <thuốc> lần 2", "Luống cà chua")])
        self.assertIn("Phun &lt;thuốc&gt; lần 2", html); self.assertNotIn("<thuốc>", html)  # nội dung người dùng được thoát HTML
        self.assertIn("- Phun <thuốc> lần 2: Luống cà chua", text)
        with mock.patch.dict(os.environ, {"APP_URL": "http://192.168.1.5:5000/"}):
            self.assertIn('href="http://192.168.1.5:5000/weather"', emails.weather_mail([("Mốc sương", "Phun phòng")], "Vinh")[2])
    def test_send_mail_attaches_html_and_logo(self):
        import emails
        sent = []
        class FakeSMTP:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def starttls(self): pass
            def login(self, *a): pass
            def send_message(self, m): sent.append(m)
        with mock.patch.dict(os.environ, {"SMTP_HOST": "smtp.x", "SMTP_USER": "u@x.vn", "SMTP_PASS": "p"}), mock.patch("smtplib.SMTP", FakeSMTP):
            self.assertTrue(core.send_mail("a@b.vn", *emails.code_mail("reset", "123456")))
        types = [p.get_content_type() for p in sent[0].walk()]
        self.assertIn("text/plain", types); self.assertIn("text/html", types)
        self.assertEqual("image/png" in types, os.path.exists(emails.LOGO_PATH))

class SeverityTests(unittest.TestCase):
    def test_lesion_ratio_and_levels(self):
        from model_service import severity
        def leaf_with_spot(frac):  # lá xanh trên nền trắng, một mảng nâu chiếm frac diện tích lá
            im = Image.new("RGB", (200, 200), (255, 255, 255)); px = im.load()
            for x in range(20, 180):
                for y in range(20, 180): px[x, y] = (40, 150, 60)
            side = int((160 * 160 * frac) ** 0.5)
            for x in range(20, 20 + side):
                for y in range(20, 20 + side): px[x, y] = (120, 70, 30)
            b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()
        s = severity(leaf_with_spot(0.05)); self.assertEqual(s["level"], "nhe"); self.assertAlmostEqual(s["pct"], 0.05, delta=0.03)
        self.assertEqual(severity(leaf_with_spot(0.2))["level"], "vua"); self.assertEqual(severity(leaf_with_spot(0.5))["level"], "nang")
        self.assertIsNone(severity(leaf(color=(255, 255, 255)).getvalue()))  # toàn nền trắng, không có lá -> không ước lượng

class PestKnowledgeTests(unittest.TestCase):
    def test_204_classes_with_vietnamese_names(self):
        self.assertEqual(len(pests.PESTS), 204)
        for c in pests.PESTS:
            i = pests.info(c); self.assertTrue(i["name"] and i["remedy"] and i["group_name"], c)
        self.assertEqual((pests.info("Nilaparvata lugens")["name"], pests.info("Mantodea")["beneficial"]), ("Rầy nâu", True))
    path = os.path.join(ROOT, "models", "pest_class_names.json")
    @unittest.skipUnless(os.path.exists(path), "chưa có models/pest_class_names.json")
    def test_model_classes_have_knowledge(self):
        with open(self.path, encoding="utf-8") as f: names = json.load(f)
        self.assertEqual(sorted(names), sorted(pests.PESTS))

class FakePests:
    """Thay PestService trong test: trả về các loài và độ giống cho trước."""
    available = True
    def __init__(self, ranked, fam=0.9): self.ranked, self.fam = ranked, fam
    def predict(self, data, top_k=3): return [pest_entry(r, p) for r, p in self.ranked], self.fam
    @property
    def class_names(self): return [r for r, _ in self.ranked]
    dual = True

def spotted_leaf():
    """Lá xanh trên nền xám, một vết nâu ở góc trên bên trái."""
    px = np.array(Image.new("RGB", (224, 224), (128, 128, 128)))
    px[20:200, 20:200] = (40, 140, 40); px[30:80, 30:80] = (140, 90, 30)
    buf = io.BytesIO(); Image.fromarray(px).save(buf, "JPEG"); return buf.getvalue()

class LesionTests(Base):
    """Trang kết quả không còn Grad-CAM; lá bệnh có ảnh tô vết hại theo màu."""
    def test_cam_stats_for_report_figures(self):
        from model_service import cam_stats  # còn dùng cho hình báo cáo gradcam_examples.py
        cam = np.zeros((7, 7), np.float32); cam[1, 1] = 1; cam[1, 2] = 0.6
        s = cam_stats(cam); self.assertEqual(s["where"], "phía trên bên trái ảnh"); self.assertTrue(0 < s["focus"] < 0.2)
        self.assertEqual(cam_stats(np.zeros((7, 7)))["focus"], 0.0)
    def predict_as(self, raw, img=None):
        info = knowledge.info(raw); m = self.app.model
        with mock.patch.object(m, "predict", return_value=([dict(info, prob=0.97)], info, np.ones(4) / 2)), mock.patch.object(m, "familiarity", return_value=0.95):
            did = self.predict(info["plant_id"], img=img).get_json()["diagnosis_id"]
        return did, self.c.get(f"/api/diagnoses/{did}").get_json()
    def test_lesion_image_at_predict_time(self):
        from model_service import lesion_overlay
        self.assertTrue(lesion_overlay(spotted_leaf()).startswith(b"\xff\xd8"))
        self.assertIsNone(lesion_overlay(leaf(color=(255, 255, 255)).getvalue()))  # toàn nền, không có lá
        self.authed()
        did, d = self.predict_as("Tomato___Early_blight", io.BytesIO(spotted_leaf()))
        self.assertRegex(d["details"]["lesion_url"], r"^/uploads/scans/[0-9a-f]+-lesion\.jpg$"); self.assertTrue(d["details"]["lesion_available"])
        self.assertIn("severity", d["details"]); self.assertNotIn("cams", d["details"])
        url = d["details"]["lesion_url"]; self.assertEqual(self.get_status(url), 200)
        self.assertEqual(self.c.get(f"/api/diagnoses/{did}/lesion").get_json()["url"], url)
        self.as_user2(); self.assertEqual(self.get_status(url), 404); self.assertEqual(self.c.get(f"/api/diagnoses/{did}/lesion").status_code, 404)
        self.c.post("/api/logout"); self.login()
        path = os.path.join(self.app.config["UPLOAD_DIR"], url.removeprefix("/uploads/"))
        self.c.delete(f"/api/diagnoses/{did}"); self.assertFalse(os.path.exists(path))
    def test_no_lesion_for_healthy_leaf_or_pest(self):
        self.authed()
        _, d = self.predict_as("Tomato___healthy", io.BytesIO(spotted_leaf()))
        self.assertNotIn("lesion_url", d["details"]); self.assertFalse(d["details"]["lesion_available"])
        self.assertEqual(self.c.get(f"/api/diagnoses/{d['id']}/lesion").status_code, 400)
        self.app.pests = FakePests([("Nilaparvata lugens", 0.91)])
        d = self.c.get(f"/api/diagnoses/{self.predict('pest').get_json()['diagnosis_id']}").get_json()
        self.assertNotIn("lesion_url", d["details"]); self.assertFalse(d["details"]["lesion_available"]); self.assertNotIn("cam_url", d["details"])
    def test_old_result_gets_lesion_on_demand_and_cams_hidden(self):
        """Kết quả cũ: còn trường Grad-CAM (không gửi cho giao diện), chưa có ảnh vết bệnh thì vẽ khi mở tab."""
        self.authed(); did, _ = self.predict_as("Tomato___Early_blight", io.BytesIO(spotted_leaf()))
        det = json.loads(self.sql("select details from diagnoses where id=?", did)[0][0])
        os.remove(os.path.join(self.app.config["UPLOAD_DIR"], det.pop("lesion_url").removeprefix("/uploads/")))
        det.update(cam_url="/uploads/scans/x-cam.jpg", cams={"Tomato___Early_blight": {"url": "/uploads/scans/x-cam-0000beef.jpg"}})
        self.run_sql("UPDATE diagnoses SET details=? WHERE id=?", json.dumps(det), did)
        d = self.c.get(f"/api/diagnoses/{did}").get_json()
        self.assertNotIn("cams", d["details"]); self.assertNotIn("cam_url", d["details"]); self.assertTrue(d["details"]["lesion_available"])
        url = self.c.get(f"/api/diagnoses/{did}/lesion").get_json()["url"]
        self.assertEqual(self.get_status(url), 200); self.assertEqual(self.c.get(f"/api/diagnoses/{did}").get_json()["details"]["lesion_url"], url)

class GoogleLoginTests(Base):
    """Đăng ký / đăng nhập bằng Google: máy chủ kiểm tra ID token qua tokeninfo của Google (giả lập, không gọi mạng)."""
    CID = "123-abc.apps.googleusercontent.com"
    def google(self, sub="g-1", email="Nong.Dan.A@gmail.com", **over):
        info = {**dict(aud=self.CID, iss="https://accounts.google.com", exp=str(int(time.time()) + 600), email=email, email_verified="true",
                       sub=sub, name="Nông Dân A"), **over}
        with mock.patch.dict(os.environ, {"GOOGLE_CLIENT_ID": self.CID}),              mock.patch("google_login.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(info).encode())):
            return self.c.post("/api/auth/google", json={"credential": "x" * 50})
    def test_disabled_without_client_id(self):
        self.assertIsNone(self.c.get("/api/auth/config").get_json()["google_client_id"])
        self.assertEqual(self.c.post("/api/auth/google", json={"credential": "x"}).status_code, 503)
        with mock.patch.dict(os.environ, {"GOOGLE_CLIENT_ID": self.CID}):
            self.assertEqual(self.c.get("/api/auth/config").get_json()["google_client_id"], self.CID)
    def test_signup_then_signin(self):
        r = self.google(); j = r.get_json()
        self.assertEqual(r.status_code, 201); self.assertEqual((j["username"], j["created"], j["need_phone"]), ("nong.dan.a", True, True))
        me = self.c.get("/api/me").get_json(); self.assertEqual((me["email"], me["phone"]), ("nong.dan.a@gmail.com", None))
        self.assertEqual(self.sql("select verified, google_sub from users"), [(1, "g-1")])  # Google đã xác minh email
        self.c.post("/api/logout")
        r = self.google(); self.assertEqual(r.status_code, 200); self.assertFalse(r.get_json()["created"])
        self.assertEqual(len(self.sql("select id from users")), 1)
        self.c.post("/api/logout"); self.signup("nong.dan.a", "khac@b.vn", ph="0987654321")  # trùng tên -> thêm số
        self.c.post("/api/logout"); self.assertEqual(self.google(sub="g-2", email="nong.dan.a@yahoo.com").get_json()["username"], "nong.dan.a1")
    def test_links_existing_email_and_rejects_bad_tokens(self):
        self.signup(verify=False)  # tài khoản cũ cùng email, chưa xác thực
        r = self.google(email="a@b.vn"); self.assertEqual(r.status_code, 200)
        self.assertEqual((r.get_json()["username"], r.get_json()["need_phone"]), ("nguyenvan", False))
        self.assertEqual(self.sql("select verified, google_sub from users"), [(1, "g-1")])
        self.c.post("/api/logout")
        self.assertEqual(self.google(sub="g-9", email="a@b.vn").status_code, 409)  # email đã gắn tài khoản Google khác
        for bad in (dict(aud="app-khac"), dict(email_verified="false"), dict(iss="evil.com"), dict(exp="1")):
            self.assertEqual(self.google(sub="g-3", email="moi@gmail.com", **bad).status_code, 401, bad)
        self.assertEqual(self.c.get("/api/me").status_code, 401)
        self.run_sql("UPDATE users SET locked=1"); self.assertEqual(self.google(email="a@b.vn").status_code, 403)

class ShoppingTests(Base):
    """Gợi ý thuốc (AI + Google Search, kiểm tra trang bán thật) và cửa hàng gần (AI + Google Maps, tọa độ từ địa chỉ). Không gọi mạng thật."""
    AI_TEXT = '```json\n{"products":[{"name":"Anvil 5SC","active_ingredient":"Hexaconazole 50 g/l","kind":"hoa_hoc","description":"Trị nấm",' \
              '"usage":"20 ml/16 l","pack":"chai 1 l","price_vnd":"185.000","shop":"Nông Nghiệp Xanh","url":"https://shop.vn/anvil"},' \
              '{"name":"Trichoderma","kind":"sinh học","price_vnd":null,"url":"https://chet.vn/x","shop":"kho.vn"},{"name":""}],"note":"Đọc nhãn."}\n```'
    META = {"groundingChunks": [{"web": {"uri": "https://vertexaisearch.cloud.google.com/r/1", "title": "kho.vn"}}]}
    def test_url_safety(self):
        import shopping
        for u in ("http://127.0.0.1/", "http://localhost:5000/", "ftp://example.com/", "http://10.0.0.5/", "https://example.com:8443/"):
            self.assertFalse(shopping._safe_url(u), u)
    def test_find_products_checks_links(self):
        import shopping
        pages = {"https://shop.vn/anvil": ("https://shop.vn/anvil", "Anvil 5SC", "https://shop.vn/a.jpg"),
                 "https://kho.vn/tricho": ("https://kho.vn/tricho", "Trichoderma", None)}
        with mock.patch.object(ai_service, "_gemini", return_value=(self.AI_TEXT, self.META)) as g, \
             mock.patch.object(shopping, "_redirect_target", return_value="https://kho.vn/tricho"), \
             mock.patch.object(shopping, "page_info", side_effect=lambda u: pages.get(u)):
            r = shopping.find_products("Bệnh đốm vòng", "Cà chua", "phun mancozeb")
        self.assertEqual(g.call_args.kwargs["tools"], [{"google_search": {}}])
        self.assertEqual([p["name"] for p in r["products"]], ["Trichoderma", "Anvil 5SC"])  # có trang bán thật, sinh học lên trước
        tri, anvil = r["products"]
        self.assertEqual((anvil["price_vnd"], anvil["image"], anvil["kind"]), (185000, "https://shop.vn/a.jpg", "hoa_hoc"))
        self.assertEqual((tri["url"], tri["kind"]), ("https://kho.vn/tricho", "sinh_hoc"))  # link AI chết -> nguồn Google cùng cửa hàng
        self.assertEqual(r["sources"], [{"title": "kho.vn", "url": "https://kho.vn/tricho"}]); self.assertEqual(r["note"], "Đọc nhãn.")
    def test_products_api_and_cache(self):
        self.authed(); did = self.predict().get_json()["diagnosis_id"]
        self.run_sql("UPDATE diagnoses SET healthy=1")
        self.assertEqual(self.c.get(f"/api/diagnoses/{did}/products").status_code, 400)  # cây khỏe: không gợi ý thuốc
        self.mark_sick()
        self.assertEqual(self.c.get(f"/api/diagnoses/{did}/products").status_code, 503)  # chưa có khóa Gemini
        found = dict(products=[dict(name="Ridomil Gold", url=None)], sources=[], note="")
        with mock.patch.object(ai_service, "gemini_available", return_value=True), mock.patch("shopping.find_products", return_value=found) as f:
            r1 = self.c.get(f"/api/diagnoses/{did}/products").get_json()
            r2 = self.c.get(f"/api/diagnoses/{did}/products").get_json()
            self.assertEqual(f.call_count, 1)  # lần sau dùng kết quả đã lưu
            self.assertEqual(f.call_args[0][:2], ("Bệnh mốc sương (sương mai)", "Cà chua"))
            self.c.get(f"/api/diagnoses/{did}/products?refresh=1"); self.assertEqual(f.call_count, 2)
        self.assertEqual(r1["products"][0]["name"], "Ridomil Gold"); self.assertIn("cached_at", r2)
        self.as_user2(); self.assertEqual(self.c.get(f"/api/diagnoses/{did}/products").status_code, 404)

class MultiPhotoTests(Base):
    """Một lượt tra cứu 1-3 ảnh: mỗi ảnh dự đoán riêng, gộp bằng trung bình xác suất."""
    EB, SEP = "Tomato___Early_blight", "Tomato___Septoria_leaf_spot"
    def send(self, n, plant="tomato"):
        imgs = [(io.BytesIO(spotted_leaf()), f"{i}.jpg") for i in range(n)]
        return self.c.post("/api/predict", data={"plant": plant, "image": imgs}, content_type="multipart/form-data")
    def run_with(self, per_photo, fams=None, n=None):
        """per_photo: mỗi ảnh một danh sách (lớp, xác suất); fams: độ quen thuộc từng ảnh."""
        m, calls = self.app.model, iter(per_photo)
        def predict(data, plant_id=None, top_k=3):
            top = [dict(knowledge.info(r), prob=p) for r, p in next(calls)]
            return top, top[0], np.ones(4) / 2
        with mock.patch.object(m, "predict", side_effect=predict), mock.patch.object(m, "familiarity", side_effect=fams or [0.95] * len(per_photo)):
            r = self.send(n or len(per_photo))
        return r, self.c.get(f"/api/diagnoses/{r.get_json()['diagnosis_id']}").get_json() if r.status_code == 200 else None
    def test_two_agreeing_photos_are_averaged(self):
        self.authed()
        r, d = self.run_with([[(self.EB, 0.9), (self.SEP, 0.1)], [(self.EB, 0.7), (self.SEP, 0.3)]])
        self.assertEqual(r.status_code, 200); self.assertEqual(d["raw"], self.EB); self.assertAlmostEqual(d["confidence"], 0.8, places=5)
        self.assertIn("2 ảnh cùng cho một kết quả", " ".join(d["details"]["notes"]))
        ph = d["details"]["photos"]; self.assertEqual([p["used"] for p in ph], [True, True])
        self.assertRegex(ph[1]["url"], r"^/uploads/scans/[0-9a-f]+-p2\.jpg$"); self.assertRegex(ph[1]["lesion_url"], r"-p2-lesion\.jpg$")
        self.assertEqual(d["details"]["severity"]["photos"], 2)
        for u in (ph[1]["url"], ph[1]["lesion_url"]):
            self.assertEqual(self.get_status(u), 200)
        self.as_user2(); self.assertEqual(self.get_status(ph[1]["url"]), 404)  # ảnh thêm cùng quyền xem với ảnh chính
        self.c.post("/api/logout"); self.login()
        path = os.path.join(self.app.config["UPLOAD_DIR"], ph[1]["url"].removeprefix("/uploads/"))
        self.c.delete(f"/api/diagnoses/{d['id']}"); self.assertFalse(os.path.exists(path))
    def test_disagreeing_photos_are_flagged(self):
        self.authed()
        _, d = self.run_with([[(self.EB, 0.9), (self.SEP, 0.1)], [(self.SEP, 0.8), (self.EB, 0.2)]])
        notes = " ".join(d["details"]["notes"])
        self.assertIn("Các ảnh cho kết quả khác nhau", notes); self.assertIn("ảnh 2: bệnh đốm lá septoria 80%", notes)
        self.assertEqual(d["details"]["top"][0]["raw"], self.EB); self.assertAlmostEqual(d["details"]["top"][0]["prob"], 0.55, places=5)
    def test_unusable_photo_is_left_out(self):
        self.authed()
        _, d = self.run_with([[(self.EB, 0.9)], [(self.SEP, 0.99)]], fams=[0.95, 0.3])  # ảnh 2 khác xa dữ liệu đã học
        self.assertEqual(d["raw"], self.EB); self.assertAlmostEqual(d["confidence"], 0.9, places=5)
        self.assertEqual([p["used"] for p in d["details"]["photos"]], [True, False])
        self.assertIn("Ảnh 2 không giống lá bệnh mô hình đã học", " ".join(d["details"]["notes"]))
    def test_limits_and_ai_gets_all_photos(self):
        self.authed()
        self.assertEqual(self.send(4).status_code, 400)
        ai = mock.Mock(return_value=ai_answer(plant_vi="Xoài", plant_en="Mango", disease_vi="Thán thư", disease_en="Anthracnose"))
        with mock.patch.multiple(ai_service, vision_available=mock.Mock(return_value=True), analyze_image=ai):
            r = self.send(3, plant="other")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(ai.call_count, 1); self.assertEqual(len(ai.call_args[0][0]), 3)  # một lần gọi AI cho cả 3 ảnh
        with mock.patch.object(ai_service, "_keys", return_value=["k"]), mock.patch.object(ai_service, "_gemini", return_value={}) as g:
            ai_service.analyze_image([b"a", b"b"])
        parts = g.call_args[0][0][0]["parts"]
        self.assertEqual(sum("inline_data" in p for p in parts), 2); self.assertIn("2 ảnh chụp cùng một cây", parts[-1]["text"])
        self.assertEqual(len(self.sql("select id from ai_samples where diagnosis_id=?", r.get_json()["diagnosis_id"])), 3)

class PestTests(Base):
    BPH = [("Nilaparvata lugens", 0.91), ("Sogatella furcifera", 0.05)]
    def setUp(self):
        super().setUp(); self.authed()
    def test_hidden_without_model(self):
        self.assertNotIn("pest", [p["id"] for p in self.c.get("/api/plants").get_json()])
        self.assertEqual(self.predict("pest").status_code, 503)
    def test_pest_mode(self):
        self.app.pests = FakePests(self.BPH)
        self.assertEqual(self.c.get("/api/plants").get_json()[0]["id"], "pest")
        r = self.predict("pest").get_json()
        self.assertEqual((r["result"]["plant"], r["result"]["disease"], r["source"], r["demo"]), ("Sâu hại", "Rầy nâu", "model", False))
        self.assertTrue(r["result"]["remedy"].startswith("Cây bị hại: lúa"))
        d = self.c.get(f"/api/diagnoses/{r['diagnosis_id']}").get_json()
        self.assertEqual((d["details"]["kind"], d["details"]["pest"]["sci"], d["healthy"]), ("pest", "Nilaparvata lugens", False))
        self.assertEqual([t["disease"] for t in d["details"]["top"]], ["Rầy nâu", "Rầy lưng trắng"])
        self.assertEqual(self.c.post(f"/api/diagnoses/{d['id']}/reanalyze").status_code, 400)  # AI phân tích lại chỉ cho bệnh lá
        reply = self.c.post("/api/chat", json={"message": "phun thuốc gì?", "diagnosis_id": d["id"]}).get_json()["reply"]
        self.assertIn("Rầy nâu", reply)
    def test_beneficial_insect(self):
        self.app.pests = FakePests([("Mantodea", 0.8)])
        r = self.predict("pest").get_json()
        self.assertEqual((r["result"]["plant"], r["result"]["healthy"]), ("Thiên địch", True))
        self.assertIn("đừng phun thuốc", " ".join(r["notes"]))
    def test_unsure_not_reported_as_a_species(self):
        self.app.pests = FakePests(self.BPH, fam=0.3)  # ảnh khác xa mọi loài đã học
        r = self.predict("pest").get_json()
        self.assertEqual((r["result"]["plant_id"], r["result"]["disease"]), ("unknown", "Chưa xác định được loài"))
        self.assertEqual(r["top"][0]["disease"], "Rầy nâu")  # vẫn giữ để tham khảo
        self.app.pests = FakePests([("Nilaparvata lugens", 0.55)])  # độ tin cậy dưới PEST_MIN_PROB (0.70)
        r = self.predict("pest").get_json()
        self.assertEqual(r["result"]["plant_id"], "unknown"); self.assertIn("Độ tin cậy thấp", " ".join(r["notes"]))
        self.app.pests = FakePests([("Nilaparvata lugens", 0.75)])  # đủ để kết luận khi đã chọn "Sâu hại"
        self.assertEqual(self.predict("pest").get_json()["result"]["disease"], "Rầy nâu")
        with mock.patch.object(self.app.model, "familiarity", return_value=0.3):  # Tự nhận diện chặt hơn: 0.75 chưa đủ
            self.assertNotEqual(self.predict("auto").get_json()["result"]["plant_id"], "pest")
        self.app.pests = FakePests(self.BPH, fam=0.55)  # đủ quen khi đã chọn "Sâu hại", chưa đủ để Tự nhận diện chuyển sang sâu hại
        self.assertEqual(self.predict("pest").get_json()["result"]["disease"], "Rầy nâu")
        with mock.patch.object(self.app.model, "familiarity", return_value=0.3):
            self.assertNotEqual(self.predict("auto").get_json()["result"]["plant_id"], "pest")
    def test_auto_switches_to_pest_when_not_a_known_leaf(self):
        self.app.pests = FakePests(self.BPH)
        with mock.patch.object(self.app.model, "familiarity", return_value=0.3):
            r = self.predict("auto").get_json()
        self.assertEqual(r["result"]["disease"], "Rầy nâu"); self.assertIn("sâu hại", r["notes"][0])
        self.app.pests = FakePests(self.BPH, fam=0.3)  # cũng không giống sâu hại -> giữ luồng bệnh lá (AI / chưa xác định)
        with mock.patch.object(self.app.model, "familiarity", return_value=0.3):
            r = self.predict("auto").get_json()
        self.assertNotEqual(r["result"]["plant_id"], "pest")

class AuthTests(Base):
    def test_register_ok(self): self.assertEqual(self.signup().status_code, 201)
    def test_email_verification_flow(self):
        r = self.signup(verify=False)
        code = r.get_json()["debug_code"]; self.assertEqual(len(code), 6)
        r = self.login(); self.assertEqual(r.status_code, 403); self.assertEqual(r.get_json()["field"], "unverified")  # chưa xác thực
        self.assertEqual(self.c.post("/api/verify", json={"email": "a@b.vn", "code": "000000"}).status_code, 400)
        self.assertEqual(self.c.post("/api/verify/resend", json={"email": "a@b.vn"}).status_code, 429)  # 1 mã/phút
        self.assertEqual(self.c.post("/api/verify", json={"email": "a@b.vn", "code": code}).status_code, 200)
        self.assertEqual(self.c.get("/api/me").get_json()["username"], "nguyenvan")  # xác thực xong đăng nhập luôn
        self.c.post("/api/logout"); self.assertEqual(self.login().status_code, 200)
    def test_forgot_password(self):
        self.signup()
        self.assertEqual(self.c.post("/api/password/forgot", json={"email": "khong@co.vn"}).status_code, 200)  # không lộ email tồn tại
        r = self.c.post("/api/password/forgot", json={"email": "a@b.vn"}); code = r.get_json()["debug_code"]
        self.assertEqual(self.c.post("/api/password/reset", json={"email": "a@b.vn", "code": "123456", "new_password": "moi12345"}).status_code, 400)
        self.assertEqual(self.c.post("/api/password/reset", json={"email": "a@b.vn", "code": code, "new_password": "moi12345"}).status_code, 200)
        self.c.post("/api/logout")
        self.assertEqual(self.login().status_code, 401); self.assertEqual(self.login(p="moi12345").status_code, 200)
        self.assertEqual(self.c.post("/api/password/reset", json={"email": "a@b.vn", "code": code, "new_password": "khac1234"}).status_code, 400)  # mã dùng 1 lần
    def test_login_rate_limit(self):
        self.signup()
        for _ in range(10):
            self.assertEqual(self.login(p="sai").status_code, 401)
        self.assertEqual(self.login(p="matkhau123").status_code, 429)  # khóa 15 phút kể cả đúng mật khẩu
        self.assertEqual(self.c.post("/api/login", json={"username": "khac", "password": "x"}).status_code, 401)  # tài khoản khác không bị ảnh hưởng
    def test_ai_daily_quota(self):
        self.authed()
        with mock.patch("client.routes.AI_DAILY_LIMIT", 2):
            self.assertEqual(self.c.post("/api/chat", json={"message": "1"}).status_code, 200)
            self.assertEqual(self.c.post("/api/chat", json={"message": "2"}).status_code, 200)
            self.assertEqual(self.c.post("/api/chat", json={"message": "3"}).status_code, 429)
    def test_unverified_cannot_login(self):
        self.signup()
        with closing(connect(self.app.config["DATABASE"])) as c:
            c.execute("update users set verified=0"); c.commit()
        self.assertEqual(self.login().status_code, 403)
    def test_register_duplicate(self): self.signup(); self.assertEqual(self.signup().status_code, 409)
    def test_register_validation(self):
        self.assertEqual(self.signup(u="a b").status_code, 400)
        self.assertEqual(self.signup(e="sai-email").status_code, 400)
        self.assertEqual(self.signup(p="123").status_code, 400)
    def test_register_reports_field(self):
        for kw, field in [({"u": "a b"}, "username"), ({"e": "sai@"}, "email"), ({"ph": "12345"}, "phone"),
                          ({"ph": "0212345678"}, "phone"), ({"ph": ""}, "phone"), ({"p": "123"}, "password")]:
            r = self.signup(**kw); self.assertEqual((r.status_code, r.get_json()["field"]), (400, field), kw)
    def test_phone_unique_and_normalized(self):
        self.signup()
        r = self.signup("user2", "u2@b.vn", ph="+84 912.345.678")
        self.assertEqual((r.status_code, r.get_json()["field"]), (409, "phone"))
        r = self.signup("user2", "a@b.vn", ph="0987654321")
        self.assertEqual((r.status_code, r.get_json()["field"]), (409, "email"))
        r = self.signup("nguyenvan", "u2@b.vn", ph="0987654321")
        self.assertEqual((r.status_code, r.get_json()["field"]), (409, "username"))
        self.assertEqual(self.signup("user2", "u2@b.vn", ph="84987654321").status_code, 201)
        self.assertEqual(self.sql("select phone from users where username='user2'"), [("0987654321",)])
    def test_login_ok_email_and_phone(self):
        self.signup()
        for ident in ("nguyenvan", "a@b.vn", "0912345678", "+84912345678"):
            self.assertEqual(self.login(u=ident).status_code, 200, ident)
    def test_login_wrong_password(self): self.signup(); self.assertEqual(self.login(p="saimatkhau").status_code, 401)
    def test_protected_requires_login(self):
        for m, u in [("get", "/api/me"), ("get", "/api/plants"), ("post", "/api/predict"), ("post", "/api/chat"), ("post", "/api/rating"),
                     ("get", "/api/history"), ("get", "/api/posts"), ("post", "/api/posts"), ("get", "/api/ratings"), ("get", "/api/notifications"),
                     ("get", "/api/diagnoses/1"), ("get", "/api/chat"), ("get", "/api/admin/posts"), ("get", "/uploads/scans/x.jpg"),
                     ("get", "/api/treatments"), ("post", "/api/treatments"), ("get", "/api/reminders"), ("get", "/api/weather"), ("get", "/api/map")]:
            self.assertEqual(getattr(self.c, m)(u).status_code, 401, u)
    def test_logout(self):
        self.authed(); self.c.post("/api/logout"); self.assertEqual(self.c.get("/api/me").status_code, 401)
    def test_password_not_plaintext(self):
        self.signup(); self.assertNotIn("matkhau123", self.sql("select pw from users")[0][0])
    def test_home_page(self):
        for url in ("/favicon.ico", "/static/img/logo.png", "/static/img/app-icon-512.png", "/client/static/manifest.json"):
            self.assertEqual(self.get_status(url), 200, url)
        built = os.path.exists(os.path.join(ROOT, "frontend", "dist", "index.html"))
        for url in ("/", "/home", "/diagnosis/3", "/p/12"):  # ứng dụng một trang: mọi đường dẫn giao diện trả index.html
            r = self.c.get(url)
            self.assertEqual(r.status_code, 200 if built else 503, url)
            if built:
                self.assertIn(b"/assets/client-", r.data)
        self.assertEqual(self.c.get("/api/khong-co").status_code, 404)  # đường dẫn API lạ không trả về trang giao diện
    def test_me_profile_update_and_password(self):
        self.authed()
        me = self.c.get("/api/me").get_json()
        self.assertEqual((me["phone"], me["role"], me["stats"]["scans"]), ("0912345678", "user", 0))
        self.assertEqual(self.c.put("/api/me", json={"email": "moi@b.vn", "phone": "0333444555"}).status_code, 200)
        self.assertEqual(self.c.put("/api/me", json={"email": "moi@b.vn", "phone": "123"}).get_json()["field"], "phone")
        self.c.post("/api/logout"); self.signup("user2", "u2@b.vn", ph="0987654321"); self.login("user2")
        r = self.c.put("/api/me", json={"email": "u2@b.vn", "phone": "0333444555"})
        self.assertEqual((r.status_code, r.get_json()["field"]), (409, "phone"))
        self.assertEqual(self.c.post("/api/me/password", json={"old_password": "sai", "new_password": "moi12345"}).status_code, 400)
        self.assertEqual(self.c.post("/api/me/password", json={"old_password": "matkhau123", "new_password": "moi12345"}).status_code, 200)
        self.c.post("/api/logout"); self.assertEqual(self.login("user2", "moi12345").status_code, 200)
    @unittest.skipIf(PG_TEST, "chỉ áp dụng cho file SQLite cũ")
    def test_old_database_is_migrated(self):
        path = os.path.join(self.tmp.name, "old.db")
        with closing(sqlite3.connect(path)) as c:
            c.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL, pw TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);"
                            "CREATE TABLE diagnoses(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, plant_id TEXT, plant TEXT, disease TEXT, raw TEXT, healthy INTEGER, confidence REAL, remedy TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);")
            c.execute("INSERT INTO users(username,email,pw) VALUES('cu','cu@b.vn',?)", (generate_password_hash("matkhau123"),))
            c.execute("INSERT INTO diagnoses(user_id,plant,disease,confidence) VALUES(1,'Cà chua','Khỏe mạnh',0.9)")
            c.commit()
        c = create_app(self.config("old.db")).test_client()
        self.assertEqual(c.post("/api/login", json={"username": "cu", "password": "matkhau123"}).status_code, 200)
        me = c.get("/api/me").get_json()
        self.assertEqual((me["phone"], me["role"], me["stats"]["scans"]), (None, "user", 1))
        self.assertIsNone(c.get("/api/history").get_json()[0]["image_url"])

class PredictTests(Base):
    def test_plants_list(self): self.authed(); self.assertEqual(len(self.c.get("/api/plants").get_json()), 14)
    def test_predict_ok(self):
        self.authed(); r = self.predict("tomato"); self.assertEqual(r.status_code, 200); j = r.get_json()
        self.assertEqual(j["result"]["plant"], "Cà chua"); self.assertTrue(0 < j["result"]["prob"] <= 1)
        self.assertLessEqual(len(j["top"]), 3); self.assertLessEqual(sum(t["prob"] for t in j["top"]), 1.0001)
        self.assertEqual(j["source"], "model")
    def test_auto_mode(self):
        self.authed(); j = self.predict("auto").get_json()
        self.assertIn(j["result"]["plant"], list(knowledge.PLANTS.values()) + ["Chưa xác định"])
    def test_result_restricted_to_chosen_plant(self):
        self.authed()
        for p in knowledge.PLANTS:
            j = self.predict(p, leaf((10, 90, 30))).get_json()
            self.assertTrue(all(t["plant"] == knowledge.PLANTS[p] for t in j["top"]), p)
    def test_deterministic(self):
        self.authed(); a = self.predict().get_json()["result"]["raw"]; b = self.predict().get_json()["result"]["raw"]; self.assertEqual(a, b)
    def test_invalid_plant(self): self.authed(); self.assertEqual(self.predict("xoai").status_code, 400)
    def test_no_image(self):
        self.authed(); r = self.c.post("/api/predict", data={"plant": "tomato"}, content_type="multipart/form-data"); self.assertEqual(r.status_code, 400)
    def test_not_an_image(self):
        self.authed(); self.assertEqual(self.predict(img=io.BytesIO(b"not an image")).status_code, 400)
    def test_history_saved_with_image(self):
        self.authed(); self.predict("potato"); h = self.c.get("/api/history").get_json()
        self.assertEqual(len(h), 1); self.assertEqual(h[0]["plant"], "Khoai tây"); self.assertTrue(h[0]["image_url"].startswith("/uploads/scans/"))
    def test_scan_image_private(self):
        self.authed(); url = self.predict().get_json()["image_url"]
        self.assertEqual(self.get_status(url), 200)
        self.as_user2(); self.assertEqual(self.get_status(url), 404)
    def test_history_isolated_between_users(self):
        self.authed(); self.predict()
        self.as_user2(); self.assertEqual(self.c.get("/api/history").get_json(), [])
    def test_diagnosis_detail_and_delete(self):
        self.authed(); j = self.predict("orange").get_json(); did = j["diagnosis_id"]
        d = self.c.get(f"/api/diagnoses/{did}").get_json()
        self.assertIn(knowledge.LIMITS["orange"], d["details"]["notes"]); self.assertIsNone(d["rating"])
        self.assertEqual(self.c.delete(f"/api/diagnoses/{did}").status_code, 200)
        self.assertEqual(self.c.get("/api/history").get_json(), [])
        self.assertEqual(os.listdir(os.path.join(self.app.config["UPLOAD_DIR"], "scans")), [])
    def test_single_class_plant_warns(self):
        self.authed()
        for p in ("orange", "soybean"):
            self.assertIn(knowledge.LIMITS[p], self.predict(p).get_json()["notes"], p)
    def test_warns_when_image_is_not_chosen_plant(self):
        self.authed(); m = self.app.model
        m.class_names, m.demo = knowledge.CLASS_NAMES + ["Background_without_leaves"], False
        for target, word in [("Background_without_leaves", "Không nhận ra lá"), ("Potato___healthy", "khoai tây")]:
            p = np.full(len(m.class_names), 0.001); p[m.class_names.index(target)] = 0.9
            m.model = FakeModel(p)
            j = self.predict("tomato").get_json()
            self.assertEqual(j["result"]["plant"], "Cà chua"); self.assertTrue(j["low_confidence"])
            self.assertTrue(any(word in n for n in j["notes"]), j["notes"])
    def test_strange_image_is_not_diagnosed(self):
        self.authed(); m = self.app.model
        p = np.full(len(m.class_names), 0.001); p[m.class_names.index("Tomato___healthy")] = 0.95
        m.demo, m.model = False, FakeModel(p)  # mô hình "tự tin" 95%
        emb = thumb_embedding(Image.open(leaf()).convert("RGB").resize((224, 224)))
        m.centroids = np.vstack([-emb])  # nhưng ảnh khác hẳn mọi lớp đã học
        j = self.predict("tomato").get_json()
        self.assertEqual((j["result"]["plant_id"], j["result"]["plant"]), ("unknown", "Cà chua"))
        self.assertTrue(any("khác xa dữ liệu" in n for n in j["notes"]), j["notes"])
        m.centroids = np.vstack([emb])  # ảnh quen thuộc -> mô hình kết luận bình thường
        j = self.predict("tomato").get_json()
        self.assertEqual((j["result"]["disease"], j["source"], j["notes"]), ("Khỏe mạnh", "model", []))
    def test_other_plant_needs_ai(self):
        self.authed(); r = self.predict("other")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(os.listdir(os.path.join(self.app.config["UPLOAD_DIR"], "scans")), [])  # không để lại ảnh rác

class AIScanTests(Base):
    def ai(self, **kw):
        return mock.patch.multiple(ai_service, vision_available=mock.Mock(return_value=True), analyze_image=mock.Mock(**kw))
    def test_new_plant_is_learned_and_saved_to_dataset(self):
        self.authed()
        with self.ai(return_value=ai_answer()):
            j = self.predict("other").get_json()
        self.assertEqual((j["source"], j["result"]["plant"], j["result"]["disease"]), ("ai", "Xoài", "Bệnh thán thư"))
        self.assertTrue(any("bộ dữ liệu" in n for n in j["notes"]))
        self.assertEqual(self.dataset_files(), ["Mango___Anthracnose"])
        plants = self.c.get("/api/plants").get_json()
        self.assertIn({"id": "mango", "name": "Xoài", "note": "", "source": "ai"}, plants)
        with self.ai(return_value=ai_answer(disease_vi="Thán thư")):
            j = self.predict("mango", leaf((200, 40, 40))).get_json()  # ảnh khác hẳn -> không khớp bộ nhớ, phải hỏi AI
            self.assertEqual(ai_service.analyze_image.call_args[0][1:], ("Xoài",))  # chỉ gợi ý tên cây, không đưa danh sách lớp
        self.assertEqual(j["result"]["disease"], "Bệnh thán thư")  # giữ tên đã học, không tạo lớp trùng
        self.assertEqual(self.sql("select class_name, samples from ai_classes"), [("Mango___Anthracnose", 2)])
    def test_ai_used_when_model_uncertain(self):
        self.authed()
        with self.ai(return_value=ai_answer(plant_vi="Cà chua", plant_en="Tomato", disease_vi="Mốc sương", disease_en="Late blight")):
            j = self.predict("auto").get_json()  # DEMO: xác suất chia cho 38 lớp nên mô hình luôn "chưa chắc chắn"
        self.assertEqual((j["source"], j["result"]["disease"]), ("ai", "Bệnh mốc sương (sương mai)"))
        self.assertTrue(any("AI (Gemini)" in n for n in j["notes"]))
        self.assertEqual(self.dataset_files(), ["Tomato___Late_blight"])
        self.assertEqual(self.sql("select count(*) from ai_classes"), [(0,)])  # lớp có sẵn trong mô hình, không phải cây mới
    def test_ai_unknown_plant_not_learned(self):
        """AI thấy bệnh nhưng không biết cây gì (VD ảnh cận một phần lá): hiện kết quả, nhưng không tạo "cây" mới, không lưu để học."""
        self.authed()
        with self.ai(return_value=ai_answer(plant_vi="Không xác định", plant_en="Unknown", disease_vi="Bệnh sương mai", disease_en="Downy Mildew")):
            j = self.predict("auto").get_json()
        self.assertEqual((j["source"], j["result"]["plant_id"], j["result"]["plant"], j["result"]["disease"]),
                         ("ai", "unidentified", "Chưa rõ loại cây", "Bệnh sương mai"))
        self.assertTrue(any("chưa xác định được loại cây" in n for n in j["notes"]), j["notes"])
        self.assertEqual(self.dataset_files(), []); self.assertEqual(self.sql("select count(*) from ai_classes, ai_samples"), [(0,)])
        with self.ai(return_value=ai_answer(plant_en="Plant type not clearly identifiable from image", plant_vi="Không xác định rõ loại cây từ ảnh")):
            self.assertEqual(self.predict("auto").get_json()["result"]["plant"], "Chưa rõ loại cây")
    def test_vague_learned_classes_ignored(self):
        """Dữ liệu "cây không xác định" đã học từ trước: không hiện trong danh sách cây, không dùng lại qua bộ nhớ ảnh."""
        self.authed()
        img = leaf((90, 70, 40)).getvalue()
        emb = self.app.model.embed(img)
        self.run_sql("INSERT INTO ai_classes(class_name,plant_id,plant,disease,healthy,samples) VALUES('Unknown___Downy_Mildew','unknown','Không xác định','Bệnh Sương mai',0,1)")
        self.run_sql("INSERT INTO ai_samples(user_id,class_name,path,confidence,embedding,embed_key) VALUES(1,'Unknown___Downy_Mildew','x.jpg',0.85,?,?)",
                     emb.astype(np.float32).tobytes(), self.app.model.embed_key)
        self.assertNotIn("unknown", [p["id"] for p in self.c.get("/api/plants").get_json()])
        j = self.c.post("/api/predict", data={"plant": "auto", "image": (io.BytesIO(img), "l.jpg")}, content_type="multipart/form-data").get_json()
        self.assertNotEqual(j["source"], "memory"); self.assertNotEqual(j["result"]["disease"], "Bệnh Sương mai")
    def test_model_plant_guess_sent_to_ai(self):
        """Mô hình chưa chắc bệnh nhưng các khả năng đều là cà chua -> gợi ý "có thể là lá cà chua" cho AI (chỉ khi Tự nhận diện)."""
        self.authed(); m = self.app.model
        p = np.full(len(m.class_names), 0.0005)
        for c, v in [("Tomato___Late_blight", 0.5), ("Tomato___Early_blight", 0.3), ("Tomato___Septoria_leaf_spot", 0.15)]:
            p[m.class_names.index(c)] = v
        m.demo, m.model = False, FakeModel(p)
        with self.ai(return_value=ai_answer(plant_vi="Cà chua", plant_en="Tomato", disease_vi="Đốm vòng", disease_en="Early blight")):
            j = self.predict("auto").get_json()
            self.assertIsNotNone(ai_service.analyze_image.call_args, j)
            kw = ai_service.analyze_image.call_args.kwargs
            self.assertEqual(kw["model_plant"], "Cà chua")
        self.assertEqual(j["result"]["disease"], "Bệnh đốm vòng (mốc sương sớm)")
        p[m.class_names.index("Potato___Late_blight")] = 0.3  # khả năng thuộc nhiều cây khác nhau -> không gợi ý
        self.run_sql("DELETE FROM ai_samples")  # ảnh màu đơn sắc giống nhau: không để bộ nhớ ảnh trả lời thay AI
        with self.ai(return_value=ai_answer()):
            self.predict("auto", leaf((10, 200, 30)))
            self.assertNotIn("model_plant", ai_service.analyze_image.call_args.kwargs)
    def test_ai_low_confidence_not_saved(self):
        self.authed()
        with self.ai(return_value=ai_answer(confidence=0.4)):
            j = self.predict("other").get_json()
        self.assertTrue(j["low_confidence"]); self.assertEqual(self.dataset_files(), [])
    def test_ai_not_a_plant(self):
        self.authed()
        with self.ai(return_value=ai_answer(is_plant=False, confidence=0.95)):
            j = self.predict("other").get_json()
        self.assertEqual(j["result"]["disease"], "Không nhận ra cây trồng"); self.assertEqual(self.dataset_files(), [])
    def test_ai_error_falls_back_to_model(self):
        self.authed()
        with self.ai(side_effect=RuntimeError("mất mạng")):
            j = self.predict("orange").get_json()  # cây 1 lớp: mô hình chắc chắn nhưng cần AI kiểm tra thêm
        self.assertEqual(j["source"], "model"); self.assertTrue(any("Chưa gọi được AI" in n for n in j["notes"]))
    RICE = dict(plant_vi="Lúa", plant_en="Rice", disease_vi="Bệnh đạo ôn", disease_en="Rice blast", confidence=0.95)
    def test_memory_reuses_ai_result_for_same_leaf(self):
        self.authed()
        with self.ai(return_value=ai_answer(**self.RICE)):
            first = self.predict("auto").get_json()
        self.assertEqual((first["source"], first["result"]["disease"]), ("ai", "Bệnh đạo ôn"))
        with self.ai(side_effect=RuntimeError("hết lượt")):
            again = self.predict("auto").get_json()  # cùng chiếc lá, AI đang lỗi
            self.assertEqual(ai_service.analyze_image.call_count, 0)  # nhận ra từ bộ nhớ, không tốn lượt gọi AI
        self.assertEqual((again["source"], again["result"]["plant"], again["result"]["disease"]), ("memory", "Lúa", "Bệnh đạo ôn"))
        self.assertTrue(any("giống 100%" in n for n in again["notes"]), again["notes"])
        self.assertEqual(self.dataset_files(), ["Rice___Rice_blast"])  # ảnh trùng không lưu thêm
    def test_unknown_when_model_unsure_and_ai_fails(self):
        self.authed()
        busy = urllib.error.HTTPError("u", 429, "Too Many Requests", None, None)
        with self.ai(side_effect=busy):
            j = self.predict("auto").get_json()  # DEMO: mô hình luôn dưới 60% ở chế độ tự nhận diện
        self.assertEqual((j["result"]["plant_id"], j["result"]["disease"], j["source"]), ("unknown", "Chưa xác định được bệnh", "model"))
        self.assertTrue(any("hết lượt" in n for n in j["notes"]), j["notes"]); self.assertEqual(len(j["top"]), 3)
        self.assertTrue(self.c.get(f"/api/diagnoses/{j['diagnosis_id']}").get_json()["details"]["ai_failed"])
    def test_hint_from_similar_learned_leaf(self):
        self.authed()
        with self.ai(return_value=ai_answer(**self.RICE)):
            self.predict("auto")
        with self.ai(side_effect=RuntimeError("lỗi")):
            j = self.predict("auto", leaf((80, 160, 40))).get_json()  # màu gần giống: độ giống ~0.88
        self.assertEqual(j["result"]["plant_id"], "unknown")
        self.assertTrue(any("khá giống mẫu đã học: Lúa, bệnh đạo ôn" in n for n in j["notes"]), j["notes"])
    BROWN_SPOT = dict(plant_vi="Lúa", plant_en="Rice", disease_vi="Bệnh đốm nâu", disease_en="Brown spot", confidence=0.9)
    def test_new_disease_of_learned_plant_not_merged(self):
        self.authed()
        with self.ai(return_value=ai_answer(**self.RICE)):
            self.predict("auto")
        with self.ai(return_value=ai_answer(**self.BROWN_SPOT)):
            j = self.predict("auto", leaf((200, 40, 40))).get_json()
        self.assertEqual((j["result"]["raw"], j["result"]["plant_id"], j["result"]["disease"]), ("Rice___Brown_spot", "rice", "Bệnh đốm nâu"))
        self.assertEqual(self.dataset_files(), ["Rice___Brown_spot", "Rice___Rice_blast"])
    def test_names_matched_to_known_classes(self):
        self.authed()
        with self.ai(return_value=ai_answer(**self.RICE)):
            self.predict("auto")
        cases = [((40, 40, 200), dict(self.RICE, disease_en="Blast", disease_vi="Bệnh đạo ôn lá"), ("Rice___Rice_blast", "Bệnh đạo ôn")),
                 ((200, 200, 40), dict(plant_vi="Ngô", plant_en="Maize", disease_vi="Bệnh gỉ sắt phương nam", disease_en="Southern rust"),
                  ("Corn_(maize)___Southern_rust", "Bệnh gỉ sắt phương nam")),
                 ((40, 200, 200), dict(plant_vi="Cà chua", plant_en="Tomato", disease_vi="Bệnh mốc sương sớm", disease_en="Early blight"),
                  ("Tomato___Early_blight", "Bệnh đốm vòng (mốc sương sớm)"))]
        for color, answer, (cls, disease) in cases:
            with self.ai(return_value=ai_answer(**answer)):
                r = self.predict("auto", leaf(color)).get_json()["result"]
            self.assertEqual((r["raw"], r["disease"]), (cls, disease), answer)
        self.assertEqual(r["plant_id"], "tomato")
        self.assertIn(("Corn_(maize)___Southern_rust", "corn", "Ngô"), self.sql("select class_name, plant_id, plant from ai_classes"))
    def test_reanalyze_replaces_wrong_label(self):
        self.authed()
        with self.ai(return_value=ai_answer(**self.RICE)):
            first = self.predict("auto").get_json()["diagnosis_id"]
            again = self.predict("auto").get_json()  # cùng ảnh -> lấy từ bộ nhớ (nhãn đạo ôn đang sai)
        self.assertEqual(again["source"], "memory")
        with self.ai(return_value=ai_answer(**self.BROWN_SPOT)):
            self.assertEqual(self.c.post(f"/api/diagnoses/{again['diagnosis_id']}/reanalyze").status_code, 200)
        self.assertEqual(self.dataset_files(), ["Rice___Brown_spot"])  # mẫu đạo ôn của ảnh này bị gỡ
        self.assertEqual(self.sql("select class_name from ai_classes"), [("Rice___Brown_spot",)])
        with self.ai(side_effect=RuntimeError("không cần gọi")):
            j = self.predict("auto").get_json()
        self.assertEqual((j["source"], j["result"]["disease"]), ("memory", "Bệnh đốm nâu"))
        self.assertEqual(self.c.get(f"/api/diagnoses/{first}").get_json()["disease"], "Bệnh đạo ôn")  # lịch sử cũ giữ nguyên
    def test_reanalyze(self):
        self.authed()
        with self.ai(side_effect=RuntimeError("lỗi")):
            did = self.predict("auto").get_json()["diagnosis_id"]
            self.assertEqual(self.c.post(f"/api/diagnoses/{did}/reanalyze").status_code, 503)
        with self.ai(return_value=ai_answer(**self.RICE)):
            self.assertEqual(self.c.post(f"/api/diagnoses/{did}/reanalyze").status_code, 200)
        d = self.c.get(f"/api/diagnoses/{did}").get_json()
        self.assertEqual((d["source"], d["plant"], d["disease"], d["details"]["ai_failed"]), ("ai", "Lúa", "Bệnh đạo ôn", False))
        self.assertEqual(self.dataset_files(), ["Rice___Rice_blast"])
        self.as_user2(); self.assertEqual(self.c.post(f"/api/diagnoses/{did}/reanalyze").status_code, 404)
    def test_embeddings_backfilled_on_start(self):
        self.authed()
        with self.ai(return_value=ai_answer(**self.RICE)):
            self.predict("auto")
        with closing(connect(self.app.config["DATABASE"])) as c:
            c.execute("update ai_samples set embedding=NULL, embed_key=NULL"); c.commit()
        create_app(self.config())
        self.assertEqual(self.sql("select embed_key, length(embedding) from ai_samples"), [("thumb", 768 * 4)])

class PostTests(Base):
    def moderate(self, decision, feedback=""):
        return mock.patch.object(ai_service, "moderate", return_value=dict(decision=decision, reason="ghi chú", feedback=feedback, source="gemini"))
    def test_approved_post_in_feed_with_image(self):
        self.authed()
        with self.moderate("approve"):
            j = self.new_post(img=leaf()).get_json()
        self.assertEqual(j["status"], "approved")
        self.as_user2()
        feed = self.c.get("/api/posts").get_json()
        self.assertEqual([p["id"] for p in feed], [j["post"]["id"]]); self.assertFalse(feed[0]["is_mine"])
        self.assertEqual(self.get_status(feed[0]["image_url"]), 200)
    def test_rejected_post_feedback_and_notification(self):
        self.authed()
        with self.moderate("reject", "Bài có lời lẽ xúc phạm."):
            r = self.new_post("nội dung xấu", img=leaf())
        j = r.get_json()
        self.assertEqual((r.status_code, j["status"], j["post"]["feedback"]), (201, "rejected", "Bài có lời lẽ xúc phạm."))
        self.assertEqual(self.c.get("/api/posts").get_json(), [])
        self.assertEqual(self.c.get("/api/posts?scope=mine").get_json()[0]["status"], "rejected")
        self.assertIn("xúc phạm", self.c.get("/api/notifications").get_json()[0]["content"])
        self.assertEqual(self.c.get("/api/me").get_json()["unread"], 1)
        self.c.post("/api/notifications/read"); self.assertEqual(self.c.get("/api/me").get_json()["unread"], 0)
        url = j["post"]["image_url"]
        self.as_user2(); self.assertEqual(self.get_status(url), 404)
    def test_without_ai_post_waits_for_admin(self):
        self.authed()
        j = self.new_post().get_json()  # không có GEMINI_API_KEY -> chờ quản trị viên
        self.assertEqual(j["status"], "pending"); self.assertEqual(self.c.get("/api/posts").get_json(), [])
    def test_post_validation(self):
        self.authed()
        self.assertEqual(self.new_post("").status_code, 400)
        self.assertEqual(self.new_post("x" * 2001).status_code, 400)
        self.assertEqual(self.new_post("có ảnh lỗi", img=io.BytesIO(b"abc")).get_json()["field"], "image")
    def test_admin_review(self):
        self.authed(); pid = self.new_post().get_json()["post"]["id"]
        self.assertEqual(self.c.get("/api/admin/posts").status_code, 403)
        self.make_admin()
        pending = self.c.get("/api/admin/posts").get_json()
        self.assertEqual([p["id"] for p in pending], [pid]); self.assertEqual(pending[0]["ai_decision"], "review")
        self.assertEqual(self.c.post(f"/api/admin/posts/{pid}", json={"action": "approve"}).status_code, 200)
        self.assertEqual([p["id"] for p in self.c.get("/api/posts").get_json()], [pid])
        self.c.post(f"/api/admin/posts/{pid}", json={"action": "reject", "note": "Ảnh không liên quan"})
        self.assertEqual(self.c.get("/api/posts").get_json(), [])
        self.assertEqual([n["content"] for n in self.c.get("/api/notifications").get_json()],
                         ["Bài viết của bạn bị quản trị viên từ chối: Ảnh không liên quan",
                          "Bài viết của bạn đã được quản trị viên duyệt và đăng lên trang chủ."])
        self.assertEqual(self.c.get("/api/admin/stats").get_json()["pending"], 0)
    def test_delete_post_owner_only(self):
        self.authed()
        with self.moderate("approve"):
            pid = self.new_post().get_json()["post"]["id"]
        self.as_user2(); self.assertEqual(self.c.delete(f"/api/posts/{pid}").status_code, 404)
        self.c.post("/api/logout"); self.login()
        self.assertEqual(self.c.delete(f"/api/posts/{pid}").status_code, 200); self.assertEqual(self.c.get("/api/posts").get_json(), [])

class InteractionTests(Base):
    def approve(self):
        return mock.patch.object(ai_service, "moderate", return_value=dict(decision="approve", reason="", feedback="", source="gemini"))
    def reject(self, feedback):
        return mock.patch.object(ai_service, "moderate", return_value=dict(decision="reject", reason="", feedback=feedback, source="gemini"))
    def posted(self, **kw):
        with self.approve():
            return self.new_post(**kw).get_json()["post"]["id"]
    def test_like_toggle_and_notification(self):
        self.authed(); pid = self.posted()
        self.as_user2()
        self.assertEqual(self.c.post(f"/api/posts/{pid}/like").get_json(), {"liked": True, "likes": 1})
        p = self.c.get("/api/posts").get_json()[0]; self.assertEqual((p["likes"], p["liked"]), (1, True))
        self.assertEqual(self.c.post(f"/api/posts/{pid}/like").get_json(), {"liked": False, "likes": 0})
        self.c.post("/api/logout"); self.login()
        n = self.c.get("/api/notifications").get_json()[0]
        self.assertEqual((n["content"], n["link"]), ("user2 đã thích bài viết của bạn.", f"#/p/{pid}"))
    def test_cannot_interact_with_unapproved_post(self):
        self.authed(); pid = self.new_post().get_json()["post"]["id"]  # không có AI -> chờ duyệt
        for url, body in [(f"/api/posts/{pid}/like", None), (f"/api/posts/{pid}/comments", {"content": "hay"}), (f"/api/posts/{pid}/share", {"kind": "link"})]:
            self.assertEqual(self.c.post(url, json=body).status_code, 404, url)
        self.assertEqual(self.c.get(f"/api/posts/{pid}").status_code, 200)  # chủ bài vẫn xem được
        self.as_user2(); self.assertEqual(self.c.get(f"/api/posts/{pid}").status_code, 404)
    def test_comments(self):
        self.authed(); pid = self.posted()
        self.as_user2()
        with self.approve() as m:
            r = self.c.post(f"/api/posts/{pid}/comments", json={"content": "Cảm ơn bác đã chia sẻ"})
        self.assertEqual(r.status_code, 201); self.assertEqual(m.call_args.kwargs["kind"], "comment")
        cid = r.get_json()["comment"]["id"]
        with self.reject("Không dùng lời lẽ xúc phạm."):
            r = self.c.post(f"/api/posts/{pid}/comments", json={"content": "đồ ngu"})
        self.assertEqual((r.status_code, r.get_json()["field"]), (400, "content")); self.assertIn("xúc phạm", r.get_json()["error"])
        self.assertEqual(self.c.post(f"/api/posts/{pid}/comments", json={"content": "AI chưa kiểm tra vẫn đăng"}).status_code, 201)
        d = self.c.get(f"/api/posts/{pid}").get_json()
        self.assertEqual([c["content"] for c in d["comments"]], ["Cảm ơn bác đã chia sẻ", "AI chưa kiểm tra vẫn đăng"])
        self.assertEqual(d["post"]["comments"], 2)
        self.c.post("/api/logout"); self.signup("user3", "u3@b.vn", ph="0977111222"); self.login("user3")
        self.assertEqual(self.c.delete(f"/api/comments/{cid}").status_code, 404)  # người ngoài không xóa được
        self.c.post("/api/logout"); self.login()
        self.assertEqual(self.c.delete(f"/api/comments/{cid}").status_code, 200)  # chủ bài xóa được
        self.assertIn("user2 đã bình luận về bài viết của bạn", self.c.get("/api/notifications").get_json()[0]["content"])
    def test_share_link_and_repost(self):
        self.authed(); pid = self.posted(img=leaf())
        self.as_user2()
        self.assertEqual(self.c.post(f"/api/posts/{pid}/share", json={"kind": "link"}).get_json(), {"shares": 1})
        j = self.c.post(f"/api/posts/{pid}/share", json={"kind": "repost"}).get_json()  # không kèm lời -> đăng ngay
        repost = j["post"]
        self.assertEqual((j["status"], repost["shared"]["id"], repost["shared"]["username"]), ("approved", pid, "nguyenvan"))
        self.assertEqual(self.get_status(repost["shared"]["image_url"]), 200)
        again = self.c.post(f"/api/posts/{repost['id']}/share", json={"kind": "repost"}).get_json()["post"]
        self.assertEqual(again["shared"]["id"], pid)  # chia sẻ bài chia sẻ -> trỏ về bài gốc
        with self.reject("Không quảng cáo."):
            r = self.c.post(f"/api/posts/{pid}/share", json={"kind": "repost", "content": "mua thuốc giá rẻ"}).get_json()
        self.assertEqual((r["status"], r["post"]["feedback"]), ("rejected", "Không quảng cáo."))
        self.assertEqual(next(p for p in self.c.get("/api/posts").get_json() if p["id"] == pid)["shares"], 3)
        self.c.post("/api/logout"); self.login()
        self.assertIn("user2 đã chia sẻ bài viết của bạn.", [n["content"] for n in self.c.get("/api/notifications").get_json()])
        self.c.delete(f"/api/posts/{pid}")
        self.as_user2()
        shared = [p["shared"] for p in self.c.get("/api/posts?scope=mine").get_json() if p["status"] == "approved"]
        self.assertEqual(shared, [{"deleted": True}, {"deleted": True}])
    def test_share_diagnosis(self):
        self.authed(); did = self.predict().get_json()["diagnosis_id"]
        with self.approve() as m:
            j = self.c.post("/api/posts", data={"content": "", "diagnosis_id": did}, content_type="multipart/form-data").get_json()
        self.assertEqual(j["status"], "approved")
        text, image = m.call_args[0]
        self.assertIn("Kèm kết quả tra cứu: Cà chua", text); self.assertTrue(image)  # AI xem cả ảnh tra cứu
        card = j["post"]["diagnosis"]
        self.assertEqual((card["id"], card["plant"]), (did, "Cà chua"))
        self.as_user2()
        self.assertEqual(self.get_status(card["image_url"]), 200)  # đã chia sẻ thì người khác xem được ảnh
        self.assertEqual(self.c.post("/api/posts", data={"diagnosis_id": did}, content_type="multipart/form-data").status_code, 404)
        self.c.post("/api/logout"); self.login()
        self.c.delete(f"/api/diagnoses/{did}")
        self.assertIsNone(self.c.get("/api/posts").get_json()[0]["diagnosis"])
    def test_shared_result_detail(self):
        self.authed(); did = self.predict("orange").get_json()["diagnosis_id"]
        with self.approve():
            pid = self.c.post("/api/posts", data={"content": "Cam nhà tôi", "diagnosis_id": did}, content_type="multipart/form-data").get_json()["post"]["id"]
            plain = self.new_post("Bài không kèm tra cứu").get_json()["post"]["id"]
        self.assertTrue(self.c.get(f"/api/posts/{pid}/result").get_json()["is_mine"])
        self.as_user2()
        r = self.c.get(f"/api/posts/{pid}/result").get_json()
        self.assertEqual((r["plant"], r["username"], r["is_mine"], r["diagnosis_id"]), ("Cam", "nguyenvan", False, did))
        self.assertTrue(r["remedy"]); self.assertNotIn("source", r)  # không hiện nguồn (mô hình/Gemini) cho người xem
        self.assertEqual(self.c.get(f"/api/posts/{plain}/result").status_code, 404)
    def test_pending_shared_diagnosis_stays_private(self):
        self.authed(); did = self.predict().get_json()["diagnosis_id"]
        card = self.c.post("/api/posts", data={"diagnosis_id": did}, content_type="multipart/form-data").get_json()["post"]["diagnosis"]
        self.as_user2(); self.assertEqual(self.get_status(card["image_url"]), 404)
    def test_delete_post_removes_interactions(self):
        self.authed(); pid = self.posted()
        self.c.post(f"/api/posts/{pid}/like"); self.c.post(f"/api/posts/{pid}/comments", json={"content": "a"})
        self.c.post(f"/api/posts/{pid}/share", json={"kind": "link"})
        self.c.delete(f"/api/posts/{pid}")
        self.assertEqual([self.sql(f"select count(*) from {t}")[0][0] for t in ("post_likes", "comments", "post_shares")], [0, 0, 0])

class AdminTests(Base):
    KEY_A, KEY_B = "AIza" + "a" * 35, "AIza" + "b" * 35
    def setUp(self):
        super().setUp()
        ai_service._cooldown.clear(); ai_service._turn = 0
        self.signup(); self.make_admin(); self.login()
    def uid(self, name):
        return next(u["id"] for u in self.c.get(f"/api/admin/users?q={name}").get_json() if u["username"] == name)
    def approve(self):
        return mock.patch.object(ai_service, "moderate", return_value=dict(decision="approve", reason="", feedback="", source="gemini"))
    def add_key(self, key, label="", tested=(True, "")):
        with mock.patch.object(ai_service, "test_key", return_value=tested):
            return self.c.post("/api/admin/keys", json={"label": label, "key": key})

    def test_non_admin_forbidden(self):
        self.as_user2()
        for m, u in [("get", "/api/admin/stats"), ("get", "/api/admin/users"), ("post", "/api/admin/users/1"), ("delete", "/api/admin/users/1"),
                     ("get", "/api/admin/comments"), ("get", "/api/admin/ratings"), ("delete", "/api/admin/ratings/1"), ("get", "/api/admin/keys"),
                     ("post", "/api/admin/keys"), ("patch", "/api/admin/keys/1"), ("delete", "/api/admin/keys/1"), ("post", "/api/admin/keys/1/test"),
                     ("put", "/api/admin/settings"), ("post", "/api/admin/broadcast")]:
            self.assertEqual(getattr(self.c, m)(u, json={}).status_code, 403, u)
    def test_admin_page_and_login(self):
        built = os.path.exists(os.path.join(ROOT, "frontend", "dist", "admin.html"))
        for url in ("/admin", "/admin/"):  # trang riêng, tách khỏi giao diện người dùng
            r = self.c.get(url)
            self.assertEqual(r.status_code, 200 if built else 503, url)
            if built:
                self.assertIn(b"/assets/admin-", r.data); self.assertNotIn(b"/assets/client-", r.data)
        self.signup("user2", "u2@b.vn", ph="0987654321")
        other = self.app.test_client()
        other.post("/api/login", json={"username": "user2", "password": "matkhau123"})
        r = other.post("/api/admin/login", json={"username": "user2", "password": "matkhau123"})
        self.assertEqual(r.status_code, 403); self.assertIn("không có quyền quản trị", r.get_json()["error"])
        self.assertEqual(other.get("/api/me").get_json()["username"], "user2")  # tài khoản thường bị từ chối: phiên cũ giữ nguyên
        self.assertEqual(other.post("/api/admin/login", json={"username": "nguyenvan", "password": "sai"}).status_code, 401)
        self.assertEqual(other.post("/api/admin/login", json={"username": "nguyenvan", "password": "matkhau123"}).status_code, 200)
        self.assertEqual(other.get("/api/me").get_json()["username"], "nguyenvan")
        self.assertEqual(other.get("/api/admin/stats").status_code, 200)
        self.c.post(f"/api/admin/users/{self.uid('user2')}", json={"action": "lock"})
        self.assertEqual(self.c.post("/api/admin/login", json={"username": "user2", "password": "matkhau123"}).status_code, 403)
    def test_analytics_and_models(self):
        self.predict(); self.c.post("/api/rating", json={"diagnosis_id": 1, "stars": 5})
        self.c.post("/api/chat", json={"message": "hi"})
        a = self.c.get("/api/admin/analytics").get_json()
        self.assertEqual((len(a["months"]), len(a["monthly"]), len(a["ai_usage"])), (12, 12, 30))
        self.assertEqual(sum(sum(m[k] for k in ("model", "ai", "memory", "pest")) for m in a["monthly"]), 1)
        self.assertEqual(a["accuracy"][0]["accuracy"], 1.0); self.assertEqual(a["ai_usage"][-1]["chat"], 1)
        m = self.c.get("/api/admin/models").get_json()
        self.assertIn("leaf", m); self.assertIn("pest", m); self.assertEqual(m["class_count"], len(knowledge.CLASS_NAMES))
        self.assertEqual(self.c.get("/api/admin/results/khong_co.png").status_code, 404)
        self.as_user2(); self.assertEqual(self.c.get("/api/admin/analytics").status_code, 403)
    def test_stats_and_broadcast(self):
        self.predict(); self.signup("user2", "u2@b.vn", ph="0987654321")
        st = self.c.get("/api/admin/stats").get_json()
        self.assertEqual((st["users"], st["diagnoses"], st["today"], len(st["daily"]), st["daily"][-1]["n"]), (2, 1, 1, 14, 1))
        self.assertEqual(self.c.post("/api/admin/broadcast", json={"content": ""}).status_code, 400)
        self.assertEqual(self.c.post("/api/admin/broadcast", json={"content": "Mưa nhiều, phòng đạo ôn"}).get_json()["sent"], 2)
        self.c.post("/api/logout"); self.login("user2")
        self.assertIn("Mưa nhiều, phòng đạo ôn", self.c.get("/api/notifications").get_json()[0]["content"])
    def test_lock_role_and_reset_password(self):
        self.signup("user2", "u2@b.vn", ph="0987654321"); u2 = self.uid("user2")
        other = self.app.test_client()
        other.post("/api/login", json={"username": "user2", "password": "matkhau123"})
        self.assertEqual(self.c.post(f"/api/admin/users/{u2}", json={"action": "lock"}).status_code, 200)
        self.assertEqual(other.get("/api/me").status_code, 403)  # đang đăng nhập cũng bị chặn ngay
        r = other.post("/api/login", json={"username": "user2", "password": "matkhau123"})
        self.assertEqual(r.status_code, 403); self.assertIn("bị khóa", r.get_json()["error"])
        self.c.post(f"/api/admin/users/{u2}", json={"action": "unlock"})
        self.assertEqual(other.post("/api/login", json={"username": "user2", "password": "matkhau123"}).status_code, 200)
        me = self.uid("nguyenvan")
        self.assertEqual(self.c.post(f"/api/admin/users/{me}", json={"action": "lock"}).status_code, 400)  # không tự khóa mình
        self.assertEqual(self.c.post(f"/api/admin/users/{me}", json={"action": "make_user"}).status_code, 400)
        self.c.post(f"/api/admin/users/{u2}", json={"action": "make_admin"})
        self.assertEqual(other.get("/api/admin/stats").status_code, 200)
        self.c.post(f"/api/admin/users/{u2}", json={"action": "make_user"})
        self.assertEqual(other.get("/api/admin/stats").status_code, 403)
        pw = self.c.post(f"/api/admin/users/{u2}", json={"action": "reset_password"}).get_json()["password"]
        self.assertEqual(len(pw), 10)
        self.assertEqual(other.post("/api/login", json={"username": "user2", "password": "matkhau123"}).status_code, 401)
        self.assertEqual(other.post("/api/login", json={"username": "user2", "password": pw}).status_code, 200)
    def test_delete_user_removes_their_content(self):
        with self.approve():
            mine = self.new_post("Bài của quản trị").get_json()["post"]["id"]
        self.as_user2()
        did = self.predict().get_json()["diagnosis_id"]
        self.c.post("/api/rating", json={"diagnosis_id": did, "stars": 4})
        with self.approve():
            self.new_post("Bài của user2")
            self.c.post(f"/api/posts/{mine}/comments", json={"content": "Hay quá"})
        self.c.post(f"/api/posts/{mine}/like")
        self.c.post("/api/logout"); self.login()
        u2 = self.uid("user2")
        self.assertEqual(self.c.delete(f"/api/admin/users/{self.uid('nguyenvan')}").status_code, 400)
        self.assertEqual(self.c.delete(f"/api/admin/users/{u2}").status_code, 200)
        counts = [self.sql(f"select count(*) from {t} where user_id=?", u2)[0][0] for t in ("posts", "comments", "post_likes", "diagnoses", "ratings")]
        self.assertEqual(counts, [0] * 5)
        p = self.c.get(f"/api/posts/{mine}").get_json()
        self.assertEqual((p["post"]["likes"], p["comments"]), (0, []))
        self.assertEqual(os.listdir(os.path.join(self.app.config["UPLOAD_DIR"], "scans")), [])
    def test_comments_ratings_and_posts_management(self):
        with self.approve():
            pid = self.new_post("Lúa nhà tôi vàng lá").get_json()["post"]["id"]
        self.new_post("Cà chua chờ duyệt")  # không có AI -> chờ duyệt
        self.as_user2()
        self.c.post(f"/api/posts/{pid}/comments", json={"content": "AI chưa kiểm tra bình luận này"})
        with self.approve():
            self.c.post(f"/api/posts/{pid}/comments", json={"content": "Bình luận đã duyệt"})
        did = self.predict().get_json()["diagnosis_id"]
        self.c.post("/api/rating", json={"diagnosis_id": did, "stars": 2, "comment": "sai rồi"})
        self.c.post("/api/logout"); self.login()
        self.assertEqual(len(self.c.get("/api/admin/comments").get_json()), 2)
        flagged = self.c.get("/api/admin/comments?flagged=1").get_json()
        self.assertEqual([c["content"] for c in flagged], ["AI chưa kiểm tra bình luận này"])
        self.assertEqual(len(self.c.get("/api/admin/comments?q=đã duyệt").get_json()), 1)
        self.assertEqual(self.c.delete(f"/api/comments/{flagged[0]['id']}").status_code, 200)
        self.assertEqual(self.c.get("/api/admin/ratings?stars=5").get_json(), [])
        rating = self.c.get("/api/admin/ratings?stars=2").get_json()[0]
        self.assertEqual((rating["username"], rating["comment"]), ("user2", "sai rồi"))
        self.assertEqual(self.c.delete(f"/api/admin/ratings/{rating['id']}").status_code, 200)
        self.assertEqual(self.c.get("/api/admin/ratings").get_json(), [])
        self.assertEqual(len(self.c.get("/api/admin/posts?status=all").get_json()), 2)
        self.assertEqual([p["content"] for p in self.c.get("/api/admin/posts?status=all&q=Lúa").get_json()], ["Lúa nhà tôi vàng lá"])
    def test_gemini_keys_are_encrypted_and_managed(self):
        self.assertEqual(self.add_key("ngắn quá").status_code, 400)
        r = self.add_key(self.KEY_A, tested=(False, "Khóa không hợp lệ hoặc bị chặn"))
        self.assertEqual((r.status_code, r.get_json()["field"]), (400, "key"))
        self.assertEqual(self.add_key(self.KEY_A, "Khóa A").status_code, 201)
        self.assertEqual(self.add_key(self.KEY_A).status_code, 409)  # trùng
        r = self.add_key(self.KEY_B, tested=(False, "Khóa đúng nhưng đang hết hạn mức với f1")).get_json()
        self.assertIn("hết hạn mức", r["message"])  # vẫn thêm: khóa đúng, chỉ tạm hết lượt
        stored = " ".join(row[0] for row in self.sql("select key_enc from ai_keys"))
        self.assertNotIn(self.KEY_A, stored); self.assertNotIn("aaaaaaaa", stored)  # lưu mã hóa
        keys = self.c.get("/api/admin/keys").get_json()["keys"]
        self.assertEqual([(k["label"], k["masked"]) for k in keys], [("Khóa A", "AIza…aaaa"), ("Khóa 2", "AIza…bbbb")])
        a, b = keys[0]["id"], keys[1]["id"]
        self.c.patch(f"/api/admin/keys/{a}", json={"enabled": False, "label": "Khóa A cũ"})
        self.assertEqual([k["label"] for k in self.app.keys.keys()], ["Khóa 2"])
        self.c.delete(f"/api/admin/keys/{b}")
        self.assertEqual(self.app.keys.keys(), [])  # còn khóa nhưng đều tắt -> AI tắt, không dùng .env
        self.assertFalse(ai_service.vision_available())
        with mock.patch.object(ai_service, "test_key", return_value=(True, "")):
            self.assertTrue(self.c.post(f"/api/admin/keys/{a}/test").get_json()["ok"])
        self.assertEqual(self.c.put("/api/admin/settings", json={"models": "Gemini@2"}).status_code, 400)
        r = self.c.put("/api/admin/settings", json={"models": "m1, m2", "fast_models": ""}).get_json()
        self.assertEqual((r["models"], r["fast_models"]), ("m1,m2", ai_service.FAST_MODELS))
    def test_keys_rotate_when_quota_exceeded(self):
        self.add_key(self.KEY_A, "A"); self.add_key(self.KEY_B, "B")
        self.c.put("/api/admin/settings", json={"models": "m1"})
        quota = urllib.error.HTTPError("u", 429, "Too Many Requests", None, io.BytesIO(json.dumps({"error": {"details": [{"retryDelay": "600s"}]}}).encode()))
        with mock.patch("urllib.request.urlopen", side_effect=[quota, gemini_response("từ khóa B"), gemini_response("lại khóa B")]) as u:
            self.assertEqual(ai_service.ask("hỏi", [], None), ("từ khóa B", "gemini"))
            self.assertEqual(ai_service.ask("hỏi tiếp", [], None), ("lại khóa B", "gemini"))  # A đang hết lượt -> bỏ qua
        used = [c[0][0].get_header("X-goog-api-key") for c in u.call_args_list]
        self.assertEqual(used, [self.KEY_A, self.KEY_B, self.KEY_B])
        keys = {k["label"]: k for k in self.c.get("/api/admin/keys").get_json()["keys"]}
        self.assertEqual((keys["A"]["fail_count"], keys["B"]["ok_count"]), (1, 2))
        self.assertIn("m1", keys["A"]["cooling"]); self.assertIn("Hết hạn mức", keys["A"]["last_error"])
        self.c.patch(f"/api/admin/keys/{keys['A']['id']}", json={"reset": True})
        self.assertEqual(self.c.get("/api/admin/keys").get_json()["keys"][0]["cooling"], {})
    def test_env_key_imported_once(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": self.KEY_A}):
            app = create_app(self.config("env.db"))
            create_app(self.config("env.db"))
        self.assertEqual([k["label"] for k in app.keys.keys()], ["Khóa từ file .env"])

class AdminDataTests(Base):
    def test_samples_list_and_delete(self):
        self.authed(); self.make_admin()
        with mock.patch.multiple(ai_service, vision_available=mock.Mock(return_value=True), analyze_image=mock.Mock(return_value=ai_answer())):
            self.predict("other")
        s = self.c.get("/api/admin/samples").get_json()
        self.assertEqual((len(s), s[0]["class_name"], s[0]["plant"]), (1, "Mango___Anthracnose", "Xoài"))
        self.assertEqual(self.c.delete(f"/api/admin/samples/{s[0]['id']}").status_code, 200)
        self.assertEqual(self.dataset_files(), [])
        self.assertNotIn("mango", [p["id"] for p in self.c.get("/api/plants").get_json()])  # lớp sai bị xóa hết mẫu -> quên cây

class GeminiTests(unittest.TestCase):
    diag = dict(plant="Cà chua", disease="Bệnh mốc sương", confidence=0.9, remedy="Phun thuốc", healthy=0)
    def setUp(self): ai_service._cooldown.clear(); ai_service.configure(None)  # không dùng kho khóa của app ở test khác
    def test_switches_model_when_quota_exceeded(self):
        body = json.dumps({"error": {"code": 429, "details": [{"retryDelay": "120s"}]}}).encode()
        quota = urllib.error.HTTPError("u", 429, "Too Many Requests", None, io.BytesIO(body))
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k", "GEMINI_MODEL": "m1,m2"}), \
             mock.patch("urllib.request.urlopen", side_effect=[quota, gemini_response("từ m2"), gemini_response("lại m2")]) as u:
            self.assertEqual(ai_service.ask("hỏi", [], None), ("từ m2", "gemini"))
            self.assertEqual(ai_service.ask("hỏi", [], None), ("lại m2", "gemini"))  # m1 đang chờ hạn mức nên bỏ qua
        self.assertEqual([c[0][0].full_url.split("/models/")[1].split(":")[0] for c in u.call_args_list], ["m1", "m2", "m2"])
        self.assertGreater(ai_service._cooldown[("env", "m1")], time.time() + 100)
    def test_moderation_uses_fast_models_and_skips_slow_ones(self):
        ok = {"decision": "approve", "reason": "", "feedback": ""}
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k", "GEMINI_FAST_MODEL": "f1,f2", "GEMINI_MODEL": "m1"}), \
             mock.patch("urllib.request.urlopen", side_effect=[TimeoutError("chậm"), gemini_response(ok), gemini_response(ok)]) as u:
            self.assertEqual(ai_service.moderate("cảm ơn bác", kind="comment")["decision"], "approve")
            self.assertEqual(ai_service.moderate("bình luận nữa", kind="comment")["decision"], "approve")
        self.assertEqual([c[0][0].full_url.split("/models/")[1].split(":")[0] for c in u.call_args_list], ["f1", "f2", "f2"])
        self.assertEqual(u.call_args_list[0].kwargs["timeout"], 15)  # bình luận không chờ quá lâu
    def test_all_models_exhausted(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k", "GEMINI_MODEL": "m1"}), mock.patch("urllib.request.urlopen") as u:
            ai_service._cooldown[("env", "m1")] = time.time() + 60
            with self.assertRaises(ai_service.AIQuotaExceeded) as cm:
                ai_service.analyze_image(b"jpeg")
        u.assert_not_called(); self.assertIn("hết lượt", ai_service.reason(cm.exception))
    def test_gemini_request_and_reply(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), mock.patch("urllib.request.urlopen", return_value=gemini_response("Trả lời")) as u:
            reply, src = ai_service.ask("Phun gì?", [{"role": "user", "content": "chào"}, {"role": "assistant", "content": "chào bạn"}], self.diag)
        self.assertEqual((reply, src), ("Trả lời", "gemini"))
        body = json.loads(u.call_args[0][0].data)
        self.assertEqual([c["role"] for c in body["contents"]], ["user", "model", "user"])
        self.assertIn("Bệnh mốc sương", body["system_instruction"]["parts"][0]["text"])
    def test_gemini_error_falls_back_offline(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), mock.patch("urllib.request.urlopen", side_effect=OSError("mất mạng")):
            reply, src = ai_service.ask("Phun thuốc gì?", [], self.diag)
        self.assertEqual(src, "offline"); self.assertIn("Phun thuốc", reply)
    def test_reply_without_double_quotes(self):
        text = 'Lá bị "đốm vòng" 🍅, phun “mancozeb”  theo nhãn, «đừng» phun trưa.'
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), mock.patch("urllib.request.urlopen", return_value=gemini_response(text)):
            reply, src = ai_service.ask("hỏi", [], None)
        self.assertEqual((reply, src), ("Lá bị đốm vòng 🍅, phun mancozeb theo nhãn, đừng phun trưa.", "gemini"))
        self.assertNotIn("'", ai_service.ask("bệnh gì vậy", [], self.diag)[0])  # ngoại tuyến cũng không bọc tên bệnh trong dấu nháy
        md = "**Bệnh mốc sương** nha *bà con*:\n* Ngắt lá bệnh\n  * Phun **mancozeb**\n- Tưới gốc"
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), mock.patch("urllib.request.urlopen", return_value=gemini_response(md)):
            # giữ *...* / **...** để giao diện in đậm; "* " đầu dòng thành gạch đầu dòng
            self.assertEqual(ai_service.ask("hỏi", [], None)[0], "**Bệnh mốc sương** nha *bà con*:\n- Ngắt lá bệnh\n - Phun **mancozeb**\n- Tưới gốc")
    def test_gemini_retries_when_overloaded(self):
        busy = urllib.error.HTTPError("u", 503, "Service Unavailable", None, None)
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), mock.patch("time.sleep"), \
             mock.patch("urllib.request.urlopen", side_effect=[busy, gemini_response("Đã trả lời")]) as u:
            self.assertEqual(ai_service.ask("hỏi", [], None), ("Đã trả lời", "gemini"))
        self.assertEqual(u.call_count, 2)
    def test_analyze_image_sends_image_and_parses(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), mock.patch("urllib.request.urlopen", return_value=gemini_response(ai_answer(confidence=85))) as u:
            a = ai_service.analyze_image(b"jpeg", "Xoài")
        self.assertEqual((a["plant_vi"], a["confidence"], a["is_plant"]), ("Xoài", 0.85, True))
        body = json.loads(u.call_args[0][0].data)
        self.assertIn("inline_data", body["contents"][0]["parts"][0])
        self.assertIn("cây Xoài", body["contents"][0]["parts"][1]["text"])
        cfg = body["generationConfig"]
        self.assertEqual(cfg["responseMimeType"], "application/json")
        self.assertEqual(cfg["responseSchema"]["propertyOrdering"][:2], ["is_plant", "symptoms"])  # quan sát trước khi kết luận
    def test_moderate(self):
        self.assertEqual(ai_service.moderate("bài viết")["decision"], "review")  # chưa có key
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}):
            with mock.patch("urllib.request.urlopen", return_value=gemini_response({"decision": "reject", "reason": "spam", "feedback": "Không quảng cáo"})):
                self.assertEqual(ai_service.moderate("vay tiền nhanh")["feedback"], "Không quảng cáo")
            blocked = mock.MagicMock(); blocked.__enter__.return_value = io.BytesIO(b'{"promptFeedback": {"blockReason": "SAFETY"}}')
            with mock.patch("urllib.request.urlopen", return_value=blocked):
                self.assertEqual(ai_service.moderate("nội dung xấu", b"img")["decision"], "reject")
            with mock.patch("urllib.request.urlopen", return_value=gemini_response({"decision": "lung tung", "reason": "", "feedback": ""})):
                self.assertEqual(ai_service.moderate("bài")["decision"], "review")

class FakeModel:
    def __init__(self, probs): self.probs = probs
    def predict(self, x, verbose=0): return np.array([self.probs])

class ChatRatingTests(Base):
    def test_chat_with_diagnosis_and_history(self):
        self.authed(); did = self.predict().get_json()["diagnosis_id"]
        r = self.c.post("/api/chat", json={"message": "Nên phun thuốc gì?", "diagnosis_id": did}); self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["reply"]); self.assertEqual(r.get_json()["source"], "offline")
        h = self.c.get(f"/api/chat?diagnosis_id={did}").get_json()
        self.assertEqual([m["role"] for m in h], ["user", "assistant"]); self.assertEqual(self.c.get("/api/chat").get_json(), [])
    def test_chat_with_image(self):
        self.authed()
        with mock.patch.object(ai_service, "ask", return_value=("Lá bị đốm nâu, có thể là đốm lá.", "gemini")) as ask:
            r = self.c.post("/api/chat", data={"message": "", "image": (leaf(), "l.jpg")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(ask.call_args[0][3])  # ảnh (bytes) được chuyển cho AI
        self.assertIn("xem ảnh này", ask.call_args[0][0])  # không có chữ -> câu hỏi mặc định
        h = self.c.get("/api/chat").get_json()
        self.assertTrue(h[0]["image_url"].startswith("/uploads/chats/")); self.assertIsNone(h[1]["image_url"])
        self.assertEqual(self.get_status(h[0]["image_url"]), 200)
        self.as_user2(); self.assertEqual(self.get_status(h[0]["image_url"]), 404)  # người khác không xem được
    def test_chat_without_diagnosis(self):
        self.authed(); self.assertEqual(self.c.post("/api/chat", json={"message": "xin chào"}).status_code, 200)
    def test_chat_empty_and_too_long(self):
        self.authed()
        self.assertEqual(self.c.post("/api/chat", json={"message": "  "}).status_code, 400)
        self.assertEqual(self.c.post("/api/chat", json={"message": "x" * 1001}).status_code, 400)
    def test_chat_other_users_diagnosis_forbidden(self):
        self.authed(); did = self.predict().get_json()["diagnosis_id"]
        self.as_user2()
        self.assertEqual(self.c.post("/api/chat", json={"message": "hi", "diagnosis_id": did}).status_code, 404)
        self.assertEqual(self.c.get(f"/api/chat?diagnosis_id={did}").status_code, 404)
        self.assertEqual(self.c.get(f"/api/diagnoses/{did}").status_code, 404)
    def test_rating_ok_and_replace(self):
        self.authed(); did = self.predict().get_json()["diagnosis_id"]
        self.assertEqual(self.c.post("/api/rating", json={"diagnosis_id": did, "stars": 4, "comment": "tốt"}).status_code, 201)
        self.assertEqual(self.c.post("/api/rating", json={"diagnosis_id": did, "stars": 5}).status_code, 201)
        self.assertEqual(self.sql("select stars from ratings"), [(5,)])
    def test_rating_validation(self):
        self.authed()
        for s in (0, 6, "5", None, True): self.assertEqual(self.c.post("/api/rating", json={"stars": s}).status_code, 400, s)
        self.assertEqual(self.c.post("/api/rating", json={"stars": 3}).status_code, 400)  # phải gắn với một kết quả tra cứu
        self.assertEqual(self.c.post("/api/rating", json={"stars": 3, "diagnosis_id": 999}).status_code, 404)
    def test_ratings_summary(self):
        self.authed(); a, b, c = (self.predict(img=leaf((i, 120, 40))).get_json()["diagnosis_id"] for i in (10, 20, 30))
        self.c.post("/api/rating", json={"diagnosis_id": a, "stars": 5, "comment": "Chính xác"})
        self.c.post("/api/rating", json={"diagnosis_id": b, "stars": 2})
        r = self.c.get("/api/ratings").get_json()
        self.assertEqual((r["count"], r["avg"], r["dist"]["5"], r["dist"]["2"]), (2, 3.5, 1, 1))
        self.assertEqual([p["id"] for p in r["pending"]], [c])
        self.assertEqual(r["items"][1]["comment"], "Chính xác"); self.assertEqual(r["items"][0]["username"], "nguyenvan")
        self.assertEqual({h["id"]: h["stars"] for h in self.c.get("/api/history").get_json()}, {a: 5, b: 2, c: None})

def fake_days(n=9, **kw):
    """Dự báo giả: n ngày từ hôm qua, mỗi ngày cùng thông số (ghi đè bằng kw)."""
    from datetime import date, timedelta
    base = dict(tmin=20, tmax=28, tmean=24, rh=70, wet_hours=2, rain=0.0, wind=10, code=1, sun=8)
    base.update(kw)
    return [dict(base, date=(date.today() + timedelta(days=i - 1)).isoformat()) for i in range(n)]

def fake_report(**kw):
    """weather.report giả: các ngày từ fake_days, kèm thời tiết hiện tại, 24 giờ tới, sáng/chiều/tối."""
    days = fake_days(**kw)
    hourly = [dict(time=f"{days[1]['date']}T{h:02d}:00", temp=25.0, rh=80, rain=0.5 if h > 14 else 0.0, rain_prob=40, code=61 if h > 14 else 2, is_day=int(6 <= h < 18))
              for h in range(24)]
    return dict(days=days, hourly=hourly, current=dict(time=f"{days[1]['date']}T09:00", temp=26.4, feels=28.0, rh=78, rain=0.0, code=2, wind=8.5, is_day=1),
                parts=weather.day_parts(hourly, days[1]["date"]))

class WeatherRuleTests(unittest.TestCase):
    def test_report_parses_current_hourly_parts(self):
        """Dữ liệu thô Open-Meteo -> hiện tại, 24 giờ kể từ giờ hiện tại, sáng/chiều/tối hôm nay, mặt trời mọc/lặn, UV."""
        hrs = [f"2026-10-28T{h:02d}:00" for h in range(24)] + [f"2026-10-29T{h:02d}:00" for h in range(24)]
        code = lambda t: 95 if t.endswith("T15:00") else 61 if "T1" in t and int(t[11:13]) >= 13 else 1
        raw = {"current": {"time": "2026-10-28T09:45", "temperature_2m": 28.6, "apparent_temperature": 31.5, "relative_humidity_2m": 58,
                           "precipitation": 0, "weather_code": 0, "wind_speed_10m": 9.1, "is_day": 1},
               "hourly": {"time": hrs, "temperature_2m": [20 + int(t[11:13]) % 12 for t in hrs], "relative_humidity_2m": [80] * 48,
                          "precipitation": [0.2] * 48, "precipitation_probability": [30] * 48, "weather_code": [code(t) for t in hrs],
                          "is_day": [int(6 <= int(t[11:13]) < 18) for t in hrs]},
               "daily": {"time": ["2026-10-28", "2026-10-29"], "weather_code": [95, 1], "temperature_2m_max": [31, 30], "temperature_2m_min": [24, 23],
                         "precipitation_sum": [4.8, 4.8], "precipitation_probability_max": [70, 30], "wind_speed_10m_max": [12, 10],
                         "sunshine_duration": [3600, 7200], "uv_index_max": [7.1, 6], "sunrise": ["2026-10-28T05:57", "2026-10-29T05:58"],
                         "sunset": ["2026-10-28T17:23", "2026-10-29T17:22"]}}
        weather._cache.clear()
        with mock.patch.object(weather, "fetch_forecast", return_value=raw) as f:
            r = weather.report(21.0, 105.8); weather.report(21.01, 105.82)
        self.assertEqual(f.call_count, 1)  # cùng ô 0.1° -> dùng cache
        weather._cache.clear()
        self.assertEqual((r["current"]["temp"], r["current"]["feels"], r["current"]["is_day"]), (28.6, 31.5, 1))
        self.assertEqual((len(r["hourly"]), r["hourly"][0]["time"], r["hourly"][-1]["time"]), (24, "2026-10-28T09:00", "2026-10-29T08:00"))
        self.assertEqual([(p["key"], p["code"]) for p in r["parts"]], [("sang", 1), ("chieu", 95), ("toi", 61)])  # có dông trong buổi -> cả buổi dông
        self.assertEqual({k: r["days"][0][k] for k in ("sunrise", "sunset", "uv", "rain_prob")}, dict(sunrise="05:57", sunset="17:23", uv=7.1, rain_prob=70))

    def test_day_stats_aggregates_hourly(self):
        raw = {"hourly": {"time": [f"2026-10-27T{h:02d}:00" for h in range(24)], "temperature_2m": [20 + h % 5 for h in range(24)],
                          "relative_humidity_2m": [95 if h < 10 else 70 for h in range(24)], "precipitation": [0.5] * 24},
               "daily": {"time": ["2026-10-27"], "weather_code": [61], "wind_speed_10m_max": [18.5], "sunshine_duration": [7200]}}
        d = weather.day_stats(raw)
        self.assertEqual(len(d), 1)
        self.assertEqual((d[0]["tmin"], d[0]["tmax"], d[0]["wet_hours"], d[0]["rain"], d[0]["code"], d[0]["wind"], d[0]["sun"]), (20, 24, 10, 12.0, 61, 18.5, 2.0))
    def test_late_blight_high_when_cool_and_wet(self):
        alerts = {a["key"]: a for a in weather.assess(fake_days(tmean=18, tmin=14, tmax=22, rh=92, wet_hours=12, rain=6), {"tomato"})}
        self.assertEqual(alerts["moc_suong"]["level"], "cao"); self.assertTrue(alerts["moc_suong"]["mine"]); self.assertEqual(len(alerts["moc_suong"]["days"]), 5)
        self.assertNotIn("nhen_do", alerts); self.assertNotIn("phan_trang", alerts)
    def test_spider_mite_when_hot_and_dry_and_levels(self):
        days = fake_days(tmax=34, tmean=30, rh=55, rain=0)
        for d in days[3:]:  # chỉ 2 ngày đầu (hôm nay, ngày mai) nóng khô -> mức vừa
            d.update(tmax=27, tmean=24, rh=80)
        alerts = {a["key"]: a for a in weather.assess(days, set())}
        self.assertEqual(alerts["nhen_do"]["level"], "vua"); self.assertFalse(alerts["nhen_do"]["mine"])
        self.assertEqual(alerts["chich_hut"]["level"], "vua")
    def test_mine_sorted_first_and_storm(self):
        days = fake_days(tmean=18, tmin=14, tmax=22, rh=92, wet_hours=12, rain=35)  # mưa to + mát ẩm: mốc sương (cà chua) và mưa gió (mọi cây)
        alerts = weather.assess(days, {"squash"})
        keys = [a["key"] for a in alerts]
        self.assertLess(keys.index("mua_gio"), keys.index("moc_suong")); self.assertLess(keys.index("oc"), keys.index("moc_suong"))  # cùng mức cao: quy tắc chung (mọi cây) xếp trước cây không phải của tôi
        self.assertTrue(alerts[0]["mine"]); self.assertFalse([a for a in alerts if a["key"] == "moc_suong"][0]["mine"])
        self.assertEqual([a["level"] for a in alerts], sorted((a["level"] for a in alerts), key={"cao": 0, "vua": 1, "thap": 2}.get))
    def test_no_alert_mild_weather(self):
        self.assertEqual(weather.assess(fake_days(tmean=24, tmax=27, rh=70, rain=1.5), set()), [])
    def test_distance(self):
        self.assertAlmostEqual(weather.distance_km(21.03, 105.85, 10.78, 106.70), 1137, delta=15)  # Hà Nội - TP.HCM

class ReviewTests(Base):
    """Báo kết quả sai và duyệt nhãn mẫu AI trước khi huấn luyện lại."""
    def ai(self, **kw):
        return mock.patch.multiple(ai_service, vision_available=mock.Mock(return_value=True), analyze_image=mock.Mock(**kw))
    def admin_session(self):
        """Đăng nhập tài khoản quản trị (user2) trên client riêng, phiên của người dùng chính giữ nguyên."""
        a = self.app.test_client()
        a.post("/api/register", json={"username": "quantri", "email": "qt@b.vn", "password": "matkhau123", "phone": "0977777777"})
        code = self.sql("select code from email_codes where email='qt@b.vn'")[0][0]
        a.post("/api/verify", json={"email": "qt@b.vn", "code": code})
        self.make_admin("quantri")
        a.post("/api/login", json={"username": "quantri", "password": "matkhau123"})
        return a
    def test_report_and_accept_adds_reviewed_sample(self):
        self.authed()
        did = self.predict("tomato").get_json()["diagnosis_id"]  # DEMO: mô hình, chưa có mẫu AI
        self.assertIsNone(self.c.get(f"/api/diagnoses/{did}/report").get_json())
        self.assertEqual(self.c.post(f"/api/diagnoses/{did}/report", json={"class_name": "Không_có___lớp"}).status_code, 400)
        self.assertEqual(self.c.post(f"/api/diagnoses/{did}/report", json={"note": "sai"}).status_code, 400)  # thiếu nhãn
        r = self.c.post(f"/api/diagnoses/{did}/report", json={"class_name": "Tomato___Late_blight", "note": "cán bộ xem rồi"})
        self.assertEqual(r.status_code, 200)
        self.c.post(f"/api/diagnoses/{did}/report", json={"class_name": "Tomato___Early_blight"})  # báo lại: sửa báo cáo cũ
        rep = self.c.get(f"/api/diagnoses/{did}/report").get_json()
        self.assertEqual((rep["status"], rep["class_name"], rep["disease"]), ("open", "Tomato___Early_blight", "Bệnh đốm vòng (mốc sương sớm)"))
        self.assertEqual(self.sql("select count(*) from reports"), [(1,)])
        a = self.admin_session()
        self.assertEqual(a.get("/api/admin/stats").get_json()["reports_open"], 1)
        [item] = a.get("/api/admin/reports").get_json()
        self.assertEqual((item["class_name"], item["kind"]), ("Tomato___Early_blight", "leaf"))
        with mock.patch("push.send") as p:
            self.assertEqual(a.post(f"/api/admin/reports/{item['id']}", json={"action": "accept", "answer": "Đúng là đốm vòng"}).get_json()["status"], "accepted")
        d = self.c.get(f"/api/diagnoses/{did}").get_json()
        self.assertEqual((d["raw"], d["disease"]), ("Tomato___Early_blight", "Bệnh đốm vòng (mốc sương sớm)"))
        self.assertTrue(d["details"]["notes"][0].startswith("Quản trị viên đã sửa"))
        self.assertEqual(self.sql("select class_name, status from ai_samples"), [("Tomato___Early_blight", "approved")])  # ảnh thực tế vào dữ liệu
        self.assertEqual(self.dataset_files(), ["Tomato___Early_blight"])
        self.assertIn("Quản trị viên đã sửa thành", self.sql("select content from notifications")[0][0])
        self.assertEqual(p.call_args[0][2], [self.sql("select id from users where username='nguyenvan'")[0][0]])  # đẩy về điện thoại
        self.assertEqual(self.c.get(f"/api/diagnoses/{did}/report").get_json()["status"], "accepted")
        self.assertEqual(a.post(f"/api/admin/reports/{item['id']}", json={"action": "reject"}).status_code, 400)  # đã xử lý
        self.as_user2(); self.assertEqual(self.c.post(f"/api/diagnoses/{did}/report", json={"disease": "x"}).status_code, 404)
    def test_reject_free_text_report(self):
        self.authed()
        did = self.predict("tomato").get_json()["diagnosis_id"]
        self.assertEqual(self.c.post(f"/api/diagnoses/{did}/report", json={"plant": "Lúa", "disease": "Đạo ôn"}).status_code, 200)
        a = self.admin_session()
        [item] = a.get("/api/admin/reports").get_json()
        self.assertIsNone(item["class_name"])
        self.assertEqual(a.post(f"/api/admin/reports/{item['id']}", json={"action": "accept"}).status_code, 400)  # tự ghi: phải chọn nhãn
        a.post(f"/api/admin/reports/{item['id']}", json={"action": "reject", "answer": "Ảnh là lá cà chua"})
        self.assertEqual(a.get("/api/admin/reports?status=done").get_json()[0]["status"], "rejected")
        self.assertIn("giữ nguyên", self.sql("select content from notifications")[0][0])
        self.assertEqual(self.sql("select count(*) from ai_samples"), [(0,)])
    def test_known_classes_not_in_review_queue(self):
        self.authed()
        with self.ai(return_value=ai_answer(plant_vi="Cà chua", plant_en="Tomato", disease_vi="Mốc sương", disease_en="Late blight")):
            self.predict("auto")  # AI gán đúng một lớp mô hình đã có (Tomato___Late_blight)
        with self.ai(return_value=ai_answer()):
            self.predict("other", leaf((200, 40, 40)))  # bệnh mới: Mango___Anthracnose
        self.assertEqual(len(self.sql("select id from ai_samples where status='pending'")), 2)
        a = self.admin_session()
        self.assertEqual([x["class_name"] for x in a.get("/api/admin/samples").get_json()], ["Mango___Anthracnose"])
        self.assertEqual(a.get("/api/admin/stats").get_json()["samples_pending"], 1)
    def test_ai_samples_wait_for_review_and_relabel(self):
        self.authed()
        with self.ai(return_value=ai_answer()):
            did = self.predict("other").get_json()["diagnosis_id"]
        self.assertEqual(self.sql("select status from ai_samples"), [("pending",)])
        a = self.admin_session()
        self.assertEqual(a.get("/api/admin/stats").get_json()["samples_pending"], 1)
        [s] = a.get("/api/admin/samples").get_json()
        self.assertEqual(a.get("/api/admin/samples?status=approved").get_json(), [])
        self.assertEqual(a.post(f"/api/admin/samples/{s['id']}", json={"action": "relabel", "class_name": "Pest_khong_co"}).status_code, 400)
        self.assertEqual(a.post(f"/api/admin/samples/{s['id']}", json={"action": "relabel", "class_name": "Tomato___Leaf_Mold"}).status_code, 200)
        self.assertEqual(self.sql("select class_name, status from ai_samples"), [("Tomato___Leaf_Mold", "approved")])
        self.assertEqual(self.dataset_files(), ["Tomato___Leaf_Mold"])  # ảnh chuyển sang thư mục lớp mới
        self.assertEqual(self.sql("select count(*) from ai_classes"), [(0,)])  # lớp xoài không còn mẫu: quên lớp
        self.assertEqual(self.c.get(f"/api/diagnoses/{did}").get_json()["disease"], "Bệnh mốc lá")
        with self.ai(return_value=ai_answer()):
            self.predict("other", leaf((200, 40, 40)))
        ids = [x["id"] for x in a.get("/api/admin/samples").get_json()]
        self.assertEqual(a.post("/api/admin/samples/approve", json={"ids": ids}).get_json()["approved"], 1)
        out = os.path.join(self.tmp.name, "xuat")
        r = self.app.test_cli_runner().invoke(args=["export-dataset", out])
        self.assertIn("2 ảnh", r.output)
        self.assertEqual(sorted(os.listdir(out)), [".xuat-tu-dataset-ai", "Mango___Anthracnose", "Tomato___Leaf_Mold"])
        other = os.path.join(self.tmp.name, "khac"); os.makedirs(other); open(os.path.join(other, "a.txt"), "w").close()
        self.assertNotEqual(self.app.test_cli_runner().invoke(args=["export-dataset", other]).exit_code, 0)  # không xóa thư mục lạ
        self.assertTrue(os.path.exists(os.path.join(other, "a.txt")))

class LibraryTests(Base):
    def test_library_lists_diseases_and_pests(self):
        self.authed()
        j = self.c.get("/api/library").get_json()
        self.assertTrue(any(d["class_name"] == "Tomato___Late_blight" and d["disease"] == "Bệnh mốc sương (sương mai)" for d in j["diseases"]))
        self.assertEqual(len(j["diseases"]), 38)  # đủ các lớp bệnh lá của mô hình, kể cả lá khỏe (như sâu hại có cả thiên địch)
        self.assertTrue(next(d for d in j["diseases"] if d["class_name"] == "Tomato___healthy")["healthy"])
        self.assertIn({"id": "tomato", "name": "Cà chua"}, j["plants"])
        self.assertEqual(len(j["pests"]), len(pests.PESTS))
        self.assertTrue(any(p["beneficial"] for p in j["pests"]))
        self.assertEqual(self.get_status("/api/library/image?c=Kh%C3%B4ng___c%C3%B3"), 404)
        with mock.patch.multiple(ai_service, vision_available=mock.Mock(return_value=True), analyze_image=mock.Mock(return_value=ai_answer())):
            self.predict("other")  # ảnh thử: AI học lớp Xoài, mẫu chờ duyệt
        names = lambda: [d["class_name"] for d in self.c.get("/api/library").get_json()["diseases"]]
        self.assertNotIn("Mango___Anthracnose", names())  # chưa duyệt: không hiện, ảnh của người dùng cũng không lộ ra
        self.assertEqual(self.get_status("/api/library/image?c=Mango___Anthracnose"), 404)
        self.run_sql("UPDATE ai_samples SET status='approved'")
        self.assertIn("Mango___Anthracnose", names())
        self.assertEqual(self.get_status("/api/library/image?c=Mango___Anthracnose"), 200)
        self.c.post("/api/logout"); self.assertEqual(self.c.get("/api/library").status_code, 401)

class PushTests(Base):
    def test_subscribe_and_push_on_notify(self):
        self.authed()
        self.assertTrue(self.c.get("/api/push/key").get_json()["key"])
        self.assertEqual(self.c.post("/api/push/test").status_code, 400)  # chưa bật trên thiết bị nào
        self.assertEqual(self.c.post("/api/push/subscribe", json={"endpoint": "http://x", "keys": {}}).status_code, 400)
        sub = {"endpoint": "https://push.example.com/send/abc123", "keys": {"p256dh": "BKey", "auth": "auth1"}}
        self.assertEqual(self.c.post("/api/push/subscribe", json=sub).status_code, 200)
        self.c.post("/api/push/subscribe", json=sub)  # đăng ký lại cùng thiết bị: không trùng
        self.assertEqual(self.sql("select count(*) from push_subs"), [(1,)])
        sent = []
        class Now:  # chạy việc gửi ngay trong luồng test
            def submit(self, f, *a): f(*a)
        resp = mock.Mock(status_code=410)
        def fake(info, data, **kw):
            sent.append((info["endpoint"], json.loads(data)))
            raise pywebpush.WebPushException("gone", response=resp)
        with mock.patch.object(push_mod, "_pool", Now()), mock.patch("pywebpush.webpush", side_effect=fake):
            self.assertEqual(self.c.post("/api/push/test").status_code, 200)
        self.assertEqual(sent[0][0], sub["endpoint"])
        self.assertEqual(sent[0][1]["url"], "/notifications")
        self.assertEqual(self.sql("select count(*) from push_subs"), [(0,)])  # dịch vụ đẩy báo đã hủy (410): xóa thiết bị
        self.c.post("/api/push/subscribe", json=sub)
        self.c.post("/api/push/unsubscribe", json={"endpoint": sub["endpoint"]})
        self.assertEqual(self.sql("select count(*) from push_subs"), [(0,)])

class CarePlanTests(Base):
    def plan(self, raw):
        i = knowledge.info(raw); return care.plan(i["disease"], raw, i["remedy"], i["healthy"])
    def test_each_disease_group_has_its_own_schedule(self):
        kinds = {raw: self.plan(raw)["kind"] for raw in ("Squash___Powdery_mildew", "Tomato___Late_blight", "Tomato___Early_blight",
                 "Corn_(maize)___Common_rust_", "Peach___Bacterial_spot", "Tomato___Tomato_Yellow_Leaf_Curl_Virus", "Tomato___Spider_mites Two-spotted_spider_mite")}
        self.assertEqual(kinds, {"Squash___Powdery_mildew": "phan_trang", "Tomato___Late_blight": "suong_mai", "Tomato___Early_blight": "nam",
                                 "Corn_(maize)___Common_rust_": "gi_sat", "Peach___Bacterial_spot": "vi_khuan",
                                 "Tomato___Tomato_Yellow_Leaf_Curl_Virus": "virus", "Tomato___Spider_mites Two-spotted_spider_mite": "nhen"})
        # nhịp khác nhau: mốc sương kiểm tra 2-3 ngày/lần, phun lại sau 5 ngày; gỉ sắt phun lại sau 10 ngày
        self.assertEqual([s["days"] for s in self.plan("Tomato___Late_blight")["steps"][:2]], [2, 5])
        self.assertEqual(self.plan("Corn_(maize)___Common_rust_")["steps"][1]["days"], 10)
        # tên thuốc lấy từ hướng xử lý của chính bệnh đó; virus thì không nhắc phun thuốc trừ bệnh
        self.assertIn("lưu huỳnh", self.plan("Squash___Powdery_mildew")["steps"][1]["content"])
        self.assertIn("metalaxyl", self.plan("Tomato___Late_blight")["steps"][1]["content"])
        self.assertFalse(any("Phun lần" in s["content"] for s in self.plan("Tomato___Tomato_Yellow_Leaf_Curl_Virus")["steps"]))
        self.assertFalse(any("Phun lần" in s["content"] for s in self.plan("Grape___Esca_(Black_Measles)")["steps"]))  # chưa có thuốc đặc trị
    def test_ai_names_and_pests(self):
        self.assertEqual(care.plan("Cháy lá do điều kiện môi trường bất lợi (thiếu nước)")["kind"], "moi_truong")
        self.assertEqual(care.plan("Bệnh mốc sương sớm (đốm vòng)")["kind"], "nam")  # 'sớm' là đốm vòng, không phải sương mai
        self.assertEqual(care.plan("Bệnh lạ")["kind"], "chung")
        self.assertEqual(care.plan("Bệnh đạo ôn")["kind"], "nam")
        self.assertEqual(care.plan("Bọ đục vỏ Tần bì")["kind"], "duc_than")  # AI gọi tên sâu trong luồng ảnh lá
        self.assertEqual(care.plan("Chưa xác định được loài", pest=True)["kind"], "sau_chung")
        self.assertEqual(care.plan(pest_raw="Nilaparvata lugens")["kind"], "chich_hut")
        self.assertEqual(care.plan("Bọ rùa đỏ", healthy=True, pest_raw="Coccinella transversalis")["kind"], "thien_dich")
        self.assertEqual(care.plan("Khỏe mạnh", healthy=True)["kind"], "khoe")
    def test_api(self):
        self.assertEqual(self.c.get("/api/care-plan?disease=x").status_code, 401)
        self.authed(); did = self.predict().get_json()["diagnosis_id"]
        self.mark_sick("squash", "Bí", "Bệnh phấn trắng")
        r = self.c.get(f"/api/care-plan?diagnosis_id={did}").get_json()
        self.assertEqual(r["kind"], "phan_trang"); self.assertTrue(r["note"] and r["steps"])
        self.assertEqual(self.c.get("/api/care-plan?disease=Bệnh gỉ sắt").get_json()["kind"], "gi_sat")
        self.as_user2()
        self.assertEqual(self.c.get(f"/api/care-plan?diagnosis_id={did}").status_code, 404)  # không xem được của người khác

class JournalTests(Base):
    def diag(self):
        return self.predict(img=leaf((120, 60, 20))).get_json()["diagnosis_id"]
    def due(self, days):
        from datetime import datetime, timedelta, timezone
        return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    def at(self, days):  # cho query string: dấu + của múi giờ phải mã hóa
        return urllib.parse.quote(self.due(days))
    def test_agenda_by_day(self):
        """Lịch việc theo khoảng ngày: việc cần làm (kể cả các lần lặp lại sắp tới), việc đã làm; giới hạn khoảng thời gian."""
        self.authed()
        tid = self.c.post("/api/treatments", json={"plant": "Cà chua", "disease": "Đốm vòng", "reminders": [
            {"content": "Kiểm tra lá", "due": self.due(1), "repeat_days": 3}, {"content": "Phun lần 2", "due": self.due(5)},
            {"content": "Đánh giá", "due": self.due(40)}]}).get_json()["id"]
        self.c.post(f"/api/treatments/{tid}/logs", json={"kind": "phun", "content": "Phun mancozeb lần 1"})
        a = self.c.get(f"/api/agenda?from={self.at(-1)}&to={self.at(10)}").get_json()
        tasks = [(t["content"], t["projected"]) for t in a["tasks"]]
        self.assertEqual(tasks.count(("Kiểm tra lá", False)), 1); self.assertEqual(tasks.count(("Kiểm tra lá", True)), 3)  # ngày 1, rồi 4, 7, 10
        self.assertIn(("Phun lần 2", False), tasks); self.assertNotIn("Đánh giá", [t[0] for t in tasks])  # ngoài khoảng
        self.assertEqual([l["content"] for l in a["logs"]], ["Phun mancozeb lần 1"]); self.assertEqual(a["tasks"], sorted(a["tasks"], key=lambda t: t["due"]))
        self.assertEqual(self.c.get(f"/api/agenda?from={self.at(2)}&to={self.at(-2)}").status_code, 400)
        self.assertEqual(self.c.get(f"/api/agenda?from={self.at(0)}&to={self.at(90)}").status_code, 400)  # quá 62 ngày
        self.as_user2()
        self.assertEqual(self.c.get(f"/api/agenda?from={self.at(-1)}&to={self.at(10)}").get_json(), {"tasks": [], "logs": []})
    def test_create_from_diagnosis_with_reminders(self):
        self.authed(); did = self.diag()
        r = self.c.post("/api/treatments", json={"diagnosis_id": did, "name": "Luống cà chua", "reminders": [
            {"content": "Kiểm tra lại cây", "due": self.due(3)}, {"content": "Phun lần 2", "due": self.due(7), "repeat_days": 7}]})
        self.assertEqual(r.status_code, 201); tid = r.get_json()["id"]
        self.assertEqual(self.c.post("/api/treatments", json={"diagnosis_id": did}).status_code, 409)  # mỗi kết quả một nhật ký đang theo dõi
        lst = self.c.get("/api/treatments").get_json()
        self.assertEqual((lst[0]["id"], lst[0]["name"], lst[0]["pending"], lst[0]["overdue"], lst[0]["next"]["content"]), (tid, "Luống cà chua", 2, 0, "Kiểm tra lại cây"))
        self.assertTrue(lst[0]["diagnosis"]["image_url"]); self.assertTrue(lst[0]["plant"]); self.assertTrue(lst[0]["disease"])
        d = self.c.get(f"/api/treatments/{tid}").get_json()
        self.assertEqual([x["content"] for x in d["reminders"]], ["Kiểm tra lại cây", "Phun lần 2"]); self.assertEqual(d["entries"], []); self.assertTrue(d["remedy"])
        self.assertEqual(self.c.get("/api/me").get_json()["stats"]["treatments"], 1)
    def test_create_manual_and_validation(self):
        self.authed()
        self.assertEqual(self.c.post("/api/treatments", json={"plant": "Xoài"}).status_code, 400)
        self.assertEqual(self.c.post("/api/treatments", json={"diagnosis_id": 999}).status_code, 404)
        self.assertEqual(self.c.post("/api/treatments", json={"plant": "Xoài", "disease": "Thán thư", "reminders": [{"content": "x", "due": "hôm qua"}]}).status_code, 400)
        self.assertEqual(self.c.post("/api/treatments", json={"plant": "Xoài", "disease": "Thán thư", "reminders": [{"content": "", "due": self.due(1)}]}).status_code, 400)
        r = self.c.post("/api/treatments", json={"plant": "Xoài", "disease": "Thán thư"}); self.assertEqual(r.status_code, 201)
        self.assertEqual(self.sql("select count(*) from treatments"), [(1,)])
    def test_logs_with_image_owner_only_and_delete(self):
        self.authed(); tid = self.c.post("/api/treatments", json={"plant": "Xoài", "disease": "Thán thư"}).get_json()["id"]
        self.assertEqual(self.c.post(f"/api/treatments/{tid}/logs", json={"kind": "phun", "content": "  "}).status_code, 400)
        self.assertEqual(self.c.post(f"/api/treatments/{tid}/logs", json={"kind": "bay", "content": "x"}).status_code, 400)
        r = self.c.post(f"/api/treatments/{tid}/logs", data={"kind": "phun", "content": "Phun mancozeb", "image": (leaf(), "p.jpg")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 201); url = r.get_json()["image_url"]; self.assertTrue(url.startswith("/uploads/treatments/"))
        self.c.post(f"/api/treatments/{tid}/logs", json={"kind": "kiemtra", "content": "Vết bệnh khô lại"})
        d = self.c.get(f"/api/treatments/{tid}").get_json()
        self.assertEqual([e["kind"] for e in d["entries"]], ["kiemtra", "phun"]); self.assertEqual(d["logs"], 2)
        self.assertEqual(self.get_status(url), 200)
        lid = d["entries"][1]["id"]
        self.as_user2()
        self.assertEqual(self.get_status(url), 404); self.assertEqual(self.c.get(f"/api/treatments/{tid}").status_code, 404)
        self.assertEqual(self.c.delete(f"/api/logs/{lid}").status_code, 404); self.assertEqual(self.c.delete(f"/api/treatments/{tid}").status_code, 404)
        self.c.post("/api/logout"); self.login()
        self.assertEqual(self.c.delete(f"/api/logs/{lid}").status_code, 200)
        self.assertEqual(self.get_status(url), 404)  # ảnh bị xóa cùng ghi chép
        self.assertEqual(self.c.delete(f"/api/treatments/{tid}").status_code, 200)
        self.assertEqual(self.sql("select count(*) from treatment_logs"), [(0,)])
    def test_reminder_done_logs_and_repeats(self):
        self.authed(); tid = self.c.post("/api/treatments", json={"plant": "Xoài", "disease": "Thán thư"}).get_json()["id"]
        self.assertEqual(self.c.post(f"/api/treatments/{tid}/reminders", json={"content": "Phun thuốc", "due": self.due(-1), "repeat_days": 7}).status_code, 201)
        self.assertEqual(self.c.post(f"/api/treatments/{tid}/reminders", json={"content": "Kiểm tra", "due": self.due(1)}).status_code, 201)
        self.assertEqual(self.c.post(f"/api/treatments/{tid}/reminders", json={"content": "x", "due": self.due(1), "repeat_days": 99}).status_code, 400)
        due = self.c.get("/api/reminders").get_json()
        self.assertEqual([(r["content"], r["overdue"]) for r in due], [("Phun thuốc", True), ("Kiểm tra", False)])
        me = self.c.get("/api/me").get_json(); self.assertEqual(me["due"], 1)
        n = self.c.get("/api/notifications").get_json()  # quá hạn -> thông báo (một lần)
        self.assertEqual(len(n), 1); self.assertIn("Phun thuốc", n[0]["content"]); self.assertEqual(n[0]["link"], f"/journal/{tid}")
        self.c.get("/api/me"); self.assertEqual(len(self.c.get("/api/notifications").get_json()), 1)
        rid = due[0]["id"]
        self.assertEqual(self.c.put(f"/api/reminders/{rid}", json={"done": 1}).status_code, 200)
        d = self.c.get(f"/api/treatments/{tid}").get_json()
        self.assertEqual(d["entries"][0]["content"], "Đã làm: Phun thuốc"); self.assertEqual(d["entries"][0]["kind"], "phun")
        rm = [r for r in d["reminders"] if r["id"] == rid][0]
        self.assertEqual(rm["done"], 0); self.assertGreater(rm["due"], self.due(6)[:19].replace("T", " "))  # lặp: hẹn lại sau 7 ngày, chưa xong
        rid2 = [r for r in d["reminders"] if r["content"] == "Kiểm tra"][0]["id"]
        self.c.put(f"/api/reminders/{rid2}", json={"done": 1})
        self.assertEqual([r["done"] for r in self.c.get(f"/api/treatments/{tid}").get_json()["reminders"] if r["id"] == rid2], [1])
        self.c.put(f"/api/reminders/{rid2}", json={"done": 0})
        self.assertEqual(self.c.get(f"/api/treatments/{tid}").get_json()["pending"], 2)
        self.assertEqual(self.c.delete(f"/api/reminders/{rid2}").status_code, 200); self.assertEqual(self.c.delete(f"/api/reminders/{rid2}").status_code, 404)
    def test_close_treatment_cancels_reminders(self):
        self.authed(); tid = self.c.post("/api/treatments", json={"plant": "Xoài", "disease": "Thán thư", "reminders": [{"content": "x", "due": self.due(2)}]}).get_json()["id"]
        self.assertEqual(self.c.put(f"/api/treatments/{tid}", json={"status": "done", "name": "Xong"}).status_code, 200)
        d = self.c.get(f"/api/treatments/{tid}").get_json()
        self.assertEqual((d["status"], d["name"], d["pending"]), ("done", "Xong", 0)); self.assertTrue(d["closed"])
        self.assertEqual(self.c.post(f"/api/treatments/{tid}/reminders", json={"content": "y", "due": self.due(1)}).status_code, 400)
        self.c.put(f"/api/treatments/{tid}", json={"status": "active"})
        self.assertEqual(self.c.get("/api/treatments").get_json()[0]["status"], "active")
    def test_remind_cli(self):
        self.authed(); tid = self.c.post("/api/treatments", json={"plant": "Xoài", "disease": "Thán thư", "reminders": [{"content": "Tưới", "due": self.due(-1)}]}).get_json()["id"]
        with mock.patch.object(core, "send_mail") as sm, mock.patch.object(core, "mail_configured", return_value=True):
            out = self.app.test_cli_runner().invoke(args=["remind", "--no-weather"]).output
        self.assertIn("1 nhắc việc", out); self.assertIn("Tưới", sm.call_args[0][2])
        self.assertEqual(self.c.get("/api/notifications").get_json()[0]["link"], f"/journal/{tid}")

class CompareResultsTests(Base):
    """Trang quản trị đọc results/compare/summary.csv do compare_models.py ghi ra."""
    SUMMARY = ("arch,name,accuracy,top3,macro_f1,weighted_f1,params_m,size_mb,cpu_ms,batch_ms,train_min,epochs,best_val_acc,test_images,classes\n"
               "mobilenetv3,MobileNetV3Large,0.9712,0.998,0.968,0.971,3.03,12.4,45.5,3.1,22.5,12,0.975,8142,39\n"
               "vit,ViT-B/16,0.9850,0.999,0.984,0.985,85.8,330.1,412.0,30.2,95.0,12,0.99,8142,39\n")
    def test_models_endpoint_and_result_files(self):
        import admin.routes as ar
        self.authed(); self.make_admin()
        with mock.patch.object(ar, "RESULTS_DIR", os.path.join(self.tmp.name, "results")):
            self.assertIsNone(self.c.get("/api/admin/models").get_json()["compare"])
            d = os.path.join(self.tmp.name, "results", "compare", "vit"); os.makedirs(d)
            with open(os.path.join(self.tmp.name, "results", "compare", "summary.csv"), "w", encoding="utf-8-sig") as f: f.write(self.SUMMARY)
            Image.new("RGB", (4, 4)).save(os.path.join(d, "confusion_matrix.png"))
            c = self.c.get("/api/admin/models").get_json()["compare"]
            self.assertEqual([r["name"] for r in c["rows"]], ["MobileNetV3Large", "ViT-B/16"]); self.assertFalse(c["chart"])
            self.assertEqual((c["rows"][1]["params_m"], c["rows"][1]["image"], c["rows"][0]["image"], c["rows"][0]["epochs"]), (85.8, True, False, 12))
            self.assertEqual(self.get_status("/api/admin/results/compare/vit/confusion_matrix.png"), 200)
            self.assertEqual(self.get_status("/api/admin/results/compare/mobilenetv3/confusion_matrix.png"), 404)
            for bad in ("compare/../summary.csv", "compare/vit/model.keras", "compare/summary.csv", "../app.py"):
                self.assertEqual(self.get_status("/api/admin/results/" + bad), 404, bad)
    def test_leaf_reevaluated_note(self):
        import admin.routes as ar
        self.authed(); self.make_admin()
        r = os.path.join(self.tmp.name, "results"); os.makedirs(r)
        with mock.patch.object(ar, "RESULTS_DIR", r):
            with open(os.path.join(r, "overall_metrics.csv"), "w", encoding="utf-8-sig") as f: f.write("Accuracy,Macro F1-score\n0.99,0.98\n")
            with open(os.path.join(r, "classification_report.csv"), "w", encoding="utf-8-sig") as f:
                f.write(",precision,recall,f1-score,support\nTomato___healthy,1.0,0.99,0.995,240\naccuracy,0.99,0.99,0.99,8318\n")
            leaf = self.c.get("/api/admin/models").get_json()["leaf"]
            self.assertNotIn("reevaluated", leaf); self.assertEqual([p["name"] for p in leaf["per_class"]], ["Tomato___healthy"])
            with open(os.path.join(r, "leaf_eval.json"), "w", encoding="utf-8") as f:
                json.dump({"model": "best_plant_model.keras", "subsets": {"test": {"accuracy": 0.99, "macro_f1": 0.98, "images": 8318}}, "train_test_gap": 0.001}, f)
            self.assertEqual(self.c.get("/api/admin/models").get_json()["leaf"]["reevaluated"]["subsets"]["test"]["images"], 8318)

class WeatherApiTests(Base):
    def test_location_required_and_saved(self):
        self.authed()
        r = self.c.get("/api/weather"); self.assertEqual(r.status_code, 400); self.assertEqual(r.get_json()["field"], "location")
        self.assertEqual(self.c.put("/api/me/location", json={"lat": 95, "lon": 1}).status_code, 400)
        self.assertEqual(self.c.put("/api/me/location", json={"lat": 21.03, "lon": 105.85, "place": "Hà Nội"}).status_code, 200)
        self.assertEqual(self.c.get("/api/me").get_json()["location"], {"lat": 21.03, "lon": 105.85, "place": "Hà Nội"})
        self.c.put("/api/me/location", json={"lat": None}); self.assertIsNone(self.c.get("/api/me").get_json()["location"])
    def test_weather_report_alerts_and_nearby(self):
        self.authed(); self.c.put("/api/me/location", json={"lat": 21.03, "lon": 105.85, "place": "Hà Nội"})
        self.predict(img=leaf((120, 60, 20))); self.mark_sick()  # tra cứu của tôi -> cây của tôi (cà chua) và một ca bệnh có tọa độ đã lưu
        self.assertEqual(self.sql("select lat, lon from diagnoses"), [(21.03, 105.85)])
        with mock.patch.object(weather, "report", return_value=fake_report(tmean=18, tmin=14, tmax=22, rh=92, wet_hours=12, rain=6)) as f:
            r = self.c.get("/api/weather")
        self.assertEqual(r.status_code, 200); j = r.get_json(); self.assertEqual(f.call_args[0], (21.03, 105.85))
        self.assertEqual(j["location"]["place"], "Hà Nội"); self.assertEqual(len(j["days"]), 9); self.assertEqual(j["days"][0]["desc"], "Ít mây")
        self.assertEqual(j["alerts"][0]["key"], "moc_suong"); self.assertEqual(j["alerts"][0]["plant_names"], ["Cà chua", "Khoai tây"])
        self.assertTrue(j["alerts"][0]["mine"]); self.assertEqual(j["my_plants"], ["Cà chua"])
        # cây AI đã học hiện bằng tên tiếng Việt; "cây không xác định được" bị bỏ
        self.run_sql("INSERT INTO ai_classes(class_name,plant_id,plant,disease,healthy,samples) VALUES('Rice___Rice_blast','rice','Lúa','Bệnh đạo ôn',0,1)")
        self.run_sql("INSERT INTO diagnoses(user_id,plant_id,plant,disease,raw,healthy,confidence,source) VALUES(1,'rice','Lúa','Bệnh đạo ôn','Rice___Rice_blast',0,0.9,'ai')")
        self.run_sql("INSERT INTO diagnoses(user_id,plant_id,plant,disease,raw,healthy,confidence,source) VALUES(1,'plant_type_not_clearly_identifiable_from_image','Không xác định rõ loại cây từ ảnh','Rệp sáp','x',0,0.9,'ai')")
        with mock.patch.object(weather, "report", return_value=fake_report()):
            self.assertEqual(self.c.get("/api/weather").get_json()["my_plants"], ["Cà chua", "Lúa"])
        self.assertEqual(j["nearby"][0]["count"], 1); self.assertEqual(j["nearby"][0]["level"], "thap")
        self.assertEqual((j["current"]["temp"], j["current"]["desc"]), (26.4, "Có mây")); self.assertEqual(len(j["hourly"]), 24)
        self.assertEqual([(p["name"], p["desc"]) for p in j["parts"]], [("Buổi sáng", "Có mây"), ("Buổi chiều", "Mưa nhỏ"), ("Buổi tối", "Mưa nhỏ")])
        with mock.patch.object(weather, "report", return_value=fake_report()):  # vị trí khác qua tham số, xa 1000 km -> không có ca gần
            j = self.c.get("/api/weather?lat=10.78&lon=106.70").get_json()
        self.assertIsNone(j["location"]["place"]); self.assertEqual(j["nearby"], [])
        with mock.patch.object(weather, "report", side_effect=OSError("mạng")):
            self.assertEqual(self.c.get("/api/weather").status_code, 503)
    def test_map_points_anonymous(self):
        self.authed(); self.predict(img=leaf((120, 60, 20)))  # chưa lưu vị trí -> không có tọa độ
        self.assertEqual(self.sql("select lat from diagnoses"), [(None,)]); self.assertEqual(self.c.get("/api/map").get_json()["points"], [])
        self.c.put("/api/me/location", json={"lat": 21.0312, "lon": 105.8512})
        self.predict(img=leaf((120, 60, 20)))  # vị trí đã lưu
        self.c.post("/api/predict", data={"plant": "tomato", "image": (leaf((120, 60, 20)), "l.jpg"), "lat": "21.0349", "lon": "105.8549"}, content_type="multipart/form-data")
        self.assertEqual(self.c.get("/api/map").get_json()["points"], [])  # "chưa xác định" không lên bản đồ
        self.mark_sick()
        pts = self.c.get("/api/map").get_json()["points"]  # ca không tọa độ bị bỏ; 2 ca bệnh cách nhau ~500 m gộp một ô
        self.assertEqual(len(pts), 1); self.assertEqual((pts[0]["lat"], pts[0]["lon"], pts[0]["n"]), (21.03, 105.85, 2))  # làm tròn 2 chữ số
        self.assertEqual(set(pts[0]) - {"plant", "disease", "lat", "lon", "n", "last"}, set())  # không có user_id
    def test_weather_notify_cli_once_per_day(self):
        self.authed(); self.c.put("/api/me/location", json={"lat": 21.03, "lon": 105.85, "place": "Hà Nội"})
        with mock.patch.object(weather, "forecast", return_value=fake_days(tmean=18, tmin=14, tmax=22, rh=92, wet_hours=12, rain=6)):
            out = self.app.test_cli_runner().invoke(args=["remind"]).output
            self.assertIn("1 cảnh báo", out)
            self.assertIn("0 cảnh báo", self.app.test_cli_runner().invoke(args=["remind"]).output)
        n = self.c.get("/api/notifications").get_json()
        self.assertEqual(len(n), 1); self.assertIn("Mốc sương", n[0]["content"]); self.assertEqual(n[0]["link"], "/weather")
    def test_geocode(self):
        self.authed()
        self.assertEqual(self.c.get("/api/geocode?q=H").get_json(), [])
        with mock.patch.object(weather, "_get", return_value={"results": [{"name": "Đà Lạt", "admin1": "Lâm Đồng", "latitude": 11.94, "longitude": 108.44, "country_code": "VN"}]}):
            self.assertEqual(self.c.get("/api/geocode?q=Đà Lạt").get_json(), [{"name": "Đà Lạt, Lâm Đồng", "lat": 11.94, "lon": 108.44}])

if __name__ == "__main__":
    unittest.main(verbosity=2)
