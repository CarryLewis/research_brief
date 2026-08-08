"""Send digest email via SMTP (stdlib)."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import get_settings


class MailSendError(RuntimeError):
    pass


def send_markdown_email(*, to_addr: str, subject: str, markdown_body: str) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        raise MailSendError("SMTP_HOST is not configured")
    from_addr = (settings.digest_from or settings.smtp_user or "").strip()
    if not from_addr:
        raise MailSendError("DIGEST_FROM or SMTP_USER is required")
    to_addr = (to_addr or settings.digest_to or "").strip()
    if not to_addr:
        raise MailSendError("DIGEST_TO is not configured")

    plain = markdown_body
    html = _md_to_simple_html(markdown_body)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    if settings.smtp_use_tls:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=60) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=60) as server:
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(from_addr, [to_addr], msg.as_string())


def _md_to_simple_html(md: str) -> str:
    """Minimal markdown→HTML for digest email (headings, lists, paragraphs)."""
    import html as html_lib
    import re

    lines = (md or "").splitlines()
    out: list[str] = []
    in_ul = False
    for line in lines:
        if line.startswith("### "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h3>{html_lib.escape(line[4:].strip())}</h3>")
        elif line.startswith("## "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h2>{html_lib.escape(line[3:].strip())}</h2>")
        elif line.startswith("# "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h1>{html_lib.escape(line[2:].strip())}</h1>")
        elif re.match(r"^[-*]\s+", line):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            item = re.sub(r"^[-*]\s+", "", line)
            out.append(f"<li>{html_lib.escape(item)}</li>")
        elif not line.strip():
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append("<br/>")
        else:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            # light bold
            esc = html_lib.escape(line)
            esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
            out.append(f"<p>{esc}</p>")
    if in_ul:
        out.append("</ul>")
    body = "\n".join(out)
    return (
        "<!DOCTYPE html><html><body style=\"font-family:system-ui,sans-serif;"
        f"line-height:1.5;max-width:720px\">{body}</body></html>"
    )
