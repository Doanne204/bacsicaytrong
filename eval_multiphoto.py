"""Đo lợi ích của tra cứu nhiều ảnh (gộp bằng trung bình xác suất, như /api/predict) trên tập test, cho mô hình lá và mô hình sâu hại.
Bộ dữ liệu không có nhiều ảnh của cùng một cây nên đo hai cận:
  - Cận trên: 3 ảnh KHÁC NHAU cùng loài (3 cá thể độc lập, lỗi ít liên quan nhau) -> lạc quan hơn thực tế.
  - Cận dưới: 3 "lần chụp" của CÙNG một ảnh (cắt lệch, phóng, lật, đổi sáng ngẫu nhiên) -> gần với chụp lại cùng một lá/con sâu.
    python eval_multiphoto.py --per_class 20
Ghi results/multiphoto.json."""
import argparse, csv, json, os, random
import numpy as np
from PIL import Image, ImageEnhance, ImageOps

ROOT = os.path.dirname(os.path.abspath(__file__))
p = argparse.ArgumentParser()
p.add_argument("--per_class", type=int, default=20)
p.add_argument("--trials", type=int, default=3, help="số bộ 3 ảnh lấy cho mỗi ảnh gốc (cận trên)")
a = p.parse_args()
rng = random.Random(0)

import tensorflow as tf
from model_service import IMG_SIZE, PestService, pest_preprocess

def view(img, k, square=True):
    """Lần chụp thứ k (k=0: ảnh gốc): cắt 80-95% ở vị trí ngẫu nhiên, có thể lật ngang, đổi sáng/tương phản +-15%.
    square: thu về 224x224 cho mô hình lá; mô hình sâu hại tự đưa cạnh ngắn về 224 rồi cắt giữa (pest_preprocess)."""
    fit = (lambda im: im.resize((IMG_SIZE, IMG_SIZE))) if square else (lambda im: im)
    if k == 0:
        return fit(img)
    r = random.Random(k * 7919 + hash(img.size))
    s = r.uniform(0.8, 0.95); w, h = img.size; cw, ch = int(w * s), int(h * s)
    x, y = r.randint(0, w - cw), r.randint(0, h - ch)
    out = img.crop((x, y, x + cw, y + ch))
    if r.random() < 0.5:
        out = ImageOps.mirror(out)
    out = ImageEnhance.Brightness(out).enhance(r.uniform(0.85, 1.15))
    out = ImageEnhance.Contrast(out).enhance(r.uniform(0.85, 1.15))
    return fit(out)

def keras_probs(model, bs=64):
    def run(imgs):
        return np.concatenate([np.asarray(model(np.stack([np.asarray(x, dtype="float32") for x in imgs[i:i + bs]]), training=False))
                               for i in range(0, len(imgs), bs)])
    return run

def yolo_probs(session, bs=64):
    def run(imgs):
        return np.concatenate([session.run(None, {"image": np.stack([pest_preprocess(x, exif=False) for x in imgs[i:i + bs]])})[0]
                               for i in range(0, len(imgs), bs)])
    return run

def evaluate(name, probs_of, items, classes, square=True):
    """items: [(đường dẫn, chỉ số lớp)]; probs_of: danh sách ảnh PIL -> ma trận xác suất."""
    imgs = [Image.open(f).convert("RGB") for f, _ in items]
    y = np.array([c for _, c in items])
    p = [probs_of([view(im, k, square) for im in imgs]) for k in range(3)]  # 3 lần chụp mỗi ảnh
    single = (p[0].argmax(1) == y).mean()
    same = ((p[0] + p[1] + p[2]).argmax(1) == y).mean()
    by_class = {}
    for i, c in enumerate(y):
        by_class.setdefault(c, []).append(i)
    hits = []
    for i, c in enumerate(y):  # cận trên: ảnh i + 2 ảnh khác cùng lớp
        others = [j for j in by_class[c] if j != i]
        for _ in range(a.trials if len(others) >= 2 else 0):
            j, k = rng.sample(others, 2)
            hits.append((p[0][i] + p[0][j] + p[0][k]).argmax() == c)
    diff = float(np.mean(hits))
    two = []  # 2 ảnh khác nhau cùng lớp
    for i, c in enumerate(y):
        others = [j for j in by_class[c] if j != i]
        if others:
            two.append((p[0][i] + p[0][rng.choice(others)]).argmax() == c)
    out = dict(images=len(items), classes=len(classes), single=float(single), same_specimen_3=float(same), two_different=float(np.mean(two)),
               three_different=diff)
    print(f"{name}: 1 ảnh {single:.2%} | 3 lần chụp cùng mẫu {same:.2%} | 2 ảnh khác cá thể {np.mean(two):.2%} | 3 ảnh khác cá thể {diff:.2%}", flush=True)
    return out

results = {}
# ---- Lá (PlantVillage, tập test của train.py) ----
names = json.load(open(os.path.join(ROOT, "models", "class_names.json"), encoding="utf-8"))
rows = [r for r in csv.DictReader(open(os.path.join(ROOT, "results", "split.csv"), encoding="utf-8-sig")) if r["subset"] == "test"]
by = {}
for r in rows:
    by.setdefault(r["class"], []).append(r["path"])
items = [(f, names.index(c)) for c, fs in sorted(by.items()) for f in rng.sample(fs, min(a.per_class, len(fs)))]
results["leaf"] = evaluate("Lá (MobileNetV3Large)", keras_probs(tf.keras.models.load_model(os.path.join(ROOT, "models", "plant_model.keras"))), items, names)

# ---- Sâu hại (INSECT204, cùng tập test của train_pests.py / yolo/train_yolo.py) ----
pnames = json.load(open(os.path.join(ROOT, "models", "pest_class_names.json"), encoding="utf-8"))
proot = os.path.join(ROOT, "dataset", "INSECT204-A Novel Large-Scale Benchmark Dataset fo", "INSECT204")
by = {}
for r in csv.DictReader(open(os.path.join(ROOT, "results", "pest_split.csv"), encoding="utf-8-sig")):
    if r["split"] == "test":
        by.setdefault(r["class"], []).append(os.path.join(proot, r["file"]))
items = [(f, pnames.index(c)) for c, fs in sorted(by.items()) for f in rng.sample(fs, min(a.per_class, len(fs)))]
results["pest"] = evaluate("Sâu hại (YOLO11m-cls)", yolo_probs(PestService().session), items, pnames, square=False)

with open(os.path.join(ROOT, "results", "multiphoto.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=1)
