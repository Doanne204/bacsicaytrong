"""Huấn luyện YOLO11-cls (Ultralytics) trên INSECT204 với đúng phép chia của train_pests.py rồi đánh giá trên cùng 31.312 ảnh test,
cùng các chỉ số như results/pest_metrics.json để so với MobileNetV3Large. Chạy bằng môi trường riêng .venv-yolo (PyTorch + CUDA):
    .venv-yolo\\Scripts\\python.exe yolo\\train_yolo.py --model yolo11s-cls --epochs 30
Trọng số khởi đầu (ImageNet) lấy ở thư mục Models đi kèm bộ dữ liệu. Kết quả: results/yolo/<model>/metrics.json, mô hình
yolo/runs/<model>/weights/best.pt."""
import argparse, json, os, sys, time
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def evaluate(weights, data, imgsz):
    """Độ chính xác trên tập test: accuracy, top-5, macro-F1, bảng ngưỡng độ tin cậy, từng lớp."""
    from ultralytics import YOLO
    best = YOLO(weights)
    names = [best.names[i] for i in range(len(best.names))]
    test_dir = os.path.join(data, "test")
    files, y = [], []
    for ci, c in enumerate(names):
        for f in sorted(os.listdir(os.path.join(test_dir, c))):
            files.append(os.path.join(test_dir, c, f)); y.append(ci)
    y = np.array(y)
    probs = np.zeros((len(files), len(names)), dtype="float32")
    t = time.time()
    for i in range(0, len(files), 256):
        for j, r in enumerate(best.predict(files[i:i + 256], imgsz=imgsz, batch=256, device=0, half=True, verbose=False)):
            probs[i + j] = r.probs.data.float().cpu().numpy()
    pred = probs.argmax(1)
    f1s, per_class = [], []
    for ci, c in enumerate(names):
        tp = int(((pred == ci) & (y == ci)).sum()); fp = int(((pred == ci) & (y != ci)).sum()); fn = int(((pred != ci) & (y == ci)).sum())
        prec = tp / (tp + fp) if tp + fp else 0.0; rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        f1s.append(f1); per_class.append(dict(name=c, precision=prec, recall=rec, f1=f1, support=tp + fn))
    conf = probs.max(1)
    thresholds = [dict(min_prob=t, coverage=float((conf >= t).mean()),
                       accuracy=float((pred[conf >= t] == y[conf >= t]).mean()) if (conf >= t).any() else None)
                  for t in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8)]
    return dict(images=len(files), classes=len(names), accuracy=float((pred == y).mean()),
                top5=float((np.argsort(-probs, 1)[:, :5] == y[:, None]).any(1).mean()), macro_f1=float(np.mean(f1s)),
                thresholds=thresholds, params=int(sum(x.numel() for x in best.model.parameters())),
                size_mb=os.path.getsize(weights) / 1e6, test_seconds_gpu=time.time() - t, per_class=per_class)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="yolo11s-cls")
    p.add_argument("--weights_dir", default=os.path.join(ROOT, "dataset", "INSECT204-A Novel Large-Scale Benchmark Dataset fo", "Models"))
    p.add_argument("--data", default=os.path.join(ROOT, "yolo", "insect204"))
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch", type=int, default=128)
    p.add_argument("--imgsz", type=int, default=224)
    p.add_argument("--lr0", type=float, default=0.001)
    p.add_argument("--patience", type=int, default=6)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--fraction", type=float, default=1.0, help="chỉ dùng một phần tập train (chạy thử)")
    p.add_argument("--eval_only", action="store_true")
    a = p.parse_args()

    from ultralytics import YOLO, settings
    import ultralytics.engine.trainer as trainer
    settings.update({"sync": False})  # không gửi thống kê sử dụng
    # Kiểm tra AMP của Ultralytics tải thêm yolo26n.pt; RTX 3060 không nằm trong danh sách GPU lỗi AMP nên bật thẳng
    trainer.check_amp = lambda model: True

    run_dir = os.path.join(ROOT, "yolo", "runs", a.model)
    out_dir = os.path.join(ROOT, "results", "yolo", a.model)
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    if not a.eval_only:
        YOLO(os.path.join(a.weights_dir, f"{a.model}.pt")).train(
            data=a.data, epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, workers=a.workers, device=0, fraction=a.fraction,
            optimizer="AdamW", lr0=a.lr0, cos_lr=True, warmup_epochs=1, patience=a.patience, seed=42, deterministic=False,
            project=os.path.join(ROOT, "yolo", "runs"), name=a.model, exist_ok=True, plots=False, amp=True)
    m = dict(model=a.model, epochs=a.epochs, imgsz=a.imgsz, train_minutes=None if a.eval_only else (time.time() - t0) / 60)
    m.update(evaluate(os.path.join(run_dir, "weights", "best.pt"), a.data, a.imgsz))
    with open(os.path.join(out_dir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)
    print(f"{a.model}: test accuracy {m['accuracy']:.4f}, top-5 {m['top5']:.4f}, macro-F1 {m['macro_f1']:.4f}, "
          f"{m['params'] / 1e6:.2f}M tham số, {m['size_mb']:.1f} MB", file=sys.stderr)


if __name__ == "__main__":  # Windows: worker DataLoader import lại file này
    main()
