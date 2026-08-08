"""Aggregate analyzed subscription emails into a daily/weekly digest and email it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import Brief, DigestRun, SourceDoc, utcnow
from ..schemas import DigestResult
from ..utils import dumps, loads, new_id
from . import llm as llm_svc
from . import mail_send
from . import notebook as notebook_svc
from . import workspace as workspace_svc
from .email_pipeline import _resolve_inbound_notebook


def run_digest(
    db: Session,
    *,
    period: str = "daily",
    notebook_id: str | None = None,
    send: bool = True,
    dry_run: bool = False,
) -> DigestResult:
    settings = get_settings()
    period = (period or "daily").lower().strip()
    if period not in {"daily", "weekly"}:
        raise ValueError("period must be daily or weekly")

    if notebook_id:
        nb = notebook_svc.get_notebook(db, notebook_id)
        if not nb:
            raise ValueError(f"Notebook not found: {notebook_id}")
    else:
        nb = _resolve_inbound_notebook(db, vault_path=settings.default_vault_path or None)

    end = utcnow()
    start = end - (timedelta(days=1) if period == "daily" else timedelta(days=7))

    emails = (
        db.query(SourceDoc)
        .filter(
            SourceDoc.notebook_id == nb.id,
            SourceDoc.connector == "email",
            SourceDoc.created_at >= start,
            SourceDoc.created_at <= end,
            SourceDoc.status.in_(("ready", "analyzed", "partial")),
        )
        .order_by(SourceDoc.created_at.asc())
        .all()
    )

    digest_id = new_id("dig")
    source_ids = [e.id for e in emails]
    label = "每日" if period == "daily" else "每周"
    lang = settings.digest_language or "zh"

    if not emails:
        subject = f"订阅{label}快报（无新内容）"
        content = (
            f"# 订阅{label}快报\n\n"
            f"时间范围：{_fmt(start)} — {_fmt(end)}（UTC）\n\n"
            "本周期内没有新的订阅邮件。\n"
            if lang.startswith("zh")
            else f"# Subscription {period} digest\n\nNo new emails in this period.\n"
        )
        row = DigestRun(
            id=digest_id,
            notebook_id=nb.id,
            period=period,
            period_start=start,
            period_end=end,
            subject=subject,
            content_md=content,
            source_ids_json=dumps([]),
            status="empty",
        )
        if not dry_run:
            db.add(row)
            db.commit()
            _maybe_write_report(nb, period=period, content_md=content, period_end=end, subject=subject)
        return DigestResult(
            digest_id=digest_id,
            notebook_id=nb.id,
            period=period,
            period_start=start,
            period_end=end,
            subject=subject,
            content_md=content,
            source_count=0,
            source_ids=[],
            status="empty",
        )

    items_blob = _build_items_blob(emails)
    content = _generate_digest_md(
        period=period,
        lang=lang,
        start=start,
        end=end,
        items_blob=items_blob,
        count=len(emails),
    )
    subject = _subject_line(period, lang, len(emails), end)

    status = "draft"
    sent_to = None
    error = None
    if dry_run:
        status = "draft"
    elif send:
        try:
            to_addr = settings.digest_to
            mail_send.send_markdown_email(
                to_addr=to_addr, subject=subject, markdown_body=content
            )
            sent_to = to_addr
            status = "sent"
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            error = str(exc)
    else:
        status = "draft"

    row = DigestRun(
        id=digest_id,
        notebook_id=nb.id,
        period=period,
        period_start=start,
        period_end=end,
        subject=subject,
        content_md=content,
        source_ids_json=dumps(source_ids),
        sent_to=sent_to,
        status=status,
        error=error,
    )
    if not dry_run:
        db.add(row)
        # also store as current brief for the notebook
        db.query(Brief).filter(Brief.notebook_id == nb.id, Brief.is_current == 1).update(
            {"is_current": 0}
        )
        db.add(
            Brief(
                id=new_id("brief"),
                notebook_id=nb.id,
                content_md=content,
                citations_json=dumps(
                    [{"source_id": s, "title": ""} for s in source_ids]
                ),
                is_current=1,
            )
        )
        for e in emails:
            meta = loads(e.metadata_json, {}) or {}
            digests = list(meta.get("digest_ids") or [])
            if digest_id not in digests:
                digests.append(digest_id)
            meta["digest_ids"] = digests
            e.metadata_json = dumps(meta)
        db.commit()
        _maybe_write_report(nb, period=period, content_md=content, period_end=end, subject=subject)

    return DigestResult(
        digest_id=digest_id,
        notebook_id=nb.id,
        period=period,
        period_start=start,
        period_end=end,
        subject=subject,
        content_md=content,
        source_count=len(emails),
        source_ids=source_ids,
        status=status,
        sent_to=sent_to,
        error=error,
    )


def _maybe_write_report(nb, *, period: str, content_md: str, period_end, subject: str) -> None:
    vault = nb.vault_path or get_settings().default_vault_path
    if not vault:
        return
    try:
        workspace_svc.write_report_note(
            vault_path=vault,
            period=period,
            content_md=content_md,
            period_end=period_end,
            subject=subject,
        )
    except Exception:  # noqa: BLE001
        pass


def _build_items_blob(emails: list[SourceDoc]) -> str:
    blocks: list[str] = []
    for i, e in enumerate(emails, start=1):
        meta = loads(e.metadata_json, {}) or {}
        analysis = meta.get("analysis") or {}
        sub_name = meta.get("subscription_name") or ""
        summary = analysis.get("summary") or ""
        points = analysis.get("key_points") or []
        tags = analysis.get("tags") or []
        points_txt = "\n".join(f"  - {p}" for p in points[:8])
        blocks.append(
            f"### [{i}] {e.title}\n"
            f"From: {e.authors or meta.get('from') or ''}\n"
            f"Subscription: {sub_name or '(unlisted)'}\n"
            f"Received: {e.created_at}\n"
            f"Summary: {summary or '(none)'}\n"
            f"Tags: {', '.join(tags) if tags else '-'}\n"
            f"Key points:\n{points_txt or '  -'}\n"
            f"Excerpt: {(e.raw_text or '')[:1200]}\n"
        )
    return "\n".join(blocks)


def _generate_digest_md(
    *,
    period: str,
    lang: str,
    start: datetime,
    end: datetime,
    items_blob: str,
    count: int,
) -> str:
    zh = (lang or "zh").startswith("zh")
    label = "每日" if period == "daily" else "每周"
    system = (
        "你是订阅情报编辑。根据多封已分析的newsletter，写一份简洁的 Markdown 快报。"
        "结构：标题、时段、本周/今日要点（5-10条）、按主题分组摘要、值得跟进的链接或问题。"
        "语气专业克制，不要编造来源中没有的信息。"
        if zh
        else "You are a newsletter digest editor. Write a concise Markdown digest from analyzed emails. "
        "Include: title, period, key takeaways, thematic summaries, follow-ups. Do not invent facts."
    )
    user = (
        f"周期：{label}\n时间：{_fmt(start)} — {_fmt(end)} UTC\n邮件数：{count}\n\n素材：\n{items_blob}"
    )
    try:
        return llm_svc.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
            max_tokens=2500,
        ).strip()
    except Exception:  # noqa: BLE001
        # Fallback without LLM
        if zh:
            return (
                f"# 订阅{label}快报\n\n"
                f"时间范围：{_fmt(start)} — {_fmt(end)}（UTC）\n\n"
                f"共 {count} 封订阅邮件。\n\n"
                f"{items_blob}\n"
            )
        return (
            f"# Subscription {period} digest\n\n"
            f"Period: {_fmt(start)} — {_fmt(end)} UTC\n\n"
            f"{count} emails.\n\n{items_blob}\n"
        )


def _subject_line(period: str, lang: str, count: int, end: datetime) -> str:
    day = end.astimezone(timezone.utc).strftime("%Y-%m-%d")
    if (lang or "zh").startswith("zh"):
        label = "每日" if period == "daily" else "每周"
        return f"【订阅{label}快报】{day} · {count} 封"
    label = "Daily" if period == "daily" else "Weekly"
    return f"[{label} digest] {day} · {count} emails"


def _fmt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
