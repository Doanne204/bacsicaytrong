"""So sánh kiến trúc cho bài toán bệnh lá (PlantVillage): MobileNetV3Large (đang dùng trong app), EfficientNet-B0 và ViT-B/16.
Cùng dữ liệu, cùng cách chia 70/15/15 (SEED 42, giống train.py), cùng augmentation, cùng quy trình 2 giai đoạn
(học lớp phân loại rồi tinh chỉnh một phần backbone) và cùng tập test; đo thêm số tham số, dung lượng, thời gian suy luận CPU.

Chạy trên Colab (GPU) bằng notebooks/so_sanh_kien_truc.ipynb, hoặc tại máy:
  python compare_models.py --all --data dataset/Plant_leave_diseases_dataset_without_augmentation --epochs 8 --fine_tune_epochs 4
  python compare_models.py --arch efficientnetb0 --data ... --limit_per_class 60 --epochs 1   (thử nhanh)
Kết quả: results/compare/<kiến trúc>/ (overall_metrics.csv, classification_report.csv, confusion_matrix.png, training_history.csv)
và results/compare/summary.csv + summary.png (bảng, biểu đồ so sánh) để trang quản trị "Đánh giá mô hình" hiển thị.
ViT cần gói keras-hub (pip install keras-hub) và tải trọng số ImageNet (~330 MB) lần đầu.
"""
import argparse, csv, json, os, time
import numpy as np
import tensorflow as tf
try:
    from sklearn.model_selection import train_test_split
except ImportError:  # chưa pip install -r requirements.txt: vẫn chạy được, nhưng cách chia tập không trùng hoàn toàn với train.py
    train_test_split = None

ARCHS = {
    "mobilenetv3": "MobileNetV3Large",
    "efficientnetb0": "EfficientNet-B0",
    "vit": "ViT-B/16",
}
IMG_SIZE, SEED, AUTOTUNE = 224, 42, tf.data.AUTOTUNE
IMG_EXTS = (".bmp", ".gif", ".jpeg", ".jpg", ".png")
VIT_PRESET = "vit_base_patch16_224_imagenet"

def write_csv(path, rows, fields=None):
    """Ghi danh sách dict ra CSV (utf-8-sig để Excel đọc đúng tiếng Việt)."""
    fields = fields or (list(rows[0]) if rows else [])
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

def list_images(data_dir, extra=(), min_images=20, limit_per_class=0):
    """Giống train.py: gộp ảnh theo thư mục lớp, bỏ lớp quá ít ảnh; limit_per_class > 0 để thử nhanh."""
    files_by_class = {}
    for d in [data_dir] + list(extra):
        if not os.path.isdir(d):
            print(f"Bỏ qua thư mục không tồn tại: {d}")
            continue
        for name in os.listdir(d):
            if not os.path.isdir(os.path.join(d, name)) or name.startswith("."):
                continue
            for root, _, files in os.walk(os.path.join(d, name)):
                files_by_class.setdefault(name, []).extend(os.path.join(root, f) for f in sorted(files) if f.lower().endswith(IMG_EXTS))
    class_names = sorted(c for c, fs in files_by_class.items() if len(fs) >= min_images)
    if limit_per_class:
        rng = np.random.RandomState(SEED)
        files_by_class = {c: [fs[i] for i in sorted(rng.choice(len(fs), min(limit_per_class, len(fs)), replace=False))] for c, fs in files_by_class.items()}
    paths = np.array([p for c in class_names for p in files_by_class[c]])
    labels = np.array([i for i, c in enumerate(class_names) for _ in files_by_class[c]])
    return class_names, paths, labels

def split(paths, labels):
    """70/15/15 stratified theo lớp, giống train.py (cùng sklearn + SEED thì trùng từng ảnh)."""
    if train_test_split:
        train_p, rest_p, train_y, rest_y = train_test_split(paths, labels, test_size=0.30, stratify=labels, random_state=SEED)
        val_p, test_p, val_y, test_y = train_test_split(rest_p, rest_y, test_size=0.50, stratify=rest_y, random_state=SEED)
        return (train_p, train_y), (val_p, val_y), (test_p, test_y)
    print("Không có scikit-learn: chia stratified bằng numpy (khác train.py ở từng ảnh, cùng tỉ lệ 70/15/15)")
    rng = np.random.RandomState(SEED)
    idx = {k: [] for k in range(3)}
    for c in np.unique(labels):
        ii = rng.permutation(np.where(labels == c)[0])
        n_tr, n_va = int(round(len(ii) * 0.7)), int(round(len(ii) * 0.15))
        idx[0] += list(ii[:n_tr]); idx[1] += list(ii[n_tr:n_tr + n_va]); idx[2] += list(ii[n_tr + n_va:])
    return tuple((paths[np.array(idx[k])], labels[np.array(idx[k])]) for k in range(3))

def evaluate(y_true, y_prob, class_names):
    """Chỉ số từ ma trận nhầm lẫn (không cần sklearn): accuracy, top-3, macro/weighted precision-recall-F1, báo cáo từng lớp."""
    n = len(class_names)
    y_pred = y_prob.argmax(1)
    cm = np.zeros((n, n), dtype=int)
    np.add.at(cm, (y_true, y_pred), 1)
    tp, support, predicted = np.diag(cm).astype(float), cm.sum(1), cm.sum(0)
    prec = np.divide(tp, predicted, out=np.zeros(n), where=predicted > 0)
    rec = np.divide(tp, support, out=np.zeros(n), where=support > 0)
    f1 = np.divide(2 * prec * rec, prec + rec, out=np.zeros(n), where=(prec + rec) > 0)
    w = support / max(1, support.sum())
    top3 = float(np.mean([t in p for t, p in zip(y_true, np.argsort(-y_prob, axis=1)[:, :3])])) if n > 3 else 1.0
    metrics = {"Accuracy": float(tp.sum() / len(y_true)), "Top-3 Accuracy": top3, "Macro Precision": float(prec.mean()), "Macro Recall": float(rec.mean()),
               "Macro F1-score": float(f1.mean()), "Weighted F1-score": float((f1 * w).sum())}
    report = [{"": c, "precision": prec[i], "recall": rec[i], "f1-score": f1[i], "support": int(support[i])} for i, c in enumerate(class_names)]
    report += [{"": "accuracy", "precision": metrics["Accuracy"], "recall": metrics["Accuracy"], "f1-score": metrics["Accuracy"], "support": len(y_true)},
               {"": "macro avg", "precision": prec.mean(), "recall": rec.mean(), "f1-score": f1.mean(), "support": len(y_true)},
               {"": "weighted avg", "precision": (prec * w).sum(), "recall": (rec * w).sum(), "f1-score": (f1 * w).sum(), "support": len(y_true)}]
    return metrics, report, cm

def load_image(path, label):
    img = tf.io.decode_image(tf.io.read_file(path), channels=3, expand_animations=False)
    return tf.image.resize(img, (IMG_SIZE, IMG_SIZE)), label  # float32 0-255, giống model_service.py

def make_ds(p, y, batch, shuffle=False):
    ds = tf.data.Dataset.from_tensor_slices((p, y))
    if shuffle:
        ds = ds.shuffle(len(p), seed=SEED, reshuffle_each_iteration=True)
    return ds.map(load_image, num_parallel_calls=AUTOTUNE).batch(batch).prefetch(AUTOTUNE)

def augmentation():
    return tf.keras.Sequential([tf.keras.layers.RandomFlip("horizontal"), tf.keras.layers.RandomRotation(0.08),
                                tf.keras.layers.RandomZoom(0.10), tf.keras.layers.RandomContrast(0.10)], name="data_augmentation")

def build(arch, num_classes):
    """Trả về (model, backbone, hàm mở khóa tinh chỉnh). Mọi kiến trúc: ảnh 0-255 -> tiền xử lý riêng -> backbone -> Dropout -> Dense softmax."""
    inputs = tf.keras.Input(shape=(IMG_SIZE, IMG_SIZE, 3), name="image")
    x = augmentation()(inputs)
    if arch == "mobilenetv3":
        base = tf.keras.applications.MobileNetV3Large(input_shape=(IMG_SIZE, IMG_SIZE, 3), include_top=False, weights="imagenet", include_preprocessing=True)
        base.trainable = False
        x = tf.keras.layers.GlobalAveragePooling2D()(base(x, training=False))
        unfreeze = lambda: _unfreeze_cnn(base, 30)
    elif arch == "efficientnetb0":
        base = tf.keras.applications.EfficientNetB0(input_shape=(IMG_SIZE, IMG_SIZE, 3), include_top=False, weights="imagenet")  # tự chuẩn hóa 0-255
        base.trainable = False
        x = tf.keras.layers.GlobalAveragePooling2D()(base(x, training=False))
        unfreeze = lambda: _unfreeze_cnn(base, 40)
    elif arch == "vit":
        try:
            import keras_hub
        except ImportError as e:
            raise SystemExit("ViT cần gói keras-hub: pip install keras-hub") from e
        base = keras_hub.models.Backbone.from_preset(VIT_PRESET)  # ViTBackbone, đầu ra chuỗi token (batch, 197, 768)
        base.trainable = False
        x = keras_hub.layers.ImageConverter.from_preset(VIT_PRESET)(x)  # chuẩn hóa pixel đúng như lúc tiền huấn luyện
        x = base(x, training=False)[:, 0]  # token [CLS]
        unfreeze = lambda: _unfreeze_vit(base, 2)
    else:
        raise ValueError(arch)
    x = tf.keras.layers.Dropout(0.25)(x)
    outputs = tf.keras.layers.Dense(num_classes, activation="softmax")(x)
    return tf.keras.Model(inputs, outputs, name=f"plant_{arch}"), base, unfreeze

def _unfreeze_cnn(base, last_n):
    base.trainable = True
    for layer in base.layers[:-last_n]:
        layer.trainable = False
    for layer in base.layers:
        if isinstance(layer, tf.keras.layers.BatchNormalization):
            layer.trainable = False

def _unfreeze_vit(base, last_blocks):
    """Mở khóa `last_blocks` khối transformer cuối (ViTBackbone.encoder.encoder_layers) và LayerNorm cuối; phần còn lại giữ nguyên.
    Không nhận ra cấu trúc (phiên bản keras-hub khác) thì tinh chỉnh toàn bộ với LR nhỏ."""
    base.trainable = True
    enc = getattr(base, "encoder", None)
    blocks = list(getattr(enc, "encoder_layers", None) or [])
    if not blocks:
        print("Không tìm thấy encoder_layers của ViT: tinh chỉnh toàn bộ backbone")
        return
    for l in base.layers:
        if l is not enc:
            l.trainable = False
    for b in blocks[:-last_blocks]:
        b.trainable = False

def callbacks(ckpt):
    return [tf.keras.callbacks.ModelCheckpoint(ckpt, monitor="val_accuracy", mode="max", save_best_only=True, verbose=0),
            tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=3, restore_best_weights=True, verbose=1),
            tf.keras.callbacks.TerminateOnNaN()]

def cpu_latency(model, images, n=30):
    """ms/ảnh khi suy luận từng ảnh một trên CPU (như app chạy trên máy không GPU)."""
    with tf.device("/CPU:0"):
        model.predict(images[:1], verbose=0)  # khởi động
        t = time.perf_counter()
        for img in images[:n]:
            model.predict(img[None], verbose=0)
        return (time.perf_counter() - t) / min(n, len(images)) * 1000

def run(arch, data, out, args, class_names, tr, va, te):
    name = ARCHS[arch]
    odir = os.path.join(out, arch)
    os.makedirs(odir, exist_ok=True)
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
    tf.keras.utils.set_random_seed(SEED)
    train, val, test = make_ds(*tr, args.batch, shuffle=True), make_ds(*va, args.batch), make_ds(*te, args.batch)
    model, base, unfreeze = build(arch, len(class_names))
    ckpt = os.path.join(odir, "best.keras")
    t0 = time.time()
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    h1 = model.fit(train, validation_data=val, epochs=args.epochs, callbacks=callbacks(ckpt), verbose=args.verbose)
    h2 = None
    if args.fine_tune_epochs:
        unfreeze()
        model.compile(optimizer=tf.keras.optimizers.Adam(args.fine_tune_lr), loss="sparse_categorical_crossentropy", metrics=["accuracy"])
        h2 = model.fit(train, validation_data=val, epochs=args.fine_tune_epochs, callbacks=callbacks(ckpt), verbose=args.verbose)
    train_time = time.time() - t0
    if os.path.exists(ckpt):
        model.load_weights(ckpt)
    hist = {k: h1.history.get(k, []) + (h2.history.get(k, []) if h2 else []) for k in sorted(set(h1.history) | (set(h2.history) if h2 else set()))}
    write_csv(os.path.join(odir, "training_history.csv"), [{k: v[i] for k, v in hist.items() if i < len(v)} for i in range(max(map(len, hist.values())))], list(hist))

    y_true = te[1]
    t = time.time()
    y_prob = model.predict(test, verbose=0)
    gpu_ms = (time.time() - t) / len(y_true) * 1000
    n_cls = len(class_names)
    metrics, report, cm = evaluate(y_true, y_prob, class_names)
    write_csv(os.path.join(odir, "overall_metrics.csv"), [metrics])
    write_csv(os.path.join(odir, "classification_report.csv"), report)  # cùng dạng với results/classification_report.csv của train.py
    np.savetxt(os.path.join(odir, "confusion_matrix.csv"), cm, fmt="%d", delimiter=",")
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(18, 18))
        ax.imshow(cm, cmap="Blues")
        ax.set_xticks(range(n_cls), class_names, rotation=90); ax.set_yticks(range(n_cls), class_names)
        ax.set_xlabel("Dự đoán"); ax.set_ylabel("Thực tế")
        for i in range(n_cls):
            for j in range(n_cls):
                ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=6, color="white" if cm[i, j] > cm.max() / 2 else "black")
        plt.title(f"Confusion Matrix - {name}"); plt.tight_layout(); plt.savefig(os.path.join(odir, "confusion_matrix.png"), dpi=150, bbox_inches="tight"); plt.close()
    except Exception as e:
        print("Không vẽ được ma trận nhầm lẫn (cần matplotlib):", e)

    # Mô hình để triển khai (không có augmentation), đo dung lượng và tốc độ CPU
    model_path = os.path.join(odir, "model.keras")
    model.save(model_path, include_optimizer=False)
    sample = np.stack([x.numpy() for x, _ in test.unbatch().take(30)])
    params = model.count_params()
    row = dict(arch=arch, name=name, accuracy=metrics["Accuracy"], top3=metrics["Top-3 Accuracy"], macro_f1=metrics["Macro F1-score"],
               weighted_f1=metrics["Weighted F1-score"], params_m=round(params / 1e6, 2), size_mb=round(os.path.getsize(model_path) / 2 ** 20, 1),
               cpu_ms=round(cpu_latency(model, sample), 1), batch_ms=round(gpu_ms, 2), train_min=round(train_time / 60, 1),
               epochs=len(hist.get("loss", [])), best_val_acc=max(hist.get("val_accuracy", [0])), test_images=len(y_true), classes=n_cls)
    print("\n".join(f"{k:14s}: {v}" for k, v in row.items()))
    with open(os.path.join(odir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(row, f, ensure_ascii=False, indent=2)
    if not args.keep_models:
        for p in (ckpt, model_path):
            if os.path.exists(p):
                os.remove(p)
    return row

def summarize(out):
    """Gộp summary.json của các kiến trúc đã chạy -> summary.csv, summary.png."""
    rows = []
    for arch in ARCHS:
        p = os.path.join(out, arch, "summary.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                rows.append(json.load(f))
    if not rows:
        return None
    write_csv(os.path.join(out, "summary.csv"), rows)
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        names = [r["name"] for r in rows]
        fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
        for ax, (col, title) in zip(axes, [("accuracy", "Accuracy trên tập test"), ("cpu_ms", "Suy luận CPU (ms/ảnh, thấp hơn tốt hơn)"), ("params_m", "Số tham số (triệu)")]):
            vals = [r[col] for r in rows]
            bars = ax.bar(names, vals, color=["#2f7d4f", "#d4a017", "#4c6ef5"][:len(rows)])
            ax.set_title(title); ax.bar_label(bars, fmt="%.3f" if col == "accuracy" else "%.1f", padding=2)
            if col == "accuracy":
                ax.set_ylim(max(0, min(vals) - 0.05), 1.0)
        plt.tight_layout(); plt.savefig(os.path.join(out, "summary.png"), dpi=150); plt.close()
    except Exception as e:
        print("Không vẽ được biểu đồ:", e)
    cols = ["name", "accuracy", "macro_f1", "params_m", "size_mb", "cpu_ms", "train_min"]
    print("\n=== SO SÁNH ===")
    print("  ".join(f"{c:>16s}" for c in cols))
    for r in rows:
        print("  ".join(f"{(round(r[c], 4) if isinstance(r[c], float) else r[c])!s:>16s}" for c in cols))
    return rows

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--arch", choices=list(ARCHS), action="append", help="Kiến trúc cần chạy (lặp lại được); --all chạy cả ba")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--fine_tune_epochs", type=int, default=4)
    ap.add_argument("--fine_tune_lr", type=float, default=1e-5)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--extra", nargs="*", default=[])
    ap.add_argument("--min_images", type=int, default=20)
    ap.add_argument("--limit_per_class", type=int, default=0, help="Chỉ lấy N ảnh mỗi lớp (thử nhanh)")
    ap.add_argument("--out", default=os.path.join("results", "compare"))
    ap.add_argument("--keep_models", action="store_true", help="Giữ file model.keras của từng kiến trúc (mỗi file 15-350 MB)")
    ap.add_argument("--verbose", type=int, default=1)
    args = ap.parse_args()
    archs = list(ARCHS) if args.all or not args.arch else args.arch
    class_names, paths, labels = list_images(os.path.abspath(args.data), [os.path.abspath(x) for x in args.extra], args.min_images, args.limit_per_class)
    if not len(paths):
        raise SystemExit(f"Không có ảnh trong {args.data}")
    tr, va, te = split(paths, labels)
    os.makedirs(args.out, exist_ok=True)
    write_csv(os.path.join(args.out, "split.csv"), [dict(path=p, **{"class": class_names[y]}, subset=s) for (ps, ys), s in zip((tr, va, te), ("train", "val", "test")) for p, y in zip(ps, ys)])
    with open(os.path.join(args.out, "class_names.json"), "w", encoding="utf-8") as f:
        json.dump(class_names, f, ensure_ascii=False, indent=2)
    print(f"Số lớp: {len(class_names)}; train/val/test: {len(tr[0])}/{len(va[0])}/{len(te[0])}; GPU: {tf.config.list_physical_devices('GPU') or 'không'}")
    for arch in archs:
        run(arch, args.data, args.out, args, class_names, tr, va, te)
    summarize(args.out)

if __name__ == "__main__":
    main()
