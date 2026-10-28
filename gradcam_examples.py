"""Hình minh họa Grad-CAM cho báo cáo: lấy ảnh trong tập test (results/split.csv do train.py / evaluate_leaf.py ghi ra), cho mô hình
bệnh lá đang dùng dự đoán, vẽ bảng "ảnh gốc | Grad-CAM của lớp dự đoán" cho các ca ĐÚNG (mỗi lớp bệnh khác nhau một ảnh) và các ca SAI
(kèm Grad-CAM của lớp đúng để thấy mô hình nhìn nhầm vào đâu). Ghi results/gradcam_examples.png và results/gradcam_errors.png.

Chạy: python gradcam_examples.py [--correct 8] [--errors 4]
"""
import argparse, csv, io, os, random, sys
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import knowledge
from model_service import ModelService, cam_stats, load_image, overlay_cam

ROOT = os.path.dirname(os.path.abspath(__file__))

def label(raw):
    i = knowledge.info(raw)
    return f"{i['plant']}: {i['disease']}"

def draw(items, title, path, per_row=1):
    """items: [(ảnh gốc bytes, [(tiêu đề ô, ảnh phủ bytes), ...], chú thích)]; per_row mẫu trên mỗi hàng của hình."""
    width = 1 + max(len(r[1]) for r in items)
    n_rows = (len(items) + per_row - 1) // per_row
    fig, axes = plt.subplots(n_rows, width * per_row, figsize=(3.3 * width * per_row, 3.7 * n_rows), squeeze=False)
    for ax in axes.ravel():
        ax.axis("off")
    for k, (orig, cams, caption) in enumerate(items):
        r, c0 = divmod(k, per_row)
        for j, (t, b) in enumerate([("Ảnh gốc\n" + caption, orig)] + cams):
            ax = axes[r, c0 * width + j]
            ax.imshow(Image.open(io.BytesIO(b)).convert("RGB").resize((256, 256)))
            ax.set_title(t, fontsize=8.5)
    fig.suptitle(title, fontsize=13)
    plt.tight_layout(rect=(0, 0, 1, 0.97))
    plt.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()
    print("Đã ghi", path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--correct", type=int, default=8, help="Số ca đúng (mỗi lớp bệnh một ảnh)")
    ap.add_argument("--errors", type=int, default=4, help="Số ca sai")
    ap.add_argument("--split", default=os.path.join(ROOT, "results", "split.csv"))
    ap.add_argument("--out", default=os.path.join(ROOT, "results"))
    ap.add_argument("--max_scan", type=int, default=600, help="Số ảnh test tối đa quét để tìm ca sai")
    args = ap.parse_args()
    m = ModelService()
    if m.demo:
        sys.exit("Chưa nạp được mô hình thật (models/plant_model.keras hoặc best_plant_model.keras)")
    if not os.path.exists(args.split):
        sys.exit(f"Không có {args.split}: chạy train.py hoặc evaluate_leaf.py trước để có cách chia tập test")
    with open(args.split, encoding="utf-8-sig") as f:
        test = [(r["path"], r["class"]) for r in csv.DictReader(f) if r["subset"] == "test" and os.path.exists(r["path"])]
    random.seed(7)
    random.shuffle(test)
    correct, errors, seen = [], [], set()
    diseased = [c for c in m.class_names if not knowledge.info(c)["healthy"] and knowledge.info(c)["plant_id"] in knowledge.PLANTS]
    for path, true in test[:args.max_scan]:
        if len(correct) >= args.correct and len(errors) >= args.errors:
            break
        if true not in diseased and knowledge.info(true)["plant_id"] not in knowledge.PLANTS:
            continue  # bỏ ảnh nền (không có lá): không có gì để giải thích
        data = open(path, "rb").read()
        probs = m._forward(load_image(data))[0]  # dự đoán trên toàn bộ lớp (như lúc đánh giá), không lọc theo cây
        i = int(np.argmax(probs))
        pred = dict(raw=m.class_names[i], prob=float(probs[i]))
        if pred["raw"] == true:
            if len(correct) < args.correct and true in diseased and true not in seen:
                seen.add(true)
                cam = m.gradcam(data, true)
                s = cam_stats(cam)
                correct.append((data, [(f"Grad-CAM: {label(true)}\n{pred['prob']:.0%}, vùng mạnh {s['focus']:.0%} ảnh", overlay_cam(data, cam))], f"Đúng: {label(true)}"))
        elif len(errors) < args.errors and true in m.class_names:
            cp, ct = m.gradcam(data, pred["raw"]), m.gradcam(data, true)
            errors.append((data, [(f"Mô hình đoán: {label(pred['raw'])}\n{pred['prob']:.0%}", overlay_cam(data, cp)),
                                  (f"Lớp đúng: {label(true)}", overlay_cam(data, ct))], f"Thực tế: {label(true)}"))
    if correct:
        draw(correct, "Grad-CAM trên ảnh test: các ca dự đoán đúng (đỏ, vàng = vùng ảnh hưởng nhiều nhất đến dự đoán)",
             os.path.join(args.out, "gradcam_examples.png"), per_row=2)
    if errors:
        draw(errors, "Grad-CAM trên các ca dự đoán sai: mô hình nhìn vào đâu khi đoán nhầm, so với lớp đúng",
             os.path.join(args.out, "gradcam_errors.png"))
    print(f"{len(correct)} ca đúng, {len(errors)} ca sai")

if __name__ == "__main__":
    main()
