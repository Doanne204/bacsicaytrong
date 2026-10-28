"""Chạy thật bằng Waitress (máy chủ WSGI đa luồng, thay cho flask run chỉ dành cho phát triển).
  python serve.py                      -> http://0.0.0.0:5000
  python serve.py --port 5443 --cert certs/lan.crt --key certs/lan.key   -> HTTPS cho điện thoại trong mạng LAN
Waitress không tự làm HTTPS, nên với --cert dùng bộ bọc TLS đơn giản (đủ cho LAN); triển khai Internet nên đặt sau Nginx/Caddy với tên miền thật."""
import argparse, os, ssl, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

p = argparse.ArgumentParser()
p.add_argument("--host", default="0.0.0.0")
p.add_argument("--port", type=int, default=5000)
p.add_argument("--threads", type=int, default=8)
p.add_argument("--cert"); p.add_argument("--key")
a = p.parse_args()

from app import create_app
app = create_app()

if a.cert:  # HTTPS: Waitress nhận kết nối thường từ một socket đã bọc TLS
    import socket
    from waitress.server import create_server
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(a.cert, a.key)
    raw = socket.create_server((a.host, a.port), reuse_port=False, backlog=128)
    srv = create_server(app, sockets=[ctx.wrap_socket(raw, server_side=True)], threads=a.threads)
    print(f"HTTPS: https://{a.host}:{a.port} ({a.threads} luồng)", flush=True)
    srv.run()
else:
    from waitress import serve
    print(f"HTTP: http://{a.host}:{a.port} ({a.threads} luồng)", flush=True)
    serve(app, host=a.host, port=a.port, threads=a.threads)
