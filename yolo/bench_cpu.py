"""Đo thời gian nhận diện 1 ảnh trên CPU (như máy chủ app, vốn không có GPU cho TensorFlow): MobileNetV3Large (TensorFlow) hoặc
các mô hình YOLO11-cls đã huấn luyện (PyTorch). Chạy bằng môi trường tương ứng:
    .venv\\Scripts\\python.exe yolo\\bench_cpu.py mobilenet
    .venv-yolo\\Scripts\\python.exe yolo\\bench_cpu.py yolo11n-cls yolo11s-cls yolo11m-cls
Ghi results/yolo/cpu_speed_<tên>.json (ms/ảnh, trung vị của 100 lần, gồm cả đọc và tiền xử lý ảnh)."""
import glob, json, os, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
files = sorted(glob.glob(os.path.join(ROOT, "yolo", "insect204", "test", "*", "*.jpg")))[::300][:100]


def bench(name, fn):
    for f in files[:5]:
        fn(f)  # khởi động
    times = []
    for f in files:
        t = time.perf_counter(); fn(f); times.append((time.perf_counter() - t) * 1000)
    out = dict(model=name, ms_median=statistics.median(times), ms_p90=sorted(times)[int(len(times) * 0.9)], images=len(times))
    os.makedirs(os.path.join(ROOT, "results", "yolo"), exist_ok=True)
    with open(os.path.join(ROOT, "results", "yolo", f"cpu_speed_{name}.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(out)


for name in sys.argv[1:]:
    if name == "mobilenet":
        sys.path.insert(0, ROOT)
        import numpy as np, tensorflow as tf
        from model_service import load_image
        # mô hình MobileNetV3Large cũ: đã thay bằng YOLO11m-cls, bản sao lưu mới nhất nằm trong backups/
        model = tf.keras.models.load_model(sorted(glob.glob(os.path.join(ROOT, "backups", "pest_before_*", "pest_model.keras")))[-1])
        bench(name, lambda f: model(np.expand_dims(np.asarray(load_image(open(f, "rb").read()), dtype="float32"), 0), training=False))
    else:
        import torch
        from ultralytics import YOLO
        torch.set_num_threads(os.cpu_count())
        m = YOLO(os.path.join(ROOT, "yolo", "runs", name, "weights", "best.pt"))
        bench(name, lambda f: m.predict(f, imgsz=224, device="cpu", verbose=False))
