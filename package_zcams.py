"""Package the cfa-dash app into zcamsNew.zip for distribution.

Excludes virtualenvs, caches, the local SQLite DB, uploaded artifacts, and any
secrets so the zip is safe to share.
"""
from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "cfa-dash"
OUT = ROOT / "zcamsNew.zip"

# Directory names (any depth) to skip entirely.
EXCLUDE_DIRS = {
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    "node_modules",
    "uploads",          # user-uploaded BLs (runtime data)
    "generated_pdfs",   # signed invoice PDFs (runtime artifacts)
}

# Files (basename match) to skip.
EXCLUDE_FILES = {
    ".DS_Store",
    "Thumbs.db",
    "zcams.db",
    "zcams.db-shm",
    "zcams.db-wal",
    "invoice_flow.log",
}

# File suffixes to skip.
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log"}


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDE_DIRS:
        return True
    if path.name in EXCLUDE_FILES:
        return True
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    return False


def main() -> int:
    if not SOURCE.is_dir():
        print(f"ERROR: source directory not found: {SOURCE}", file=sys.stderr)
        return 2

    file_count = 0
    total_bytes = 0
    skipped = 0

    if OUT.exists():
        OUT.unlink()

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for current, dirs, files in os.walk(SOURCE):
            current_path = Path(current)
            # Prune excluded directories in-place so os.walk does not descend.
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            rel_dir = current_path.relative_to(SOURCE)
            for filename in files:
                src_path = current_path / filename
                rel_path = rel_dir / filename
                if should_skip(rel_path) or should_skip(src_path.relative_to(SOURCE.parent)):
                    skipped += 1
                    continue
                arcname = Path("zcamsNew") / rel_path
                zf.write(src_path, arcname.as_posix())
                file_count += 1
                total_bytes += src_path.stat().st_size

    out_size = OUT.stat().st_size
    print(f"Packaged: {OUT}")
    print(f"  files included : {file_count}")
    print(f"  files skipped  : {skipped}")
    print(f"  source bytes   : {total_bytes:,}")
    print(f"  archive bytes  : {out_size:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
