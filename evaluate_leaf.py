"""Đánh giá lại mô hình bệnh lá đang dùng (models/plant_model.keras hoặc best_plant_model.keras) trên PlantVillage, khi không còn
số liệu lúc huấn luyện (VD mô hình train ở máy khác). Chia tập giống hệt train.py (70/15/15 stratified, SEED 42, cùng thứ tự file),
đo accuracy trên cả 3 phần train/val/test, rồi ghi số liệu tập test vào results/ để trang quản trị "Đánh giá mô hình" hiển thị.

LƯU Ý: không biết chắc mô hình đã được huấn luyện với đúng cách chia này. Nếu lúc train dùng cách chia khác, một phần ảnh "test"
đã được mô hình học -> accuracy cao hơn thực tế. Nếu train đúng cách chia này thì accuracy tập train thường cao hơn tập test;
train xấp xỉ test thì không phân biệt được hai trường hợp. Số liệu chuẩn cho báo cáo nên lấy
từ lần huấn luyện lại có tập test riêng (train.py hoặc compare_models.py / notebooks/so_sanh_kien_truc.ipynb).

Chạy: python evaluate_leaf.py --data dataset/Plant_leave_diseases_dataset_without_augmentation
      thêm --subsets test để chỉ chạy tập test (nhanh hơn ~6 lần)
"""
import argparse, json, os, time
import numpy as np
import tensorflow as tf
from compare_models import evaluate, list_images, make_ds, split, write_csv

ROOT = os.path.dirname(os.path.abspath(__file__))
MODELS = [os.path.join(ROOT, "models", n) for n in ("plant_model.keras", "best_plant_model.keras")]

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=os.path.join("dataset", "Plant_leave_diseases_dataset_without_augmentation"))
    ap.add_argument("--model", default=next((p for p in MODELS if os.path.exists(p)), MODELS[0]))
    ap.add_argument("--subsets", nargs="+", default=["train", "val", "test"], choices=["train", "val", "test"])
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--out", default=os.path.join(ROOT, "results"))
    args = ap.parse_args()

    with open(os.path.join(ROOT, "models", "class_names.json"), encoding="utf-8") as f:
        model_classes = json.load(f)
    class_names, paths, labels = list_images(os.path.abspath(args.data))
    if class_names != model_classes:
        raise SystemExit(f"Lớp trong dữ liệu ({len(class_names)}) khác models/class_names.json ({len(model_classes)}): không đánh giá được")
    parts = dict(zip(("train", "val", "test"), split(paths, labels)))
    print(f"Mô hình: {args.model}\nSố lớp: {len(class_names)}; train/val/test: " + "/".join(str(len(parts[k][0])) for k in ("train", "val", "test")))
    model = tf.keras.models.load_model(args.model)

    acc, test_out = {}, None
    for name in [s for s in ("train", "val", "test") if s in args.subsets]:
        p, y = parts[name]
        t = time.time()
        prob = model.predict(make_ds(p, y, args.batch), verbose=0)
        metrics, report, cm = evaluate(y, prob, class_names)
        acc[name] = dict(accuracy=metrics["Accuracy"], macro_f1=metrics["Macro F1-score"], images=int(len(y)))
        print(f"{name:5s}: accuracy {metrics['Accuracy']:.4f}, macro-F1 {metrics['Macro F1-score']:.4f} ({len(y)} ảnh, {time.time() - t:.0f}s)", flush=True)
        if name == "test":
            test_out = (metrics, report, cm, p, y)

    os.makedirs(args.out, exist_ok=True)
    if test_out:
        metrics, report, cm, p, y = test_out
        write_csv(os.path.join(args.out, "overall_metrics.csv"), [metrics])
        write_csv(os.path.join(args.out, "classification_report.csv"), report)
        write_csv(os.path.join(args.out, "split.csv"), [dict(path=pp, **{"class": class_names[k]}, subset=s)
                                                         for s in ("train", "val", "test") for pp, k in zip(*parts[s])])
        plots(cm, report, class_names, args.out)
    gap = acc["train"]["accuracy"] - acc["test"]["accuracy"] if {"train", "test"} <= set(acc) else None
    info = dict(source="evaluate_leaf.py", model=os.path.basename(args.model),
                model_time=time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(args.model))),
                evaluated=time.strftime("%Y-%m-%d %H:%M"), subsets=acc, train_test_gap=gap,
                note="Đánh giá lại sau khi huấn luyện; không chắc tập test này chưa được dùng lúc huấn luyện")
    with open(os.path.join(args.out, "leaf_eval.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    if gap is not None:
        print(f"\nChênh lệch accuracy train - test: {gap * 100:.2f} điểm %"
              + (" (gần như bằng nhau: không xác định được tập test đã được học hay chưa)" if abs(gap) < 0.005 else ""))
    print(f"Đã ghi {args.out}: overall_metrics.csv, classification_report.csv, confusion_matrix.png, class_metrics.png, leaf_eval.json")

def plots(cm, report, class_names, out):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import ConfusionMatrixDisplay
    fig, ax = plt.subplots(figsize=(20, 20))
    ConfusionMatrixDisplay(cm, display_labels=class_names).plot(ax=ax, xticks_rotation="vertical", colorbar=False, values_format="d")
    plt.title("Confusion Matrix - MobileNetV3Large (đánh giá lại)"); plt.tight_layout()
    plt.savefig(os.path.join(out, "confusion_matrix.png"), dpi=150, bbox_inches="tight"); plt.close()
    rows = report[:len(class_names)]
    x = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(20, 7))
    for i, (k, lbl) in enumerate([("precision", "Precision"), ("recall", "Recall"), ("f1-score", "F1-score")]):
        ax.bar(x + (i - 1) * 0.27, [r[k] for r in rows], width=0.27, label=lbl)
    ax.set_xticks(x, [r[""] for r in rows], rotation=90); ax.set_ylim(0, 1.05); ax.set_ylabel("Score"); ax.legend()
    plt.title("Precision, Recall and F1-score by Class"); plt.tight_layout()
    plt.savefig(os.path.join(out, "class_metrics.png"), dpi=150, bbox_inches="tight"); plt.close()

if __name__ == "__main__":
    main()
