from __future__ import annotations

import email
import imaplib
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Any

from ..config import get_settings
from .base import BaseConnector, FetchedDoc


class EmailConnector(BaseConnector):
    """Read-only IMAP fetch for newsletter / subscription mail."""

    name = "email"

    def fetch(self, scope: dict[str, Any]) -> list[FetchedDoc]:
        settings = get_settings()
        if not settings.imap_user or not settings.imap_password:
            return []

        email_spec = (scope.get("connectors") or {}).get("email") or {}
        max_results = int(email_spec.get("max_results") or 20)
        days_back = int(email_spec.get("days_back") or 30)
        from_allowlist = [x.lower() for x in (email_spec.get("from_allowlist") or []) if x]
        labels = email_spec.get("labels") or []

        since = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%d-%b-%Y")

        docs: list[FetchedDoc] = []
        try:
            mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
            mail.login(settings.imap_user, settings.imap_password)
            folders = labels if labels else [settings.imap_folder]
            for folder in folders:
                typ, _ = mail.select(folder, readonly=True)
                if typ != "OK":
                    continue
                typ, data = mail.search(None, f"(SINCE {since})")
                if typ != "OK" or not data or not data[0]:
                    continue
                ids = data[0].split()
                ids = list(reversed(ids))[: max_results * 3]
                for msg_id in ids:
                    if len(docs) >= max_results:
                        break
                    typ, msg_data = mail.fetch(msg_id, "(RFC822)")
                    if typ != "OK" or not msg_data or not msg_data[0]:
                        continue
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)
                    sender = _decode(msg.get("From", ""))
                    if from_allowlist and not _match_allowlist(sender, from_allowlist):
                        continue
                    subject = _decode(msg.get("Subject", "")) or "(No subject)"
                    body = _extract_body(msg)
                    date_hdr = msg.get("Date")
                    published = None
                    if date_hdr:
                        try:
                            published = parsedate_to_datetime(date_hdr).date().isoformat()
                        except Exception:  # noqa: BLE001
                            published = date_hdr[:32]
                    doc = FetchedDoc(
                        connector=self.name,
                        title=subject,
                        raw_text=f"{subject}\n\nFrom: {sender}\n\n{body}".strip(),
                        authors=sender,
                        published_at=published,
                        metadata={"folder": folder, "message_id": msg.get("Message-ID")},
                    )
                    if self.passes_filters(doc, scope):
                        docs.append(doc)
            mail.logout()
        except Exception as exc:  # noqa: BLE001
            docs.append(
                FetchedDoc(
                    connector=self.name,
                    title="IMAP fetch failed",
                    raw_text="",
                    status="failed",
                    error=str(exc),
                )
            )
        return docs[:max_results]


def _decode(value: str) -> str:
    parts = decode_header(value)
    out = []
    for data, charset in parts:
        if isinstance(data, bytes):
            out.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(data)
    return "".join(out)


def _match_allowlist(sender: str, patterns: list[str]) -> bool:
    sender_l = sender.lower()
    for pat in patterns:
        pat = pat.lower().strip()
        if pat.startswith("*@"):
            if sender_l.endswith(pat[1:]):
                return True
        elif pat in sender_l:
            return True
    return False


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        texts = []
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            if ctype == "text/plain":
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                texts.append(payload.decode(charset, errors="replace"))
            elif ctype == "text/html" and not texts:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                html = payload.decode(charset, errors="replace")
                texts.append(_strip_html(html))
        return "\n".join(texts).strip()
    payload = msg.get_payload(decode=True) or b""
    charset = msg.get_content_charset() or "utf-8"
    text = payload.decode(charset, errors="replace")
    if msg.get_content_type() == "text/html":
        return _strip_html(text)
    return text.strip()


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
