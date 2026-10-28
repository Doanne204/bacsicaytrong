"""Tạo thư mục dữ liệu phân loại cho YOLO (train/val/test/<loài>/ảnh) từ results/pest_split.csv, tức đúng phép chia 6:1:3 mà
train_pests.py đã dùng, để so sánh công bằng với MobileNetV3Large. Ảnh được ghi thành bản sao mới, thu nhỏ cạnh ngắn về --size px
(YOLO vẫn đưa về 224; ảnh gốc rất lớn làm khâu đọc ảnh chậm hơn GPU nhiều lần). Không bao giờ ghi vào bộ dữ liệu gốc
(Ultralytics ghi đè ảnh JPEG hỏng khi quét). Chạy lại thì bỏ qua file đã có."""
import argparse, csv, os, sys
from concurrent.futures import ProcessPoolExecutor
from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True  # vài ảnh INSECT204 bị cắt cụt cuối file


def convert(job):
    src, dst, size = job
    if os.path.exists(dst):
        return 0
    with Image.open(src) as im:
        im = im.convert("RGB")  # không xoay theo EXIF, giống tf.io.decode_image của train_pests.py (vài ảnh có EXIF hỏng)
        s = size / min(im.size)
        if s < 1:
            im = im.resize((round(im.width * s), round(im.height * s)), Image.BICUBIC)
        im.save(dst, "JPEG", quality=95)
    return 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="dataset/INSECT204-A Novel Large-Scale Benchmark Dataset fo/INSECT204")
    p.add_argument("--split", default="results/pest_split.csv")
    p.add_argument("--out", default="yolo/insect204")
    p.add_argument("--size", type=int, default=256)
    a = p.parse_args()
    jobs, counts = [], {}
    with open(a.split, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dst_dir = os.path.join(a.out, r["split"], r["class"])
            os.makedirs(dst_dir, exist_ok=True)
            n = counts[r["split"]] = counts.get(r["split"], 0) + 1
            # tên file có thể trùng giữa các thư mục con của cùng một loài -> thêm số thứ tự
            jobs.append((os.path.join(a.data, r["file"]), os.path.join(dst_dir, f"{n:06d}_{os.path.splitext(os.path.basename(r['file']))[0]}.jpg"), a.size))
    with ProcessPoolExecutor() as ex:
        done = sum(ex.map(convert, jobs, chunksize=256))
    print(counts, f"ghi mới {done} ảnh", file=sys.stderr)


if __name__ == "__main__":
    main()
