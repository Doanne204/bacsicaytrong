"""Tạo chứng chỉ HTTPS tự ký cho mạng LAN (để điện thoại dùng được camera trực tiếp trong trang).
Trình duyệt chỉ cho trang web mở camera khi chạy HTTPS (hoặc localhost), nên truy cập qua http://<IP> thì nút Chụp ảnh
chỉ mở ứng dụng camera của điện thoại. Chạy lại script này khi IP máy tính đổi.
Chạy: python make_cert.py [IP thêm ...]  ->  certs/lan.crt, certs/lan.key"""
import datetime, ipaddress, os, socket, sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

def local_ips():
    ips = {"127.0.0.1"}
    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        ips.add(info[4][0])
    try:  # IP của card mạng đang ra Internet (không gửi gói tin nào)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(ips | set(sys.argv[1:]))

def main():
    ips = local_ips()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Bac si cay trong (LAN)")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "lan.key"), "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    with open(os.path.join(out, "lan.crt"), "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print("Da tao certs/lan.crt cho:", ", ".join(["localhost"] + ips))

if __name__ == "__main__":
    main()
