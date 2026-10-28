"""Mẫu email của app (HTML + bản chữ thường cho trình đọc mail không hiện HTML). Viết bằng bảng và style nội dòng vì Gmail, Outlook
bỏ thẻ <style> và nhiều thuộc tính CSS. Logo đính kèm dạng ảnh nội tuyến (cid) nên hiện được cả khi app chạy trong mạng nội bộ."""
import os
from html import escape

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared", "img", "logo-96.png")
LOGO_CID = "logo-bacsicaytrong"
GREEN, GREEN_DARK, PADDY, INK, MUTED, SOFT = "#2b6a36", "#1d4a26", "#d9a21b", "#1f2a1f", "#5f6b5f", "#eef5e9"
FONT = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def app_url():
    """Địa chỉ mở app trong email: APP_URL trong .env, nếu không thì địa chỉ của yêu cầu hiện tại (khi gửi mã lúc đăng ký)."""
    url = os.getenv("APP_URL")
    if not url:
        try:
            from flask import request
            url = request.host_url
        except RuntimeError:  # ngoài yêu cầu web (lệnh flask remind chạy theo lịch)
            return None
    return url.rstrip("/")


def logo():
    """(bytes PNG, cid) của logo hoặc None nếu thiếu file."""
    try:
        with open(LOGO_PATH, "rb") as f:
            return f.read(), LOGO_CID
    except OSError:
        return None


def render(title, intro, code=None, items=None, button=None, note=None, footer=None):
    """Email theo khuôn chung -> (văn bản thuần, HTML).
    code: mã xác thực hiện to; items: [(tiêu đề, mô tả)] hiện thành danh sách; button: (chữ, đường dẫn trong app);
    note: dòng nhắc nhỏ dưới nội dung; footer: lý do người nhận nhận được email."""
    base = app_url()
    link = f"{base}{button[1]}" if button and base else None
    footer = footer or "Bạn nhận email này vì tài khoản Bác sĩ cây trồng dùng địa chỉ email này."
    # ---- văn bản thuần ----
    text = [title, "", intro]
    if code:
        text += ["", f"Mã của bạn: {code}"]
    for head, desc in items or []:
        text.append(f"- {head}" + (f": {desc}" if desc else ""))
    if note:
        text += ["", note]
    if link:
        text += ["", f"{button[0]}: {link}"]
    text += ["", "--", "Bác sĩ cây trồng", footer]
    # ---- HTML ----
    e = escape
    parts = [f'<p style="margin:0 0 20px;font-size:15px;line-height:1.6;color:{INK}">{e(intro)}</p>']
    if code:
        digits = "".join(f'<span style="display:inline-block;margin:0 3px">{e(c)}</span>' for c in str(code))
        parts.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px"><tr><td align="center" '
            f'style="background:{SOFT};border:1px dashed {GREEN};border-radius:14px;padding:22px 12px">'
            f'<div style="font-size:13px;color:{MUTED};margin-bottom:8px">Mã xác thực của bạn</div>'
            f'<div style="font-family:Consolas,\'Courier New\',monospace;font-size:34px;font-weight:700;letter-spacing:4px;color:{GREEN_DARK}">{digits}</div>'
            f'</td></tr></table>')
    if items:
        rows = "".join(
            f'<tr><td valign="top" style="padding:12px 0;border-top:1px solid #e3eadf;width:22px">'
            f'<div style="width:10px;height:10px;border-radius:5px;background:{PADDY};margin-top:6px"></div></td>'
            f'<td style="padding:12px 0;border-top:1px solid #e3eadf;font-size:15px;line-height:1.5;color:{INK}"><b>{e(h)}</b>'
            + (f'<div style="font-size:13px;color:{MUTED};margin-top:2px">{e(d)}</div>' if d else "") + "</td></tr>"
            for h, d in items)
        parts.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px;border-bottom:1px solid #e3eadf">{rows}</table>')
    if note:
        parts.append(f'<p style="margin:0 0 20px;font-size:13px;line-height:1.6;color:{MUTED}">{e(note)}</p>')
    if link:
        parts.append(
            f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:4px 0 8px"><tr><td style="border-radius:12px;background:{GREEN}">'
            f'<a href="{e(link)}" style="display:inline-block;padding:12px 22px;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none">{e(button[0])}</a>'
            f'</td></tr></table>')
    has_logo = os.path.exists(LOGO_PATH)
    brand = (f'<img src="cid:{LOGO_CID}" width="36" height="36" alt="" style="display:block;border:0;border-radius:10px;background:#ffffff">'
             if has_logo else "")
    html = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title></head>
<body style="margin:0;padding:0;background:#f2f5ef;font-family:{FONT}">
<div style="display:none;max-height:0;overflow:hidden">{e(intro[:110])}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f2f5ef"><tr><td align="center" style="padding:28px 12px">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:18px;overflow:hidden;border:1px solid #dfe7da">
  <tr><td style="background:{GREEN_DARK};background-image:linear-gradient(135deg,{GREEN},{GREEN_DARK});padding:20px 28px">
   <table role="presentation" cellpadding="0" cellspacing="0"><tr>
    <td style="padding-right:12px">{brand}</td>
    <td style="font-size:17px;font-weight:700;color:#ffffff">Bác sĩ cây trồng</td>
   </tr></table>
  </td></tr>
  <tr><td style="height:4px;background:{PADDY};font-size:0;line-height:0">&nbsp;</td></tr>
  <tr><td style="padding:28px 28px 8px">
   <h1 style="margin:0 0 12px;font-size:21px;line-height:1.35;color:{INK}">{e(title)}</h1>
   {''.join(parts)}
  </td></tr>
  <tr><td style="padding:16px 28px 24px;font-size:12px;line-height:1.6;color:{MUTED};border-top:1px solid #edf1ea">
   {e(footer)}<br>Kết quả và lời khuyên của ứng dụng chỉ mang tính tham khảo; bệnh nặng hãy hỏi cán bộ khuyến nông.
  </td></tr>
 </table>
</td></tr></table>
</body></html>"""
    return "\n".join(text), html


def code_mail(purpose, code):
    """(tiêu đề, văn bản, HTML) cho mã xác thực đăng ký (verify) hoặc đặt lại mật khẩu (reset)."""
    if purpose == "verify":
        subject, title = "Mã xác thực Bác sĩ cây trồng", "Xác thực email của bạn"
        intro = "Cảm ơn bạn đã đăng ký Bác sĩ cây trồng. Nhập mã dưới đây vào ứng dụng để hoàn tất đăng ký."
    else:
        subject, title = "Mã đặt lại mật khẩu Bác sĩ cây trồng", "Đặt lại mật khẩu"
        intro = "Có người vừa yêu cầu đặt lại mật khẩu cho tài khoản dùng email này. Nhập mã dưới đây để đặt mật khẩu mới."
    text, html = render(title, intro, code=code,
                        note="Mã có hiệu lực 15 phút và chỉ dùng được một lần. Không chia sẻ mã này cho ai. "
                             "Nếu bạn không yêu cầu, hãy bỏ qua email này, tài khoản của bạn vẫn an toàn.")
    return subject, text, html


def reminders_mail(items):
    """items: [(việc, tên nhật ký)] -> (tiêu đề, văn bản, HTML)."""
    text, html = render("Việc chăm sóc cây đến hạn hôm nay",
                        f"Bạn có {len(items)} việc chăm sóc cây đã đến hạn. Làm xong thì đánh dấu trong Nhật ký để ứng dụng ghi lại.",
                        items=items, button=("Mở nhật ký chăm sóc", "/journal"),
                        footer="Bạn nhận email này vì đã đặt lịch nhắc trong Nhật ký điều trị.")
    return "Bác sĩ cây trồng: việc cần làm hôm nay", text, html


def weather_mail(alerts, place=None):
    """alerts: [(tên cảnh báo, lời khuyên)] -> (tiêu đề, văn bản, HTML)."""
    where = f" tại {place}" if place else ""
    text, html = render("Cảnh báo sâu bệnh theo thời tiết",
                        f"Thời tiết 5 ngày tới{where} thuận lợi cho các loại sâu bệnh dưới đây. Kiểm tra vườn sớm và phòng trừ kịp thời.",
                        items=alerts, button=("Xem dự báo và cảnh báo", "/weather"),
                        footer="Bạn nhận email này vì đã lưu vị trí vườn để nhận cảnh báo thời tiết.")
    return "Bác sĩ cây trồng: cảnh báo sâu bệnh theo thời tiết", text, html
