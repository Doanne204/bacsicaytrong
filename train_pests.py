"""MÔ HÌNH CŨ, CHỈ ĐỂ SO SÁNH: app dùng YOLO11m-cls làm mô hình sâu hại (yolo/train_yolo.py rồi yolo/export_pest.py), đúng 76,3% so với
71,0% của bản MobileNetV3Large này trên cùng tập test. Script này mặc định ghi vào models/candidate_pest, results/candidate_pest để không đè
mô hình app đang dùng. Phép chia train/val/test 6:1:3 (seed cố định) giống hệt results/pest_split.csv mà yolo/make_yolo_dataset.py dùng.

Huấn luyện mô hình nhận diện sâu hại trên INSECT204 (204 loài côn trùng, ốc, nhện hại và thiên địch), cùng kiến trúc MobileNetV3Large
với mô hình bệnh lá để app chạy chung TensorFlow.
Bước 1 (chạy được trên CPU): trích vector đặc trưng 960 chiều bằng MobileNetV3Large học sẵn trên ImageNet (đóng băng, lưu cache để chạy
        lại nhanh), rồi học lớp phân loại trên các vector. Kết quả ghép thành một mô hình nhận ảnh 224x224 giá trị 0-255 như mô hình bệnh lá.
Bước 2 (tùy chọn): --finetune_epochs N tinh chỉnh MobileNetV3 trên ảnh có tăng cường (lật, xoay, phóng to, sáng tối, tương phản):
        toàn bộ backbone (--unfreeze -1, mặc định) hoặc N lớp cuối; LR khởi động 1 epoch rồi giảm cosine (--finetune_lr), AdamW,
        label smoothing 0.1, dừng sớm theo val_accuracy và lấy epoch tốt nhất. CPU i5-14600KF: khoảng 9-10 phút/epoch.
Chạy: python train_pests.py --data "dataset/INSECT204-A Novel Large-Scale Benchmark Dataset fo/INSECT204"
      thêm --finetune_epochs 12 để tinh chỉnh
Ra:   <models_dir>/pest_model.keras, pest_class_names.json, pest_centroids.npz (nhận ra ảnh không phải sâu hại),
      <results_dir>/pest_split.csv (ảnh thuộc train/val/test), pest_metrics.json
"""
import argparse, csv, hashlib, json, os, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--data", required=True, help="Thư mục có mỗi loài một thư mục con")
parser.add_argument("--hidden", type=int, default=512, help="Số nơ-ron lớp ẩn trước softmax (0: chỉ một lớp softmax)")
parser.add_argument("--epochs", type=int, default=60, help="Số epoch tối đa khi học lớp phân loại (dừng sớm theo tập val)")
parser.add_argument("--finetune_epochs", type=int, default=0, help="Số epoch tinh chỉnh MobileNetV3 trên ảnh (0: chỉ học lớp phân loại)")
parser.add_argument("--unfreeze", type=int, default=-1, help="-1: tinh chỉnh toàn bộ backbone; N: chỉ N lớp cuối")
parser.add_argument("--finetune_lr", type=float, default=1e-4, help="LR cao nhất khi tinh chỉnh (khởi động 1 epoch rồi giảm cosine)")
parser.add_argument("--label_smoothing", type=float, default=0.1)
parser.add_argument("--patience", type=int, default=3)
parser.add_argument("--batch", type=int, default=64)
parser.add_argument("--limit_per_class", type=int, default=0, help="Chỉ lấy tối đa N ảnh mỗi lớp (chạy thử nhanh)")
parser.add_argument("--cache", default=os.path.join("results", "pest_cache"), help="Thư mục lưu vector đặc trưng đã trích")
parser.add_argument("--models_dir", default=os.path.join("models", "candidate_pest"))
parser.add_argument("--results_dir", default=os.path.join("results", "candidate_pest"))
args = parser.parse_args()

import tensorflow as tf
from model_service import file_key, load_image, IMG_SIZE

SEED = 42
ROOT = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(ROOT, args.models_dir)
RESULTS = os.path.join(ROOT, args.results_dir)
T_START = time.time()
os.makedirs(MODELS, exist_ok=True); os.makedirs(RESULTS, exist_ok=True); os.makedirs(args.cache, exist_ok=True)
tf.keras.utils.set_random_seed(SEED)
data_dir = os.path.abspath(args.data)

# 1. Danh sách ảnh, bỏ ảnh trùng nội dung: trùng trong cùng lớp giữ 1 bản; trùng giữa các lớp khác nhau bỏ hết (không rõ nhãn đúng)
class_names = sorted(d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d)))
files = {c: sorted(f for f in os.listdir(os.path.join(data_dir, c)) if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp"))) for c in class_names}
if args.limit_per_class:
    files = {c: fs[:args.limit_per_class] for c, fs in files.items()}
print(f"{len(class_names)} lớp, {sum(map(len, files.values()))} ảnh", flush=True)

def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

items = [(c, f) for c in class_names for f in files[c]]
with ThreadPoolExecutor(16) as ex:
    digests = list(ex.map(lambda it: md5(os.path.join(data_dir, *it)), items))
owners = {}
for (c, _), h in zip(items, digests):
    owners.setdefault(h, set()).add(c)
seen, kept, dup_same, dup_cross = set(), {c: [] for c in class_names}, 0, 0
for (c, f), h in zip(items, digests):
    if len(owners[h]) > 1:
        dup_cross += 1
    elif h in seen:
        dup_same += 1
    else:
        seen.add(h); kept[c].append(f)
print(f"Bỏ {dup_same} ảnh trùng trong cùng lớp, {dup_cross} ảnh trùng giữa các lớp khác nhau", flush=True)

# 2. Chia train/val/test 6:1:3 theo từng lớp (đúng tỉ lệ của bài báo INSECT204), cố định seed để chạy lại ra cùng kết quả
rng = np.random.default_rng(SEED)
split = {"train": [], "val": [], "test": []}
for i, c in enumerate(class_names):
    fs = list(kept[c]); rng.shuffle(fs)
    n_val, n_test = max(1, round(len(fs) * 0.1)), max(1, round(len(fs) * 0.3))
    for name, part in (("val", fs[:n_val]), ("test", fs[n_val:n_val + n_test]), ("train", fs[n_val + n_test:])):
        split[name] += [(os.path.join(c, f), i) for f in part]
with open(os.path.join(RESULTS, "pest_split.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["file", "class", "split"])
    for name, rows in split.items():
        w.writerows((p, class_names[y], name) for p, y in rows)
print({k: len(v) for k, v in split.items()}, flush=True)

# 3. Trích vector đặc trưng bằng MobileNetV3Large ImageNet (tiền xử lý nằm trong mô hình, nhận ảnh 0-255 như mô hình bệnh lá)
def backbone(trainable=False):
    base = tf.keras.applications.MobileNetV3Large(input_shape=(IMG_SIZE, IMG_SIZE, 3), include_top=False, weights="imagenet",
                                                  include_preprocessing=True)
    base.trainable = trainable
    return base

base = backbone()
gap = tf.keras.layers.GlobalAveragePooling2D(name="gap")(base.output)
extractor = tf.keras.Model(base.input, gap)

def read(rel):
    try:
        with open(os.path.join(data_dir, rel), "rb") as f:
            return np.asarray(load_image(f.read()), dtype=np.float32)
    except Exception:  # ảnh hỏng: đánh dấu bỏ
        return None

def embed_split(name, rows, chunk=1024):
    """Trích vector theo từng khúc, lưu cache để chạy lại (hoặc bị ngắt giữa chừng) không phải tính lại.
    Đọc ảnh của khúc kế tiếp (nhiều luồng) trong lúc mô hình chạy khúc hiện tại."""
    key = hashlib.md5("\n".join(r for r, _ in rows).encode()).hexdigest()[:10]
    out, ok, t0 = [], [], time.time()
    starts = list(range(0, len(rows), chunk))
    cache = [os.path.join(args.cache, f"{name}_{key}_{s // chunk:04d}.npz") for s in starts]
    with ThreadPoolExecutor(12) as ex, ThreadPoolExecutor(1) as pre:
        load = lambda s: list(ex.map(read, [r for r, _ in rows[s:s + chunk]]))
        nxt = {}
        for k, s in enumerate(starts):
            if os.path.exists(cache[k]):
                z = np.load(cache[k]); out.append(z["emb"]); ok.append(z["ok"]); continue
            imgs = (nxt.pop(s) if s in nxt else pre.submit(load, s)).result()
            later = next((t for j, t in enumerate(starts[k + 1:], k + 1) if not os.path.exists(cache[j])), None)
            if later is not None:
                nxt[later] = pre.submit(load, later)
            good = np.array([im is not None for im in imgs])
            batch = np.stack([im if im is not None else np.zeros((IMG_SIZE, IMG_SIZE, 3), np.float32) for im in imgs])
            emb = extractor.predict(batch, batch_size=args.batch, verbose=0).astype(np.float32)
            np.savez(cache[k], emb=emb, ok=good); out.append(emb); ok.append(good)
            done = min(s + chunk, len(rows))
            print(f"  {name}: {done}/{len(rows)} ảnh, {time.time() - t0:.0f} giây", flush=True)
    return np.concatenate(out), np.concatenate(ok)

X, Y = {}, {}
for name, rows in split.items():
    e, good = embed_split(name, rows)
    X[name], Y[name] = e[good], np.array([y for _, y in rows])[good]
    if (~good).sum():
        print(f"  {name}: bỏ {(~good).sum()} ảnh không đọc được", flush=True)

# 4. Học lớp phân loại trên vector; trọng số lớp ~ 1/sqrt(số ảnh) để lớp ít ảnh không bị lấn át (dữ liệu lệch 60 - 5510 ảnh/lớp)
n = len(class_names)
def head_layers():
    layers = [tf.keras.layers.Dropout(0.3, name="head_dropout")]
    if args.hidden:
        layers += [tf.keras.layers.Dense(args.hidden, activation="relu", name="head_hidden"), tf.keras.layers.Dropout(0.3, name="head_dropout2")]
    return layers + [tf.keras.layers.Dense(n, activation="softmax", name="pest_output")]

inp = tf.keras.Input((X["train"].shape[1],))
h = inp
for layer in head_layers():
    h = layer(h)
head = tf.keras.Model(inp, h)
cnt = np.bincount(Y["train"], minlength=n)
cw = 1 / np.sqrt(np.maximum(cnt, 1)); cw = cw / (cw * cnt).sum() * cnt.sum()
head.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="sparse_categorical_crossentropy",
             metrics=["accuracy", tf.keras.metrics.SparseTopKCategoricalAccuracy(5, name="top5")])
head.fit(X["train"], Y["train"], validation_data=(X["val"], Y["val"]), epochs=args.epochs, batch_size=256, verbose=2,
         class_weight=dict(enumerate(cw)),
         callbacks=[tf.keras.callbacks.EarlyStopping("val_accuracy", patience=6, restore_best_weights=True),
                    tf.keras.callbacks.ReduceLROnPlateau("val_loss", factor=0.3, patience=3)])

# Ghép backbone + lớp phân loại thành một mô hình phẳng (app lấy cả xác suất lẫn vector lớp "gap" trong một lần chạy)
def full_model(base):
    x = tf.keras.layers.GlobalAveragePooling2D(name="gap")(base.output)
    for layer in head_layers():
        x = layer(x)
    return tf.keras.Model(base.input, x, name="pest_model")

model = full_model(base)
for layer in head.layers[1:]:
    model.get_layer(layer.name).set_weights(layer.get_weights())

# 5. (Tùy chọn) tinh chỉnh MobileNetV3 trên ảnh có tăng cường
test_probs = None
if args.finetune_epochs:
    base.trainable = True  # backbone dùng chung với mô hình ghép; BatchNorm giữ thống kê ImageNet để tinh chỉnh ổn định
    if args.unfreeze > 0:
        for layer in base.layers[:-args.unfreeze]:
            layer.trainable = False
    for layer in base.layers:
        if isinstance(layer, tf.keras.layers.BatchNormalization):
            layer.trainable = False
    augment = tf.keras.Sequential([
        tf.keras.layers.RandomFlip("horizontal"), tf.keras.layers.RandomRotation(0.08), tf.keras.layers.RandomZoom(0.15),
        tf.keras.layers.RandomBrightness(0.15, value_range=(0, 255)), tf.keras.layers.RandomContrast(0.15),
    ], name="augment")
    def ds(rows, train):
        paths = [os.path.join(data_dir, r) for r, _ in rows]
        d = tf.data.Dataset.from_tensor_slices((paths, [y for _, y in rows]))
        if train:
            d = d.shuffle(len(rows), seed=SEED)
        def load(p, y):
            img = tf.image.resize(tf.io.decode_image(tf.io.read_file(p), channels=3, expand_animations=False), (IMG_SIZE, IMG_SIZE),
                                  method="bicubic")  # giống PIL resize trong load_image
            return tf.clip_by_value(img, 0, 255), y
        d = d.map(load, num_parallel_calls=tf.data.AUTOTUNE).batch(args.batch)
        if train:  # tăng cường theo lô, ngoài mô hình nên mô hình lưu ra không có lớp tăng cường
            d = d.map(lambda x, y: (augment(x, training=True), tf.one_hot(y, n)), num_parallel_calls=tf.data.AUTOTUNE)
        else:
            d = d.map(lambda x, y: (x, tf.one_hot(y, n)))
        return d.prefetch(tf.data.AUTOTUNE)
    steps = int(np.ceil(len(split["train"]) / args.batch))
    schedule = tf.keras.optimizers.schedules.CosineDecay(initial_learning_rate=args.finetune_lr / 10, decay_steps=max(1, steps * (args.finetune_epochs - 1)),
                                                         alpha=0.01, warmup_target=args.finetune_lr, warmup_steps=steps)
    model.compile(optimizer=tf.keras.optimizers.AdamW(learning_rate=schedule, weight_decay=1e-5),
                  loss=tf.keras.losses.CategoricalCrossentropy(label_smoothing=args.label_smoothing),
                  metrics=["accuracy", tf.keras.metrics.TopKCategoricalAccuracy(5, name="top5")])
    print(f"Tinh chỉnh {sum(l.trainable for l in base.layers)}/{len(base.layers)} lớp backbone, "
          f"{sum(int(np.prod(w.shape)) for w in model.trainable_weights):,} tham số", flush=True)
    ckpt = os.path.join(MODELS, "pest_best.keras")
    model.fit(ds(split["train"], True), validation_data=ds(split["val"], False), epochs=args.finetune_epochs, verbose=2,
              class_weight=dict(enumerate(cw)),
              callbacks=[tf.keras.callbacks.ModelCheckpoint(ckpt, monitor="val_accuracy", mode="max", save_best_only=True, verbose=1),
                         tf.keras.callbacks.EarlyStopping("val_accuracy", patience=args.patience, restore_best_weights=True),
                         tf.keras.callbacks.CSVLogger(os.path.join(RESULTS, "pest_training_log.csv")),
                         tf.keras.callbacks.TerminateOnNaN()])
    if os.path.exists(ckpt):
        os.remove(ckpt)  # trọng số tốt nhất đã được EarlyStopping khôi phục vào model
    # vector đặc trưng đã đổi theo backbone mới: tính lại cho tập train (tâm lớp) và test (đánh giá)
    extractor = tf.keras.Model(model.input, [model.output, model.get_layer("gap").output])
    for name in ("train", "test"):
        probs, embs = [], []
        for imgs, _ in ds(split[name], False):
            p, e = extractor(imgs, training=False); probs.append(p.numpy()); embs.append(e.numpy())
        X[name], Y[name] = np.concatenate(embs), np.array([y for _, y in split[name]])
        if name == "test":
            test_probs = np.concatenate(probs)

# 6. Đánh giá trên tập test (chưa dùng khi học)
def unit(a):
    return a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)
probs = test_probs if test_probs is not None else head.predict(X["test"], batch_size=1024, verbose=0)
pred, y = probs.argmax(1), Y["test"]
top5 = (np.argsort(-probs, 1)[:, :5] == y[:, None]).any(1).mean()
per_class = []
for i, c in enumerate(class_names):
    tp = int(((pred == i) & (y == i)).sum()); fp = int(((pred == i) & (y != i)).sum()); fn = int(((pred != i) & (y == i)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0; rec = tp / (tp + fn) if tp + fn else 0.0
    per_class.append(dict(name=c, precision=prec, recall=rec, f1=2 * prec * rec / (prec + rec) if prec + rec else 0.0, test=int((y == i).sum())))
pairs = {}
for a, b in zip(y, pred):
    if a != b:
        pairs[(a, b)] = pairs.get((a, b), 0) + 1
# Kết luận khi độ tin cậy >= ngưỡng: bao nhiêu % ảnh được kết luận và đúng bao nhiêu % (để chọn PEST_MIN_PROB trong app)
conf = probs.max(1)
thresholds = [dict(min_prob=t, coverage=float((conf >= t).mean()), accuracy=float((pred[conf >= t] == y[conf >= t]).mean()) if (conf >= t).any() else None)
              for t in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8)]
metrics = dict(classes=n, images={k: int(len(v)) for k, v in Y.items()}, accuracy=float((pred == y).mean()), top5=float(top5),
               macro_f1=float(np.mean([p["f1"] for p in per_class])), finetune_epochs=args.finetune_epochs, hidden=args.hidden,
               unfreeze=args.unfreeze if args.finetune_epochs else 0, label_smoothing=args.label_smoothing if args.finetune_epochs else 0,
               train_minutes=round((time.time() - T_START) / 60, 1), thresholds=thresholds,
               worst=sorted(per_class, key=lambda p: p["f1"])[:15],
               confused=[dict(true=class_names[a], pred=class_names[b], n=k) for (a, b), k in sorted(pairs.items(), key=lambda x: -x[1])[:20]],
               per_class=per_class)

# 7. Lưu mô hình, thứ tự lớp, tâm vector mỗi lớp (để nhận ra ảnh không phải sâu hại, như class_centroids.npz của mô hình bệnh lá)
path = os.path.join(MODELS, "pest_model.keras")
model.save(path, include_optimizer=False)
with open(os.path.join(MODELS, "pest_class_names.json"), "w", encoding="utf-8") as f:
    json.dump(class_names, f, ensure_ascii=False, indent=1)
embed_key = file_key(path)
tr = unit(X["train"])
centroids = unit(np.vstack([tr[Y["train"] == i].mean(0) for i in range(n)])).astype(np.float32)
np.savez(os.path.join(MODELS, "pest_centroids.npz"), centroids=centroids, embed_key=embed_key, class_names=np.array(class_names))
fam = (unit(X["test"]) @ centroids.T).max(1)
metrics["familiarity_test"] = {f"p{q}": float(np.percentile(fam, q)) for q in (1, 5, 10, 50)}
with open(os.path.join(RESULTS, "pest_metrics.json"), "w", encoding="utf-8") as f:
    json.dump(metrics, f, ensure_ascii=False, indent=1)
print(f"\nTest: accuracy {metrics['accuracy']:.4f}, top-5 {metrics['top5']:.4f}, macro-F1 {metrics['macro_f1']:.4f}")
for t in thresholds:
    print(f"  độ tin cậy >= {t['min_prob']:.1f}: kết luận {t['coverage']:.1%} ảnh, đúng {t['accuracy'] or 0:.1%}")
print(f"Độ quen thuộc ảnh test (giống tâm loài nhất): {metrics['familiarity_test']}")
print(f"Đã lưu {path}, pest_class_names.json, pest_centroids.npz; chi tiết: {os.path.join(RESULTS, 'pest_metrics.json')}")
