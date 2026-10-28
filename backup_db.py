"""Sao lưu CSDL và ảnh tải lên vào backups/<ngày-giờ>/, giữ lại --keep bản mới nhất (mặc định 14).
  python backup_db.py              (PostgreSQL: dùng pg_dump; SQLite: chép file app.db)
Đặt lịch chạy hằng ngày bằng Task Scheduler của Windows (xem README) hoặc cron trên Linux."""
import argparse, os, shutil, subprocess, sys, time
from urllib.parse import urlparse
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

p = argparse.ArgumentParser()
p.add_argument("--out", default=os.path.join(ROOT, "backups"))
p.add_argument("--keep", type=int, default=14)
p.add_argument("--no-uploads", action="store_true", help="Chỉ sao lưu CSDL, bỏ qua ảnh")
a = p.parse_args()

stamp = time.strftime("%Y%m%d-%H%M%S")
dest = os.path.join(a.out, stamp)
os.makedirs(dest, exist_ok=True)
url = os.getenv("DATABASE") or os.getenv("DATABASE_URL") or os.path.join(ROOT, "instance", "app.db")
if url.startswith(("postgresql://", "postgres://")):
    u = urlparse(url)
    pg_dump = os.getenv("PG_DUMP", "pg_dump")
    if shutil.which(pg_dump) is None:  # bản cài PostgreSQL trên Windows không thêm vào PATH
        cands = sorted(p for p in [os.path.join(r"C:\Program Files\PostgreSQL", v, "bin", "pg_dump.exe") for v in ("18", "17", "16", "15")] if os.path.exists(p))
        pg_dump = cands[0] if cands else pg_dump
    out = os.path.join(dest, f"{u.path.lstrip('/')}.dump")
    env = dict(os.environ, PGPASSWORD=u.password or "")
    subprocess.run([pg_dump, "-h", u.hostname or "localhost", "-p", str(u.port or 5432), "-U", u.username or "postgres", "-Fc", "-f", out, u.path.lstrip("/")],
                   check=True, env=env)
    print("Đã sao lưu PostgreSQL ->", out, f"({os.path.getsize(out) // 1024} KB)")
    print("Khôi phục: pg_restore -h localhost -U postgres -d <csdl mới> --clean --if-exists", out)
else:
    import sqlite3
    out = os.path.join(dest, "app.db")
    with sqlite3.connect(url) as src, sqlite3.connect(out) as dst:
        src.backup(dst)  # an toàn khi ứng dụng đang chạy
    print("Đã sao lưu SQLite ->", out)
if not a.no_uploads:
    up = os.getenv("UPLOAD_DIR") or os.path.join(ROOT, "instance", "uploads")
    if os.path.isdir(up):
        shutil.make_archive(os.path.join(dest, "uploads"), "zip", up)
        print("Đã nén ảnh tải lên -> uploads.zip")
old = sorted(d for d in os.listdir(a.out) if os.path.isdir(os.path.join(a.out, d)))[:-a.keep]
for d in old:
    shutil.rmtree(os.path.join(a.out, d), ignore_errors=True)
if old:
    print(f"Đã xóa {len(old)} bản cũ, giữ {a.keep} bản mới nhất")
