"""Huấn luyện MobileNetV3Large trên PlantVillage (mô hình bệnh lá của app).
Chạy: python train.py --data dataset/Plant_leave_diseases_dataset_without_augmentation
Thêm ảnh AI đã phân tích từ app (cùng cấu trúc thư mục lớp): --extra dataset_ai
Huấn luyện thử / ra thư mục riêng để so với mô hình đang dùng: --models_dir models/candidate --results_dir results/candidate

Quy trình (bản 2):
  1. Học lớp phân loại trên backbone ImageNet đóng băng (--epochs, LR 1e-3).
  2. Tinh chỉnh TOÀN BỘ backbone (--unfreeze -1; hoặc N lớp cuối) với LR khởi động dần rồi giảm theo cosine (--fine_tune_lr),
     label smoothing 0.1, augmentation mạnh hơn (lật dọc, xoay, phóng to, dịch, sáng tối, tương phản), EarlyStopping theo val_accuracy.
  BatchNormalization luôn chạy ở chế độ suy luận (dùng thống kê ImageNet) để tinh chỉnh ổn định với batch nhỏ.
Bản 1 (chỉ mở 30 lớp cuối, LR cố định 1e-5, 10+5 epoch) cho mô hình chưa học hết: accuracy train ~94,7%, test ~95%.
"""

import argparse
import json
import os
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from compare_models import write_csv  # ghi CSV bằng thư viện chuẩn (pandas bị Windows Application Control chặn trên máy này)
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, top_k_accuracy_score,
    classification_report, confusion_matrix, ConfusionMatrixDisplay,
)
from sklearn.model_selection import train_test_split

parser = argparse.ArgumentParser()
parser.add_argument("--data", required=True)
parser.add_argument("--epochs", type=int, default=3, help="Số epoch học lớp phân loại (backbone đóng băng)")
parser.add_argument("--fine_tune_epochs", type=int, default=15, help="Số epoch tinh chỉnh tối đa (dừng sớm nếu val_accuracy không tăng)")
parser.add_argument("--fine_tune_lr", type=float, default=1e-4, help="LR cao nhất khi tinh chỉnh (sau 1 epoch khởi động, giảm dần theo cosine)")
parser.add_argument("--unfreeze", type=int, default=-1, help="-1: tinh chỉnh toàn bộ backbone; N: chỉ N lớp cuối")
parser.add_argument("--label_smoothing", type=float, default=0.1)
parser.add_argument("--patience", type=int, default=4)
parser.add_argument("--batch", type=int, default=32)
parser.add_argument("--extra", nargs="*", default=[], help="Thư mục ảnh bổ sung cùng cấu trúc lớp, VD: dataset_ai")
parser.add_argument("--min_images", type=int, default=20, help="Bỏ qua lớp có ít ảnh hơn số này (không đủ để chia train/val/test)")
parser.add_argument("--limit_per_class", type=int, default=0, help="Chỉ lấy N ảnh mỗi lớp (thử nhanh)")
parser.add_argument("--models_dir", default="models")
parser.add_argument("--results_dir", default="results")
args = parser.parse_args()

IMG_SIZE = 224  # trùng model_service.IMG_SIZE
SEED = 42
AUTOTUNE = tf.data.AUTOTUNE
tf.keras.utils.set_random_seed(SEED)
MD, RD = args.models_dir, args.results_dir
os.makedirs(MD, exist_ok=True)
os.makedirs(RD, exist_ok=True)

# 1. Kiểm tra dữ liệu
data_dir = os.path.abspath(args.data)
if not os.path.isdir(data_dir):
    raise FileNotFoundError(f"Không tìm thấy thư mục dữ liệu: {data_dir}")

IMG_EXTS = (".bmp", ".gif", ".jpeg", ".jpg", ".png")
files_by_class = {}  # gộp ảnh của các thư mục có cùng tên lớp (dataset gốc + --extra)
for d in [data_dir] + [os.path.abspath(x) for x in args.extra]:
    if not os.path.isdir(d):
        print(f"Bỏ qua thư mục không tồn tại: {d}")
        continue
    for name in os.listdir(d):
        if not os.path.isdir(os.path.join(d, name)) or name.startswith("."):
            continue
        for root, _, files in os.walk(os.path.join(d, name)):
            files_by_class.setdefault(name, []).extend(
                os.path.join(root, f) for f in sorted(files) if f.lower().endswith(IMG_EXTS))
small = sorted(c for c, fs in files_by_class.items() if len(fs) < args.min_images)
if small:
    print(f"Bỏ qua {len(small)} lớp có dưới {args.min_images} ảnh: {small}")
# Thứ tự lớp sắp xếp giống image_dataset_from_directory để khớp với mô hình đã train trước đó
class_names = sorted(c for c in files_by_class if c not in small)
if args.limit_per_class:
    rng = np.random.RandomState(SEED)
    files_by_class = {c: [fs[i] for i in sorted(rng.choice(len(fs), min(args.limit_per_class, len(fs)), replace=False))]
                      for c, fs in files_by_class.items()}
num_classes = len(class_names)
paths = np.array([p for c in class_names for p in files_by_class[c]])
labels = np.array([i for i, c in enumerate(class_names) for _ in files_by_class[c]])
if len(paths) == 0:
    raise ValueError(f"Không có ảnh nào trong {data_dir}")

# Chia 70/15/15 theo từng ảnh, stratified theo lớp: 3 tập không trùng ảnh và đủ mọi lớp (giống evaluate_leaf.py, compare_models.py).
train_p, rest_p, train_y, rest_y = train_test_split(
    paths, labels, test_size=0.30, stratify=labels, random_state=SEED)
val_p, test_p, val_y, test_y = train_test_split(
    rest_p, rest_y, test_size=0.50, stratify=rest_y, random_state=SEED)

# Lưu tên lớp ngay từ đầu: app cần file này để nạp cả best_plant_model.keras nếu train bị dừng giữa chừng
with open(os.path.join(MD, "class_names.json"), "w", encoding="utf-8") as f:
    json.dump(class_names, f, ensure_ascii=False, indent=2)
write_csv(os.path.join(RD, "split.csv"), [{"path": p, "class": class_names[y], "subset": s}
                                           for ps, ys, s in [(train_p, train_y, "train"), (val_p, val_y, "val"), (test_p, test_y, "test")]
                                           for p, y in zip(ps, ys)])

def load_image(path, label):
    img = tf.io.decode_image(tf.io.read_file(path), channels=3, expand_animations=False)
    # resize bilinear ra float32 0-255, giống image_dataset_from_directory và model_service.py
    return tf.image.resize(img, (IMG_SIZE, IMG_SIZE)), tf.one_hot(label, num_classes)

def make_ds(p, y, shuffle=False):
    ds = tf.data.Dataset.from_tensor_slices((p, y))
    if shuffle:
        ds = ds.shuffle(len(p), seed=SEED, reshuffle_each_iteration=True)
    return ds.map(load_image, num_parallel_calls=AUTOTUNE).batch(args.batch).prefetch(AUTOTUNE)

train = make_ds(train_p, train_y, shuffle=True)
val = make_ds(val_p, val_y)
test = make_ds(test_p, test_y)  # không xáo trộn -> thứ tự nhãn trùng với test_y

print(f"\nSố lớp: {num_classes}")
print(f"Số ảnh train/val/test: {len(train_p)}/{len(val_p)}/{len(test_p)}")
print(f"GPU: {tf.config.list_physical_devices('GPU') or 'không (chạy CPU)'}")

# 2. Augmentation chỉ áp dụng khi training (ảnh lá chụp ở mọi hướng nên lật cả dọc)
augmentation = tf.keras.Sequential([
    tf.keras.layers.RandomFlip("horizontal_and_vertical"),
    tf.keras.layers.RandomRotation(0.15),
    tf.keras.layers.RandomZoom(0.15),
    tf.keras.layers.RandomTranslation(0.08, 0.08),
    tf.keras.layers.RandomBrightness(0.15, value_range=(0, 255)),
    tf.keras.layers.RandomContrast(0.15),
], name="data_augmentation")

# 3. MobileNetV3Large: preprocessing tích hợp (nhận ảnh 0-255). Cấu trúc giữ nguyên như bản 1 để app dùng được
#    (lớp GlobalAveragePooling2D cho vector đặc trưng và Grad-CAM).
base_model = tf.keras.applications.MobileNetV3Large(
    input_shape=(IMG_SIZE, IMG_SIZE, 3),
    include_top=False,
    weights="imagenet",
    include_preprocessing=True,
)
base_model.trainable = False

inputs = tf.keras.Input(shape=(IMG_SIZE, IMG_SIZE, 3), name="image")
x = augmentation(inputs)
x = base_model(x, training=False)  # BatchNorm ở chế độ suy luận cả khi tinh chỉnh
x = tf.keras.layers.GlobalAveragePooling2D()(x)
x = tf.keras.layers.Dropout(0.3)(x)
outputs = tf.keras.layers.Dense(num_classes, activation="softmax")(x)
model = tf.keras.Model(inputs, outputs, name="plant_mobilenetv3large")

checkpoint_path = os.path.join(MD, "best_plant_model.keras")
loss = tf.keras.losses.CategoricalCrossentropy(label_smoothing=args.label_smoothing)
metrics = ["accuracy", tf.keras.metrics.TopKCategoricalAccuracy(k=3, name="top3")]

def make_callbacks():
    return [
        tf.keras.callbacks.ModelCheckpoint(
            checkpoint_path, monitor="val_accuracy", mode="max",
            save_best_only=True, verbose=1
        ),
        tf.keras.callbacks.EarlyStopping(
            monitor="val_accuracy", mode="max", patience=args.patience,
            restore_best_weights=True, verbose=1
        ),
        tf.keras.callbacks.TerminateOnNaN(),
        tf.keras.callbacks.CSVLogger(os.path.join(RD, "training_log.csv"), append=True),
    ]

if os.path.exists(os.path.join(RD, "training_log.csv")):
    os.remove(os.path.join(RD, "training_log.csv"))
t_start = time.time()

# 4. Giai đoạn 1: train phần classifier
model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3), loss=loss, metrics=metrics)
print("\n========== GIAI ĐOẠN 1: TRAIN CLASSIFIER ==========")
history1 = model.fit(train, validation_data=val, epochs=args.epochs, callbacks=make_callbacks(), verbose=2)

# 5. Giai đoạn 2: tinh chỉnh backbone, LR khởi động 1 epoch rồi giảm theo cosine
print("\n========== GIAI ĐOẠN 2: FINE-TUNING ==========")
base_model.trainable = True
if args.unfreeze > 0:
    for layer in base_model.layers[:-args.unfreeze]:
        layer.trainable = False
for layer in base_model.layers:
    if isinstance(layer, tf.keras.layers.BatchNormalization):
        layer.trainable = False
steps = int(np.ceil(len(train_p) / args.batch))
schedule = tf.keras.optimizers.schedules.CosineDecay(
    initial_learning_rate=args.fine_tune_lr / 10, decay_steps=max(1, steps * (args.fine_tune_epochs - 1)),
    alpha=0.01, warmup_target=args.fine_tune_lr, warmup_steps=steps,
)
model.compile(optimizer=tf.keras.optimizers.AdamW(learning_rate=schedule, weight_decay=1e-5), loss=loss, metrics=metrics)
print(f"Số lớp được tinh chỉnh: {sum(l.trainable for l in base_model.layers)}/{len(base_model.layers)}; "
      f"tham số học được: {sum(int(np.prod(w.shape)) for w in model.trainable_weights):,}")
history2 = model.fit(train, validation_data=val, epochs=args.epochs + args.fine_tune_epochs, initial_epoch=len(history1.history["loss"]),
                     callbacks=make_callbacks(), verbose=2)
train_minutes = (time.time() - t_start) / 60

# Tải mô hình có val_accuracy tốt nhất
if os.path.exists(checkpoint_path):
    model = tf.keras.models.load_model(checkpoint_path)

# 6. Lưu lịch sử train và biểu đồ
history = {}
for key in set(history1.history) | set(history2.history):
    history[key] = history1.history.get(key, []) + history2.history.get(key, [])
keys = sorted(history)
write_csv(os.path.join(RD, "training_history.csv"), [{k: history[k][i] for k in keys if i < len(history[k])}
                                                     for i in range(max(len(v) for v in history.values()))], keys)

for key, title, filename in [
    ("accuracy", "Training and Validation Accuracy", "training_accuracy.png"),
    ("loss", "Training and Validation Loss", "training_loss.png"),
]:
    val_key = "val_" + key
    if key in history and val_key in history:
        plt.figure(figsize=(9, 5))
        plt.plot(history[key], label="Train " + key)
        plt.plot(history[val_key], label="Validation " + key)
        plt.axvline(len(history1.history["loss"]) - 0.5, color="gray", linestyle="--", linewidth=1, label="Bắt đầu fine-tuning")
        plt.title(title)
        plt.xlabel("Epoch")
        plt.ylabel(key)
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(RD, filename), dpi=160)
        plt.close()

# 7. Đánh giá: train/val (không augmentation) để xem chênh lệch, test là số liệu chính
print("\n" + "=" * 60)
print("ĐÁNH GIÁ MOBILENETV3LARGE")
print("=" * 60)
subset_acc = {}
for name, ds, y in [("train", make_ds(train_p, train_y), train_y), ("val", val, val_y)]:
    subset_acc[name] = float(accuracy_score(y, np.argmax(model.predict(ds, verbose=0), axis=1)))
    print(f"{name:5s}: accuracy {subset_acc[name]:.4f}")
test_loss = model.evaluate(test, verbose=0)[0]
y_true = test_y
y_prob = model.predict(test, verbose=0)
y_pred = np.argmax(y_prob, axis=1)
subset_acc["test"] = float(accuracy_score(y_true, y_pred))
print(f"test : accuracy {subset_acc['test']:.4f}")

metrics_out = {
    "Test Loss": test_loss,
    "Accuracy": accuracy_score(y_true, y_pred),
    "Top-3 Accuracy": top_k_accuracy_score(y_true, y_prob, k=3, labels=np.arange(num_classes)),
    "Macro Precision": precision_score(y_true, y_pred, average="macro", zero_division=0),
    "Macro Recall": recall_score(y_true, y_pred, average="macro", zero_division=0),
    "Macro F1-score": f1_score(y_true, y_pred, average="macro", zero_division=0),
    "Weighted Precision": precision_score(y_true, y_pred, average="weighted", zero_division=0),
    "Weighted Recall": recall_score(y_true, y_pred, average="weighted", zero_division=0),
    "Weighted F1-score": f1_score(y_true, y_pred, average="weighted", zero_division=0),
}
print("\n--- CHỈ SỐ TỔNG THỂ (TEST) ---")
for name, value in metrics_out.items():
    print(f"{name:20s}: {value:.4f}" + (f" ({value * 100:.2f}%)" if "Accuracy" in name else ""))

write_csv(os.path.join(RD, "overall_metrics.csv"), [{k: float(v) for k, v in metrics_out.items()}])
with open(os.path.join(RD, "train_summary.json"), "w", encoding="utf-8") as f:
    json.dump(dict(script="train.py v2", subsets=subset_acc, epochs=len(history.get("loss", [])), head_epochs=len(history1.history["loss"]),
                   fine_tune_lr=args.fine_tune_lr, unfreeze=args.unfreeze, label_smoothing=args.label_smoothing, batch=args.batch,
                   images=dict(train=len(train_p), val=len(val_p), test=len(test_p)), train_minutes=round(train_minutes, 1),
                   gpu=bool(tf.config.list_physical_devices("GPU")), finished=time.strftime("%Y-%m-%d %H:%M")), f, ensure_ascii=False, indent=2)

report_text = classification_report(
    y_true, y_pred, labels=np.arange(num_classes),
    target_names=class_names, digits=4, zero_division=0
)
print("\n--- CLASSIFICATION REPORT ---\n")
print(report_text)

report_dict = classification_report(
    y_true, y_pred, labels=np.arange(num_classes),
    target_names=class_names, output_dict=True, zero_division=0
)
write_csv(os.path.join(RD, "classification_report.csv"),  # dạng bảng như pandas: cột đầu là tên lớp / accuracy / macro avg / weighted avg
          [{"": k, **(v if isinstance(v, dict) else {"precision": v, "recall": v, "f1-score": v, "support": len(y_true)})} for k, v in report_dict.items()],
          ["", "precision", "recall", "f1-score", "support"])

cm = confusion_matrix(y_true, y_pred, labels=np.arange(num_classes))
fig, ax = plt.subplots(figsize=(20, 20))
ConfusionMatrixDisplay(cm, display_labels=class_names).plot(
    ax=ax, xticks_rotation="vertical", colorbar=False, values_format="d"
)
plt.title("Confusion Matrix - MobileNetV3Large")
plt.tight_layout()
plt.savefig(os.path.join(RD, "confusion_matrix.png"), dpi=150, bbox_inches="tight")
plt.close()

xs = np.arange(num_classes)
fig, ax = plt.subplots(figsize=(20, 7))
for i, (k, lbl) in enumerate([("precision", "Precision"), ("recall", "Recall"), ("f1-score", "F1-score")]):
    ax.bar(xs + (i - 1) * 0.27, [report_dict[c][k] for c in class_names], width=0.27, label=lbl)
ax.set_xticks(xs, class_names, rotation=90)
ax.set_ylim(0, 1.05)
ax.set_ylabel("Score")
ax.set_xlabel("Class")
ax.legend(loc="lower right")
plt.title("Precision, Recall and F1-score by Class")
plt.tight_layout()
plt.savefig(os.path.join(RD, "class_metrics.png"), dpi=150, bbox_inches="tight")
plt.close()

# 8. Lưu mô hình cho app (không kèm trạng thái optimizer cho nhẹ; class_names.json đã lưu ở bước 1)
model.save(os.path.join(MD, "plant_model.keras"), include_optimizer=False)

print(f"\nThời gian huấn luyện: {train_minutes:.1f} phút. Đã lưu:")
for item in ["plant_model.keras", "best_plant_model.keras", "class_names.json"]:
    print("- " + os.path.join(MD, item))
for item in ["overall_metrics.csv", "classification_report.csv", "confusion_matrix.png", "class_metrics.png",
             "training_history.csv", "training_accuracy.png", "training_loss.png", "split.csv", "train_summary.json"]:
    print("- " + os.path.join(RD, item))
