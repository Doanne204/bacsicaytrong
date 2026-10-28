"""Nạp mô hình Keras đã huấn luyện. Nếu chưa có file mô hình -> chạy chế độ DEMO (kết quả giả lập, chỉ để thử giao diện/kiểm thử).
Ngoài xác suất các lớp, mô hình còn cho vector đặc trưng (lớp GlobalAveragePooling, 960 chiều) để so độ giống giữa các ảnh."""
import hashlib, io, json, os
import numpy as np
from PIL import Image, ImageOps
import knowledge, pests

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
# train.py lưu plant_model.keras ở cuối; nếu quá trình train dừng giữa chừng thì chỉ có best_plant_model.keras
MODEL_PATHS = [os.getenv("MODEL_PATH")] if os.getenv("MODEL_PATH") else [
    os.path.join(MODELS_DIR, "plant_model.keras"), os.path.join(MODELS_DIR, "best_plant_model.keras")]
CLASSES_PATH = os.getenv("CLASSES_PATH", os.path.join(MODELS_DIR, "class_names.json"))
CENTROIDS_PATH = os.getenv("CENTROIDS_PATH", os.path.join(MODELS_DIR, "class_centroids.npz"))
# Mô hình sâu hại (train_pests.py, INSECT204): chưa có file thì app ẩn lựa chọn "Sâu hại"
PEST_MODEL_PATH = os.getenv("PEST_MODEL_PATH", os.path.join(MODELS_DIR, "pest_model.keras"))
PEST_CLASSES_PATH = os.path.join(MODELS_DIR, "pest_class_names.json")
PEST_CENTROIDS_PATH = os.path.join(MODELS_DIR, "pest_centroids.npz")
IMG_SIZE = 224

def _unit(v):
    v = np.asarray(v, dtype=np.float32).ravel()
    return v / (np.linalg.norm(v) + 1e-9)

def load_image(image_bytes):
    """Ảnh PIL RGB 224x224 đưa vào mô hình; dùng chung lúc huấn luyện (train_pests.py) và lúc chạy để xử lý ảnh giống hệt nhau."""
    return ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB").resize((IMG_SIZE, IMG_SIZE))

def file_key(path):
    """Mã nhận diện file mô hình theo nội dung (chép file sang máy khác vẫn khớp, huấn luyện lại thì đổi)."""
    with open(path, "rb") as f:
        return f"{os.path.basename(path)}:{hashlib.sha256(f.read()).hexdigest()[:16]}"

def thumb_embedding(img):
    """Vector đặc trưng đơn giản (ảnh thu nhỏ 16x16) khi không có mô hình thật (DEMO/kiểm thử)."""
    v = np.asarray(img.resize((16, 16)), dtype=np.float32).ravel()
    return _unit(v - v.mean())

class ModelService:
    def __init__(self):
        self.model, self.dual, self.demo = None, None, True
        self.class_names = knowledge.CLASS_NAMES
        self.embed_key = "thumb"  # vector của mô hình khác nhau thì không so sánh được với nhau
        path = next((p for p in MODEL_PATHS if os.path.exists(p)), None)
        if path:
            try:
                # Bắt buộc có class_names.json: đoán thứ tự lớp sẽ làm lệch nhãn mà không báo lỗi
                if not os.path.exists(CLASSES_PATH):
                    raise FileNotFoundError(f"thiếu {CLASSES_PATH} (thứ tự lớp lúc huấn luyện)")
                with open(CLASSES_PATH, encoding="utf-8") as f:
                    names = json.load(f)
                import tensorflow as tf
                model = tf.keras.models.load_model(path)
                if model.output_shape[-1] != len(names):
                    raise ValueError(f"mô hình có {model.output_shape[-1]} lớp nhưng class_names.json có {len(names)} lớp")
                self.model, self.class_names, self.demo = model, names, False
                gap = next((l for l in model.layers if isinstance(l, tf.keras.layers.GlobalAveragePooling2D)), None)
                if gap is not None:  # một lần chạy cho cả xác suất lẫn vector đặc trưng
                    self.dual = tf.keras.Model(model.inputs, [model.output, gap.output])
                    self.embed_key = f"{os.path.basename(path)}:{os.path.getsize(path)}:{int(os.path.getmtime(path))}"
            except Exception as e:  # thiếu TF hoặc file lỗi
                print("[model] Không nạp được mô hình, dùng DEMO:", e, flush=True)
        self.centroids = None  # vector trung bình mỗi lớp trong dữ liệu huấn luyện, để nhận ra ảnh "lạ"
        if self.dual is not None and os.path.exists(CENTROIDS_PATH):
            c = np.load(CENTROIDS_PATH)
            if str(c["embed_key"]) == self.embed_key:
                self.centroids = c["centroids"]
            else:
                print("[model] class_centroids.npz tính bằng mô hình khác, hãy chạy lại: flask --app app build-centroids <thư mục ảnh>", flush=True)

    def familiarity(self, emb):
        """Độ giống cao nhất giữa ảnh và tâm các lớp đã học; thấp = ảnh khác xa dữ liệu huấn luyện (VD cây chưa có). None nếu chưa có tâm lớp."""
        return None if self.centroids is None else float(np.max(self.centroids @ emb))

    def build_centroids(self, data_dir, per_class=40, seed=0):
        """Tính tâm (trung bình vector đặc trưng) cho mỗi lớp từ tối đa per_class ảnh trong data_dir/<lớp>/ rồi lưu CENTROIDS_PATH."""
        if self.dual is None:
            raise RuntimeError("cần mô hình thật để tính vector đặc trưng")
        rng, rows = np.random.default_rng(seed), []
        for c in self.class_names:
            d = os.path.join(data_dir, c)
            files = sorted(f for f in os.listdir(d) if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")))
            pick = rng.choice(files, size=min(per_class, len(files)), replace=False)
            embs = [self.embed(open(os.path.join(d, f), "rb").read()) for f in pick]
            rows.append(_unit(np.mean(embs, axis=0)))
        self.centroids = np.vstack(rows).astype(np.float32)
        np.savez(CENTROIDS_PATH, centroids=self.centroids, embed_key=self.embed_key, class_names=np.array(self.class_names))
        return self.centroids

    def gradcam(self, image_bytes: bytes, class_name: str):
        """Bản đồ nhiệt Grad-CAM (14x14, 0-1) cho lớp class_name: vùng ảnh khiến mô hình nghĩ tới lớp đó. None nếu không có mô hình thật."""
        if self.dual is None or class_name not in self.class_names:
            return None
        if getattr(self, "_grad", None) is None:
            self._grad = grad_model_inner(self.model)
        return gradcam_map(self._grad, image_bytes, self.class_names.index(class_name))

    def _indices_for(self, plant_id=None):
        """Các lớp của cây plant_id; None = mọi lớp cây trồng (bỏ lớp nền) cho chế độ tự nhận diện."""
        ids = [knowledge.info(c)["plant_id"] for c in self.class_names]
        return [i for i, p in enumerate(ids) if (p == plant_id if plant_id else p in knowledge.PLANTS)]

    def _forward(self, img):
        """(xác suất các lớp, vector đặc trưng đơn vị) cho ảnh PIL 224x224."""
        x = np.expand_dims(np.asarray(img, dtype="float32"), 0)  # tiền xử lý nằm trong mô hình
        if self.dual is not None:
            p, e = self.dual(x, training=False)
            return np.asarray(p)[0], _unit(np.asarray(e)[0])
        return self.model.predict(x, verbose=0)[0], thumb_embedding(img)

    def embed(self, image_bytes: bytes):
        img = load_image(image_bytes)
        return self._forward(img)[1] if self.dual is not None else thumb_embedding(img)

    def predict(self, image_bytes: bytes, plant_id=None, top_k: int = 3):
        """Trả về (top_k lớp thuộc cây đã chọn, lớp có xác suất cao nhất trên toàn bộ mô hình, vector đặc trưng).
        Giữ nguyên xác suất softmax gốc, không chuẩn hóa lại theo cây, để cây chỉ có 1 lớp không luôn ra 100%."""
        idx = self._indices_for(plant_id)
        if not idx:
            raise ValueError("Cây không được hỗ trợ")
        img = load_image(image_bytes)
        if self.demo:
            seed = int(hashlib.sha256(image_bytes).hexdigest()[:8], 16)
            probs = np.zeros(len(self.class_names))
            probs[idx] = np.random.default_rng(seed).dirichlet(np.ones(len(idx)) * 0.5)
            emb = thumb_embedding(img)
        else:
            probs, emb = self._forward(img)
        order = sorted(idx, key=lambda i: probs[i], reverse=True)[:top_k]
        out = []
        for o in order:
            d = knowledge.info(self.class_names[o])
            out.append(dict(raw=self.class_names[o], plant_id=d["plant_id"], plant=d["plant"], disease=d["disease"], healthy=d["healthy"],
                            remedy=d["remedy"], prob=float(probs[o])))
        return out, knowledge.info(self.class_names[int(np.argmax(probs))]), emb

# ---------- Grad-CAM (chỉ dùng cho hình báo cáo gradcam_examples.py) và vết bệnh, mức độ bệnh ----------
# Trang kết quả đã bỏ Grad-CAM: vùng mô hình chú ý thường không trùng vết bệnh (trên 56 ảnh lá bệnh test, điểm nóng nhất nằm trên vết
# bệnh 41% với lớp 14x14, 27% với lớp 7x7 cuối), người dùng dễ hiểu nhầm là bản đồ bệnh. Thay bằng ảnh tô vết hại theo màu (lesion_overlay).

def grad_model_for(model, fmap_layer_output):
    """Mô hình phụ cho Grad-CAM: (bản đồ đặc trưng, đầu vào lớp Dense cuối) cùng lớp Dense đó để tự tính logit."""
    import tensorflow as tf
    dense = model.layers[-1]
    if not isinstance(dense, tf.keras.layers.Dense):
        raise ValueError("lớp cuối của mô hình không phải Dense")
    return tf.keras.Model(model.inputs, [fmap_layer_output, dense.input]), dense

def grad_model_inner(model, size=14):
    """Như grad_model_for nhưng lấy bản đồ đặc trưng size x size bên trong backbone lồng (mô hình lá: ảnh -> tăng cường -> MobileNetV3Large
    -> GAP -> Dropout -> Dense). Chọn khối cuối cùng có kích thước đó (lớp ..._add, đầu ra của một khối MobileNetV3). Không có thì dùng 7x7."""
    import tensorflow as tf
    dense = model.layers[-1]
    gap = next(l for l in model.layers if isinstance(l, tf.keras.layers.GlobalAveragePooling2D))
    bb = next((l for l in model.layers if isinstance(l, tf.keras.Model) and len(l.output.shape) == 4 and l.output.shape[1] < size), None)
    inner = [l for l in bb.layers if l.name.endswith("_add") and len(l.output.shape) == 4 and l.output.shape[1] == size] if bb else []
    if not inner:
        return grad_model_for(model, gap.input)
    sub = tf.keras.Model(bb.input, [inner[-1].output, bb.output])

    def run(x, training=False):  # bỏ qua lớp tăng cường ảnh (không làm gì khi suy luận) và Dropout
        fmap, last = sub(x, training=training)
        return fmap, gap(last)
    return run, dense

def gradcam_map(grad, image_bytes, class_index):
    """Grad-CAM (Selvaraju và cộng sự, 2017) trên LOGIT của lớp (trước softmax), như bài báo gốc.
    Trọng số mỗi kênh = trung bình gradient của logit theo kênh đó; bản đồ = ReLU(tổng có trọng số các kênh), chuẩn hóa 0-1.
    Không lấy gradient của xác suất softmax: khi mô hình phân vân hoặc rất chắc, gradient đó chủ yếu phản ánh phần khác biệt với
    các lớp còn lại nên vùng nóng hay rơi vào nền, mép lá. Tính cho ảnh và ảnh lật ngang rồi lấy trung bình (lật lại) cho bớt nhiễu."""
    import tensorflow as tf
    grad_model, dense = grad
    img = np.asarray(load_image(image_bytes), dtype="float32")
    x = tf.constant(np.stack([img, img[:, ::-1]]))
    with tf.GradientTape() as tape:
        fmap, h = grad_model(x, training=False)
        score = tf.reduce_sum(tf.matmul(h, dense.kernel[:, class_index:class_index + 1]) + dense.bias[class_index])
    grads = tape.gradient(score, fmap)
    if grads is None:
        return None
    w = tf.reduce_mean(grads, axis=(1, 2))
    cams = tf.nn.relu(tf.reduce_sum(fmap * w[:, None, None, :], axis=-1)).numpy()
    cam = (cams[0] + cams[1][:, ::-1]) / 2
    return cam / (cam.max() + 1e-9)

def cam_stats(cam):
    """Mô tả bản đồ nhiệt: tỉ lệ diện tích ảnh có mức ảnh hưởng mạnh (>= 0.5) và vị trí vùng nóng nhất (3x3 ô: trên/giữa/dưới, trái/giữa/phải)."""
    c = np.asarray(Image.fromarray((np.clip(cam, 0, 1) * 255).astype(np.uint8)).resize((96, 96), Image.BICUBIC), dtype=np.float32) / 255.0
    ys, xs = np.nonzero(c >= 0.5)
    if not len(ys):
        return dict(focus=0.0, where="")
    cy, cx = np.average(ys, weights=c[ys, xs]) / 96, np.average(xs, weights=c[ys, xs]) / 96
    row = "phía trên" if cy < 1 / 3 else "phía dưới" if cy > 2 / 3 else ""
    col = "bên trái" if cx < 1 / 3 else "bên phải" if cx > 2 / 3 else ""
    where = " ".join(p for p in (row, col) if p) + " ảnh" if row or col else "chính giữa ảnh"
    return dict(focus=round(float((c >= 0.5).mean()), 3), where=where)

def _heat_rgb(cam):
    """Bản đồ nhiệt (HxW, 0-1) -> ảnh RGB uint8 theo thang xanh dương -> xanh lá -> vàng -> đỏ."""
    c = np.clip(cam, 0, 1)
    r = np.clip(1.5 * c - 0.25, 0, 1); g = np.clip(1 - np.abs(2 * c - 1) * 1.2 + 0.2, 0, 1); b = np.clip(1 - 2 * c, 0, 1)
    return (np.stack([r, g, b], -1) * 255).astype(np.uint8)

def overlay_cam(image_bytes, cam, alpha=0.65):
    """Phủ bản đồ nhiệt Grad-CAM lên ảnh gốc: chỗ mô hình chú ý ít thì giữ nguyên ảnh, chỗ chú ý nhiều tô vàng -> đỏ. Trả về bytes JPEG."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    img.thumbnail((800, 800))
    c = np.asarray(Image.fromarray((np.clip(cam, 0, 1) * 255).astype(np.uint8)).resize(img.size, Image.BICUBIC), dtype=np.float32) / 255.0
    heat = _heat_rgb(c).astype(np.float32)
    a = (np.clip((c - 0.15) / 0.85, 0, 1) ** 0.8 * alpha)[..., None]  # vùng lạnh (< 0.15) trong suốt hoàn toàn
    out = (np.asarray(img, dtype=np.float32) * (1 - a) + heat * a).astype(np.uint8)
    buf = io.BytesIO(); Image.fromarray(out).save(buf, "JPEG", quality=85)
    return buf.getvalue()

def leaf_lesion(img):
    """(lá, vết hại) theo màu cho ảnh PIL RGB: lá = phần có màu (bỏ nền trắng/xám sáng, giữ phần lá tối, vết thâm); vết hại = phần lá
    không còn xanh (nâu, vàng, đen, trắng). Ước lượng thô, cần nền đơn giản."""
    hsv = np.asarray(img.convert("HSV"), dtype=np.int16)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    leaf = (s > 45) & (v > 35) | ((v < 110) & (s > 25))
    green = leaf & (h >= 38) & (h <= 110)  # màu xanh lá (thang hue 0-255 của PIL)
    return leaf, leaf & ~green

def lesion_overlay(image_bytes):
    """Ảnh tô các vết hại phát hiện theo màu (hồng, viền đậm) cho trang kết quả. Trả về bytes JPEG hoặc None nếu không tách được lá."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    img.thumbnail((800, 800))
    leaf, lesion = leaf_lesion(img)
    if leaf.mean() < 0.05:
        return None
    from PIL import ImageFilter
    m = Image.fromarray((lesion * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(5))  # bỏ chấm lẻ tẻ
    fill = np.asarray(m, dtype=np.float32) / 255
    edge = np.asarray(m.filter(ImageFilter.MaxFilter(5)), dtype=np.float32) / 255 - fill
    base = np.asarray(img, dtype=np.float32) * 0.75  # làm tối ảnh một chút cho vết tô nổi lên
    color = np.array([236, 72, 153], dtype=np.float32)
    out = base * (1 - 0.55 * fill[..., None]) + color * 0.55 * fill[..., None]
    out = out * (1 - edge[..., None]) + color * edge[..., None]
    buf = io.BytesIO(); Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(buf, "JPEG", quality=85)
    return buf.getvalue()

def severity(image_bytes):
    """Ước lượng tỉ lệ diện tích lá bị hại bằng màu sắc (vùng lá không còn xanh: nâu, vàng, đen, trắng), đúng phần được tô ở ảnh vết bệnh.
    Chỉ là ước lượng thô để xếp mức nhẹ / trung bình / nặng; nền phải đơn giản, lá chiếm phần lớn ảnh."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    img.thumbnail((320, 320))
    leaf, lesion = leaf_lesion(img)
    if leaf.sum() < 0.03 * leaf.size:
        return None
    return severity_level(float(lesion.sum() / leaf.sum()), float(leaf.sum() / leaf.size))

def severity_level(pct, leaf_pct):
    """Xếp mức nhẹ / trung bình / nặng kèm lời khuyên cho tỉ lệ diện tích lá bị hại pct (của một ảnh hoặc trung bình nhiều ảnh)."""
    level = "nhe" if pct < 0.10 else "vua" if pct < 0.30 else "nang"
    label = {"nhe": "Nhẹ", "vua": "Trung bình", "nang": "Nặng"}[level]
    advice = {"nhe": "Vết bệnh còn ít: ngắt bỏ lá bệnh, theo dõi 2-3 ngày/lần, ưu tiên biện pháp canh tác và sinh học, chưa cần phun thuốc diện rộng.",
              "vua": "Bệnh đã lan khá rộng trên lá: xử lý sớm theo hướng dẫn, phun đúng thuốc đúng lúc, kiểm tra các cây xung quanh.",
              "nang": "Lá bị hại nặng: cắt bỏ và tiêu hủy lá/cành bệnh, xử lý ngay cho cả vườn, cân nhắc hỏi cán bộ khuyến nông vì có thể cần phối hợp thuốc."}[level]
    return dict(pct=round(pct, 3), level=level, label=label, advice=advice, leaf_pct=round(leaf_pct, 3))

def pest_entry(raw, prob):
    """Một dòng kết quả sâu hại theo cùng khuôn kết quả bệnh lá (plant/disease/remedy) kèm thông tin loài."""
    d = pests.info(raw)
    return dict(raw=d["raw"], plant_id="pest", plant="Thiên địch" if d["beneficial"] else "Sâu hại", disease=d["name"],
                healthy=d["beneficial"], remedy=d["remedy"], prob=float(prob), group_name=d["group_name"], hosts=d["hosts"],
                beneficial=d["beneficial"])

class PestService:
    """Mô hình nhận diện sâu hại (204 loài INSECT204, cùng kiến trúc MobileNetV3Large), kèm tâm vector mỗi loài để nhận ra ảnh
    không phải côn trùng/loài chưa học. Không có file mô hình hoặc nạp lỗi thì available=False."""

    def __init__(self):
        self.dual, self.class_names, self.centroids = None, [], None
        if not os.path.exists(PEST_MODEL_PATH):
            return
        try:
            with open(PEST_CLASSES_PATH, encoding="utf-8") as f:
                names = json.load(f)
            import tensorflow as tf
            model = tf.keras.models.load_model(PEST_MODEL_PATH)
            if model.output_shape[-1] != len(names):
                raise ValueError(f"mô hình có {model.output_shape[-1]} lớp nhưng pest_class_names.json có {len(names)} lớp")
            self.dual = tf.keras.Model(model.inputs, [model.output, model.get_layer("gap").output])
            self._grad = grad_model_for(model, model.get_layer("gap").input)  # cho Grad-CAM
            self.class_names = names
            self.embed_key = file_key(PEST_MODEL_PATH)  # đổi mô hình thì bản đồ Grad-CAM đã lưu không còn đúng
            if os.path.exists(PEST_CENTROIDS_PATH):
                c = np.load(PEST_CENTROIDS_PATH)
                if str(c["embed_key"]) == file_key(PEST_MODEL_PATH):
                    self.centroids = c["centroids"]
                else:
                    print("[pest] pest_centroids.npz không khớp pest_model.keras, hãy chạy lại train_pests.py", flush=True)
        except Exception as e:  # thiếu TF hoặc file lỗi: app vẫn chạy, chỉ ẩn nhận diện sâu hại
            self.dual = None
            print("[pest] Không nạp được mô hình sâu hại:", e, flush=True)

    @property
    def available(self):
        return self.dual is not None

    def predict(self, image_bytes: bytes, top_k: int = 3):
        """(top_k loài kèm thông tin hiển thị, độ giống cao nhất với tâm các loài hoặc None nếu chưa có tâm)."""
        p, e = self.dual(np.expand_dims(np.asarray(load_image(image_bytes), dtype="float32"), 0), training=False)
        p, e = np.asarray(p)[0], _unit(np.asarray(e)[0])
        fam = None if self.centroids is None else float(np.max(self.centroids @ e))
        return [pest_entry(self.class_names[i], p[i]) for i in np.argsort(-p)[:top_k]], fam

    def gradcam(self, image_bytes: bytes, class_name: str):
        """Grad-CAM cho loài class_name (mô hình phẳng: lớp tích chập cuối là đầu vào của lớp "gap")."""
        if self.dual is None or class_name not in self.class_names:
            return None
        return gradcam_map(self._grad, image_bytes, self.class_names.index(class_name))
