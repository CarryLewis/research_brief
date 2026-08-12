#!/usr/bin/env python3
"""Non-destructive migrator: legacy vault → Constitution V1.1 cognitive roots.

Maps:
  Library/Articles|Emails|Books/**  → Information/
  Library/Notes/**, Reflections/**  → Thinking/
  Insights/**                       → Research/
  Books/** (Constitution)           → Information/
  Concepts/**, Projects/**          → Thinking/ (default; review Research manually)
  Reports/**                        → Archive/Digests/
  Collections/**                    → Archive/Collections/
  Archive/Legacy|PreConstitution-*  → stay cold

Never deletes without copying into Archive/ConstitutionV1/{stamp}/ first.
Logs every move to Archive/ConstitutionV1/migration-log-{stamp}.md

Usage:
  cd backend && python scripts/migrate_to_constitution_v1_1.py --vault ../vault
  cd backend && python scripts/migrate_to_constitution_v1_1.py --vault ../vault --dry-run
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

COGNITIVE_ROOTS = ("Information", "Thinking", "Research")


def _unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    for i in range(2, 500):
        alt = dest.with_name(f"{stem} ({i}){suffix}")
        if not alt.exists():
            return alt
    raise RuntimeError(f"Too many collisions for {dest}")


def _mirror_and_copy(
    src: Path,
    dest: Path,
    mirror: Path,
    *,
    dry_run: bool,
    log: list[str],
) -> None:
    dest = _unique_dest(dest) if not dry_run else dest
    log.append(f"{src} → {dest}")
    if dry_run:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    mirror.parent.mkdir(parents=True, exist_ok=True)
    if not mirror.exists():
        shutil.copy2(src, mirror)
    if not dest.exists():
        shutil.copy2(src, dest)
    src.unlink(missing_ok=True)


def _copy_md_tree(
    src_dir: Path,
    dest_dir: Path,
    *,
    dry_run: bool,
    log: list[str],
    archive_mirror: Path,
) -> int:
    if not src_dir.is_dir():
        return 0
    moved = 0
    for path in sorted(src_dir.rglob("*.md")):
        if not path.is_file() or path.name.startswith("."):
            continue
        dest = dest_dir / path.name
        mirror = archive_mirror / src_dir.name / path.relative_to(src_dir)
        _mirror_and_copy(path, dest, mirror, dry_run=dry_run, log=log)
        moved += 1
    return moved


def migrate(vault: Path, *, dry_run: bool = False) -> dict[str, int]:
    vault = vault.expanduser().resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_root = vault / "Archive" / "ConstitutionV1" / stamp
    log: list[str] = []
    stats = {
        "information": 0,
        "thinking": 0,
        "research": 0,
        "digests": 0,
        "collections": 0,
        "attachments": 0,
    }

    for name in COGNITIVE_ROOTS:
        (vault / name).mkdir(parents=True, exist_ok=True)
    (vault / "Information" / "Attachments").mkdir(parents=True, exist_ok=True)
    (vault / "Archive" / "Digests").mkdir(parents=True, exist_ok=True)
    if not dry_run:
        archive_root.mkdir(parents=True, exist_ok=True)

    lib = vault / "Library"
    if lib.is_dir():
        for medium in ("Articles", "Emails", "Books"):
            stats["information"] += _copy_md_tree(
                lib / medium,
                vault / "Information",
                dry_run=dry_run,
                log=log,
                archive_mirror=archive_root / "Library",
            )
        attach = lib / "Attachments"
        if attach.is_dir():
            for path in sorted(attach.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(attach)
                dest = vault / "Information" / "Attachments" / rel
                mirror = archive_root / "Library" / "Attachments" / rel
                _mirror_and_copy(path, dest, mirror, dry_run=dry_run, log=log)
                stats["attachments"] += 1
        stats["thinking"] += _copy_md_tree(
            lib / "Notes",
            vault / "Thinking",
            dry_run=dry_run,
            log=log,
            archive_mirror=archive_root / "Library",
        )

    stats["thinking"] += _copy_md_tree(
        vault / "Reflections",
        vault / "Thinking",
        dry_run=dry_run,
        log=log,
        archive_mirror=archive_root,
    )
    stats["thinking"] += _copy_md_tree(
        vault / "Concepts",
        vault / "Thinking",
        dry_run=dry_run,
        log=log,
        archive_mirror=archive_root,
    )
    stats["thinking"] += _copy_md_tree(
        vault / "Projects",
        vault / "Thinking",
        dry_run=dry_run,
        log=log,
        archive_mirror=archive_root,
    )
    stats["information"] += _copy_md_tree(
        vault / "Books",
        vault / "Information",
        dry_run=dry_run,
        log=log,
        archive_mirror=archive_root,
    )
    stats["research"] += _copy_md_tree(
        vault / "Insights",
        vault / "Research",
        dry_run=dry_run,
        log=log,
        archive_mirror=archive_root,
    )
    # Reports may nest Daily/Weekly — preserve relative path under Digests
    reports = vault / "Reports"
    if reports.is_dir():
        for path in sorted(reports.rglob("*.md")):
            if not path.is_file():
                continue
            rel = path.relative_to(reports)
            dest = vault / "Archive" / "Digests" / rel
            mirror = archive_root / "Reports" / rel
            _mirror_and_copy(path, dest, mirror, dry_run=dry_run, log=log)
            stats["digests"] += 1
    stats["collections"] += _copy_md_tree(
        vault / "Collections",
        vault / "Archive" / "Collections",
        dry_run=dry_run,
        log=log,
        archive_mirror=archive_root,
    )

    if not dry_run:
        for name in (
            "Library",
            "Reflections",
            "Concepts",
            "Projects",
            "Books",
            "Insights",
            "Reports",
            "Collections",
        ):
            d = vault / name
            if not d.is_dir():
                continue
            leftovers = [
                p
                for p in d.rglob("*")
                if p.is_file() and p.name not in {".gitkeep", "MOVED.md"}
            ]
            if not leftovers:
                shutil.rmtree(d, ignore_errors=True)
            else:
                (d / "MOVED.md").write_text(
                    "# Moved to Constitution V1.1\n\n"
                    f"Recoverable copy under `Archive/ConstitutionV1/{stamp}/`.\n"
                    "Daily roots: Information / Thinking / Research.\n",
                    encoding="utf-8",
                )

    log_path = vault / "Archive" / "ConstitutionV1" / f"migration-log-{stamp}.md"
    lines = [
        "# Constitution V1.1 migration log",
        "",
        f"- vault: `{vault}`",
        f"- dry_run: `{dry_run}`",
        f"- stamp: `{stamp}`",
        "",
        "## Stats",
        "",
        *[f"- {k}: {v}" for k, v in stats.items()],
        "",
        "## Moves",
        "",
        *([f"- `{m}`" for m in log] if log else ["- (none)"]),
        "",
    ]
    if not dry_run:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        print("\n".join(lines))

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate vault to Constitution V1.1")
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "vault",
        help="Path to Obsidian vault",
    )
    parser.add_argument("--dry-run", action="store_true", help="Log actions without writing")
    args = parser.parse_args()
    stats = migrate(args.vault, dry_run=args.dry_run)
    print("Migration stats:", stats)


if __name__ == "__main__":
    main()
