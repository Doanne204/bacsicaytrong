"""Tạo chứng chỉ HTTPS tự ký cho mạng LAN (để điện thoại dùng được camera trực tiếp trong trang, và đăng nhập Google).
Trình duyệt chỉ cho trang web mở camera khi chạy HTTPS (hoặc localhost), nên truy cập qua http://<IP> thì nút Chụp ảnh
chỉ mở ứng dụng camera của điện thoại. Chạy lại script này khi IP máy tính đổi.
Đăng nhập Google không nhận địa chỉ IP (kể cả HTTPS), nên chứng chỉ còn kèm tên nip.io của từng IP LAN: 192-168-1-72.nip.io luôn
trỏ về 192.168.1.72 (dịch vụ DNS công khai, miễn phí). Thêm https://<tên>.nip.io:5443 vào "Nguồn gốc JavaScript được cho phép".
Chạy: python make_cert.py [IP hoặc tên miền thêm ...]  ->  certs/lan.crt, certs/lan.key"""
import datetime, ipaddress, os, socket, sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

def is_ip(s):
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False

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
    return sorted(ips | {a for a in sys.argv[1:] if is_ip(a)})

def nip_names(ips):
    """Tên nip.io cho các IP mạng nội bộ (192.168.x.x, 10.x.x.x...) để dùng làm địa chỉ đăng nhập Google."""
    return [ip.replace(".", "-") + ".nip.io" for ip in ips if ipaddress.ip_address(ip).is_private and not ipaddress.ip_address(ip).is_loopback]

def main():
    ips = local_ips()
    names = ["localhost"] + nip_names(ips) + [a for a in sys.argv[1:] if not is_ip(a)]
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Bac si cay trong (LAN)")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "lan.key"), "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    with open(os.path.join(out, "lan.crt"), "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print("Da tao certs/lan.crt cho:", ", ".join(names + ips))
    for n in nip_names(ips):
        print(f"Dien thoai mo: https://{n}:5443  (them dia chi nay vao Google Cloud > Nguon goc JavaScript duoc cho phep)")

if __name__ == "__main__":
    main()
