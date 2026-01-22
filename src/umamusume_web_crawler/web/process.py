from __future__ import annotations

import logging
from pathlib import Path


def _coerce_path(path: str | Path) -> Path:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    return file_path


def _suppress_pdfminer_warnings() -> None:
    for name in ("pdfminer", "pdfminer.pdfinterp", "pdfminer.pdffont"):
        logging.getLogger(name).setLevel(logging.ERROR)


def convert_markitdown(path: str | Path) -> str:
    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise ImportError(
            "markitdown is not installed. Try: pip install 'markitdown[all]'"
        ) from exc

    file_path = _coerce_path(path)
    if file_path.suffix.lower() == ".pdf":
        _suppress_pdfminer_warnings()

    md = MarkItDown(enable_plugins=False)
    result = md.convert(str(file_path))
    return result.text_content or ""
