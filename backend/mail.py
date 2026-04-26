"""Send transactional email (password reset) via SMTP."""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

log = logging.getLogger("lotlegends.mail")


def smtp_configured() -> bool:
    return bool(os.getenv("LOTLEGENDS_SMTP_HOST", "").strip())


def _strip_brackets(addr: str) -> str:
    a = (addr or "").strip()
    if a.startswith("<") and a.endswith(">"):
        return a[1:-1].strip()
    return a


def send_password_reset_email(
    to_email: str, reset_url: str, *, from_name: str = "The Lot Legends"
) -> bool:
    """Send a password reset link. Returns True if SMTP accepted the message.

    If LOTLEGENDS_SMTP_* is not set, returns False and the caller may log the URL.
    """
    if not smtp_configured():
        return False

    host = (os.getenv("LOTLEGENDS_SMTP_HOST") or "").strip()
    port = int(os.getenv("LOTLEGENDS_SMTP_PORT", "587"))
    user = (os.getenv("LOTLEGENDS_SMTP_USER") or "").strip()
    password = os.getenv("LOTLEGENDS_SMTP_PASSWORD") or ""
    from_raw = (os.getenv("LOTLEGENDS_SMTP_FROM") or user).strip()
    if not from_raw or not user:
        log.warning("LOTLEGENDS_SMTP_HOST set but FROM/USER missing")
        return False

    from_addr = _strip_brackets(from_raw)
    to_addr = (to_email or "").strip().lower()
    if not to_addr or "@" not in to_addr:
        return False

    subject = "รีเซ็ตรหัสผ่าน — The Lot Legends"
    text = (
        f"คลิกลิงก์ด้านล่างเพื่อตั้งรหัสผ่านใหม่ (อายุ 1 ชั่วโมง)\n"
        f"\n{reset_url}\n\n"
        f"หากคุณไม่ได้ขอ ให้เพิกเฉยอีเมลนี้\n"
    )
    html = f"""
    <p>คลิกปุ่มเพื่อตั้งรหัสผ่านใหม่ (อายุ 1 ชั่วโมง)</p>
    <p><a href="{reset_url}" style="color:#C9A661;">{reset_url}</a></p>
    <p style="color:#888;font-size:12px;">หากคุณไม่ได้ขอ ให้เพิกเฉยอีเมลนี้</p>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_addr)) if "@" in from_addr else from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            if port != 25:
                smtp.starttls(context=context)
                smtp.ehlo()
            if password or user:
                smtp.login(user, password)
            smtp.sendmail(from_addr, [to_addr], msg.as_string())
        return True
    except Exception:  # noqa: BLE001
        log.exception("SMTP send failed to %s", to_addr)
        return False
