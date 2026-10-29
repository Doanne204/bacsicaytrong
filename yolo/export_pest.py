"""Đưa mô hình YOLO11-cls đã huấn luyện (train_yolo.py) vào app làm mô hình sâu hại chính. Chạy bằng .venv-yolo (PyTorch + CUDA):
    .venv-yolo\\Scripts\\python.exe yolo\\export_pest.py --model yolo11m-cls
1. Xuất ONNX hai đầu ra: xác suất 204 loài và vector đặc trưng 1280 chiều (đầu vào lớp Linear cuối) -> models/pest_model.onnx;
   app chạy bằng onnxruntime trên CPU (không cần PyTorch), tiền xử lý giống hệt pest_preprocess() trong model_service.py.
2. Tâm vector mỗi loài từ ảnh train -> models/pest_centroids.npz (nhận ra ảnh không phải côn trùng / loài chưa học).
3. Đánh giá trên 31.312 ảnh test bằng đúng đường xử lý của app -> results/pest_metrics.json (trang quản trị "Đánh giá mô hình"):
   accuracy, top-5, macro-F1, bảng ngưỡng độ tin cậy, loài kém nhất, cặp hay nhầm, độ quen thuộc của ảnh test và của ảnh lá
   PlantVillage (để chọn PEST_FAMILIAR_MIN, PEST_MIN_PROB trong client/routes.py).
Mô hình cũ (MobileNetV3Large của train_pests.py) được chép sang backups/ trước khi ghi đè."""
import argparse, hashlib, json, os, random, shutil, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import torch
from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from model_service import pest_preprocess  # noqa: E402  (cùng một hàm tiền xử lý với app)

MODELS, RESULTS = os.path.join(ROOT, "models"), os.path.join(ROOT, "results")


class Dual(torch.nn.Module):
    """Mạng YOLO11-cls trả về (xác suất, vector đặc trưng trước lớp Linear)."""
    def __init__(self, net):
        super().__init__()
        self.body, self.head = net.model[:-1], net.model[-1]

    def forward(self, x):
        for m in self.body:
            x = m(x)
        h = self.head
        z = h.pool(h.conv(x)).flatten(1)
        return h.linear(z).softmax(1), z


def file_key(path):  # giống model_service.file_key
    with open(path, "rb") as f:
        return f"{os.path.basename(path)}:{hashlib.sha256(f.read()).hexdigest()[:16]}"


def unit(a):
    return a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)


def run(net, files, batch=256):
    """Xác suất và vector đặc trưng (đã chuẩn hóa) cho danh sách file ảnh, tiền xử lý bằng pest_preprocess."""
    def load(f):
        with open(f, "rb") as fh:
            return pest_preprocess(fh.read(), exif=False)
    probs, feats = [], []
    with ThreadPoolExecutor(8) as ex, torch.no_grad():
        for i in range(0, len(files), batch):
            x = torch.from_numpy(np.stack(list(ex.map(load, files[i:i + batch])))).cuda()
            p, z = net(x)
            probs.append(p.float().cpu().numpy()); feats.append(z.float().cpu().numpy())
            print(f"\r{min(i + batch, len(files))}/{len(files)}", end="", file=sys.stderr)
    print(file=sys.stderr)
    return np.concatenate(probs), unit(np.concatenate(feats))


def listing(split_dir, names):
    files, y = [], []
    for ci, c in enumerate(names):
        for f in sorted(os.listdir(os.path.join(split_dir, c))):
            files.append(os.path.join(split_dir, c, f)); y.append(ci)
    return files, np.array(y)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="yolo11m-cls")
    p.add_argument("--data", default=os.path.join(ROOT, "yolo", "insect204"))
    p.add_argument("--leaves", default=os.path.join(ROOT, "dataset", "Plant_leave_diseases_dataset_without_augmentation"))
    a = p.parse_args()
    from ultralytics import YOLO
    weights = os.path.join(ROOT, "yolo", "runs", a.model, "weights", "best.pt")
    yolo = YOLO(weights)
    names = [yolo.names[i] for i in range(len(yolo.names))]
    net = Dual(yolo.model.float().eval()).cuda().eval()

    # 0. Sao lưu mô hình sâu hại đang dùng
    stamp = time.strftime("%Y%m%d-%H%M")
    bak = os.path.join(ROOT, "backups", f"pest_before_{a.model}_{stamp}")
    os.makedirs(bak, exist_ok=True)
    for f in ("pest_model.keras", "pest_model.onnx", "pest_class_names.json", "pest_centroids.npz"):
        if os.path.exists(os.path.join(MODELS, f)):
            shutil.copy2(os.path.join(MODELS, f), bak)
    if os.path.exists(os.path.join(RESULTS, "pest_metrics.json")):
        shutil.copy2(os.path.join(RESULTS, "pest_metrics.json"), bak)

    # 1. Xuất ONNX (CPU, float32), kiểm tra khớp với PyTorch
    onnx_path = os.path.join(MODELS, "pest_model.onnx")
    cpu = Dual(YOLO(weights).model.float().eval()).eval()
    torch.onnx.export(cpu, torch.zeros(1, 3, 224, 224), onnx_path, input_names=["image"], output_names=["probs", "feats"],
                      dynamic_axes={"image": {0: "n"}, "probs": {0: "n"}, "feats": {0: "n"}}, opset_version=17, dynamo=False)
    with open(os.path.join(MODELS, "pest_class_names.json"), "w", encoding="utf-8") as f:
        json.dump(names, f, ensure_ascii=False, indent=1)
    key = file_key(onnx_path)
    print("Đã xuất", onnx_path, f"{os.path.getsize(onnx_path) / 1e6:.1f} MB", key, file=sys.stderr)

    # Ảnh qua đường xử lý của app phải cho cùng kết quả với Ultralytics predict (Resize 224 + CenterCrop, RGB, /255)
    test_files, y_test = listing(os.path.join(a.data, "test"), names)
    sample = test_files[::997][:32]
    ours, _ = run(net, sample)
    theirs = np.stack([r.probs.data.float().cpu().numpy() for r in yolo.predict(sample, imgsz=224, verbose=False)])
    print("Lệch tối đa so với Ultralytics:", float(np.abs(ours - theirs).max()), file=sys.stderr)

    # 2. Tâm vector mỗi loài từ ảnh train
    train_files, y_train = listing(os.path.join(a.data, "train"), names)
    _, f_train = run(net, train_files)
    centroids = unit(np.vstack([f_train[y_train == i].mean(0) for i in range(len(names))])).astype(np.float32)
    np.savez(os.path.join(MODELS, "pest_centroids.npz"), centroids=centroids, embed_key=key, class_names=np.array(names))

    # 3. Đánh giá trên tập test + ảnh lá PlantVillage (ảnh không phải côn trùng)
    probs, f_test = run(net, test_files)
    pred, conf = probs.argmax(1), probs.max(1)
    fam = (f_test @ centroids.T).max(1)
    per_class, pairs = [], {}
    for ci, c in enumerate(names):
        tp = int(((pred == ci) & (y_test == ci)).sum()); fp = int(((pred == ci) & (y_test != ci)).sum()); fn = int(((pred != ci) & (y_test == ci)).sum())
        prec = tp / (tp + fp) if tp + fp else 0.0; rec = tp / (tp + fn) if tp + fn else 0.0
        per_class.append(dict(name=c, precision=prec, recall=rec, f1=2 * prec * rec / (prec + rec) if prec + rec else 0.0, test=tp + fn))
    for t, q in zip(y_test, pred):
        if t != q:
            pairs[(int(t), int(q))] = pairs.get((int(t), int(q)), 0) + 1
    rng = random.Random(42)
    leaf_files = [os.path.join(d, f) for d in (os.path.join(a.leaves, c) for c in sorted(os.listdir(a.leaves)) if c != "Background_without_leaves")
                  for f in sorted(os.listdir(d))]
    leaf_files = rng.sample(leaf_files, 600)
    lp, lf = run(net, leaf_files)
    leaf_fam, leaf_conf = (lf @ centroids.T).max(1), lp.max(1)
    gate = []  # chế độ Tự nhận diện: chuyển sang sâu hại khi độ quen >= T và độ tin cậy >= 0.6 (LOW_CONF)
    for t in (0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7):
        ok = (fam >= t) & (conf >= 0.6)
        gate.append(dict(familiar_min=t, pests_familiar=float((fam >= t).mean()), pests_switched=float(ok.mean()),
                         switched_accuracy=float((pred[ok] == y_test[ok]).mean()) if ok.any() else None,
                         leaves_familiar=float((leaf_fam >= t).mean()), leaves_switched=float(((leaf_fam >= t) & (leaf_conf >= 0.6)).mean())))
    n_val = sum(len(os.listdir(os.path.join(a.data, "val", c))) for c in names)
    metrics = dict(model=a.model, architecture=a.model.replace("yolo", "YOLO"), classes=len(names),
                   images=dict(train=len(train_files), val=n_val, test=len(test_files)),
                   accuracy=float((pred == y_test).mean()), top5=float((np.argsort(-probs, 1)[:, :5] == y_test[:, None]).any(1).mean()),
                   macro_f1=float(np.mean([c["f1"] for c in per_class])), params=int(sum(x.numel() for x in cpu.parameters())),
                   size_mb=os.path.getsize(onnx_path) / 1e6, embed_key=key,
                   thresholds=[dict(min_prob=t, coverage=float((conf >= t).mean()),
                                    accuracy=float((pred[conf >= t] == y_test[conf >= t]).mean()) if (conf >= t).any() else None)
                               for t in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)],
                   worst=sorted(per_class, key=lambda c: c["f1"])[:15],
                   confused=[dict(true=names[i], pred=names[j], n=k) for (i, j), k in sorted(pairs.items(), key=lambda x: -x[1])[:20]],
                   per_class=per_class, familiarity_test={f"p{q}": float(np.percentile(fam, q)) for q in (1, 5, 10, 50)},
                   familiarity_leaves={f"p{q}": float(np.percentile(leaf_fam, q)) for q in (50, 90, 99)}, auto_gate=gate)
    with open(os.path.join(RESULTS, "pest_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=1)
    print(f"accuracy {metrics['accuracy']:.4f}, top-5 {metrics['top5']:.4f}, macro-F1 {metrics['macro_f1']:.4f}", file=sys.stderr)
    for t in metrics["thresholds"]:
        print("ngưỡng", t, file=sys.stderr)
    for g in gate:
        print("Tự nhận diện", g, file=sys.stderr)
    print("Độ quen ảnh test", metrics["familiarity_test"], "ảnh lá", metrics["familiarity_leaves"], file=sys.stderr)
    print("Mô hình cũ sao lưu ở", bak, file=sys.stderr)


if __name__ == "__main__":
    main()
