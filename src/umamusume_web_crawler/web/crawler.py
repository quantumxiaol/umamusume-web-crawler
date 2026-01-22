from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig, ProxyConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from umamusume_web_crawler.config import config


class SingleProxyRotationStrategy:
    def __init__(self, proxy_config: ProxyConfig) -> None:
        self.proxy_config = proxy_config

    async def get_next_proxy(self) -> ProxyConfig:
        return self.proxy_config


class UmamusumeCrawler:
    def __init__(self, workspace: str | Path | None = None, keep_files: bool = False):
        """
        :param workspace: 指定工作目录。如果为 None，使用系统临时目录。
        :param keep_files: 是否保留文件。如果使用临时目录，该选项通常为 False。
        """
        self.keep_files = keep_files
        self._temp_dir: tempfile.TemporaryDirectory | None = None

        if workspace:
            self.work_dir = Path(workspace)
            self.work_dir.mkdir(parents=True, exist_ok=True)
            self.is_temp = False
        else:
            if keep_files:
                self.work_dir = Path(tempfile.mkdtemp(prefix="umamusume_crawl_"))
                self.is_temp = True
            else:
                self._temp_dir = tempfile.TemporaryDirectory(prefix="umamusume_crawl_")
                self.work_dir = Path(self._temp_dir.name)
                self.is_temp = True

    def _get_file_path(self, url: str, ext: str) -> Path:
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        ext = ext.lstrip(".")
        return self.work_dir / f"{url_hash}.{ext}"

    def cleanup(self) -> None:
        if not self.is_temp or self.keep_files:
            return
        if self._temp_dir is not None:
            self._temp_dir.cleanup()
        else:
            shutil.rmtree(self.work_dir, ignore_errors=True)

    def __enter__(self) -> "UmamusumeCrawler":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()


_MD_OPTIONS = {
    "ignore_links": True,
    "ignore_images": True,
    "escape_html": False,
    "body_width": 80,
}

_md_generator = DefaultMarkdownGenerator(options=_MD_OPTIONS)

_REAL_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

_STEALTH_JS = (
    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
)

_BILIGAME_JSON_MARKERS = (
    '"relation_type"',
    '"member_id"',
    '"日文名"',
    '"头像"',
    '"中文名"',
)

_BILIGAME_MAIN_SELECTOR = "#mw-content-text > .mw-parser-output"
_MOEGIRL_MAIN_SELECTOR = ".mw-parser-output"

_CAPTURE_PNG_ATTRS = ("screenshot_path", "screenshot", "screenshot_base64", "screenshot_data")
_CAPTURE_PDF_ATTRS = ("pdf_path", "pdf", "pdf_base64", "pdf_data")


def _resolve_output_dir(
    output_dir: Path | None,
    *,
    workspace: UmamusumeCrawler | str | Path | None,
    keep_files: bool,
    require_output_dir: bool,
) -> tuple[Path, UmamusumeCrawler | None]:
    if output_dir is not None:
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path, None
    if isinstance(workspace, UmamusumeCrawler):
        workspace.work_dir.mkdir(parents=True, exist_ok=True)
        return workspace.work_dir, None
    if workspace is None and require_output_dir:
        raise ValueError("output_dir or workspace is required to retain capture files.")
    crawler = UmamusumeCrawler(workspace=workspace, keep_files=keep_files)
    crawler.work_dir.mkdir(parents=True, exist_ok=True)
    return crawler.work_dir, crawler


async def _await_with_timeout(coro, timeout_s: float | None) -> object:
    if timeout_s is None or timeout_s <= 0:
        return await coro
    return await asyncio.wait_for(coro, timeout=timeout_s)


def _resolve_timeout(timeout_s: float | None) -> float | None:
    return config.crawler_timeout_s if timeout_s is None else timeout_s


async def _run_with_timeout(coro, timeout_s: float | None) -> object:
    return await _await_with_timeout(coro, _resolve_timeout(timeout_s))


def _resolve_user_data_dir() -> str | None:
    user_data_dir = config.crawler_user_data_dir
    if not user_data_dir:
        return None
    path = Path(user_data_dir).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _strip_json_blocks(text: str, markers: tuple[str, ...]) -> str:
    lines = text.splitlines()
    cleaned: list[str] = []
    skipping = False
    depth = 0
    for line in lines:
        if skipping:
            depth += line.count("[") - line.count("]")
            if depth <= 0:
                skipping = False
            continue
        if any(marker in line for marker in markers):
            depth = line.count("[") - line.count("]")
            if depth > 0:
                skipping = True
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _post_process_content(url: str, content: str) -> str:
    if "wiki.biligame.com/umamusume" in url:
        return _strip_json_blocks(content, _BILIGAME_JSON_MARKERS)
    return content


def _build_pruning_markdown_generator(
    *, threshold: float | None = None, min_word_threshold: int | None = None
) -> DefaultMarkdownGenerator:
    threshold = config.crawler_pruned_threshold if threshold is None else threshold
    min_word_threshold = (
        config.crawler_pruned_min_words
        if min_word_threshold is None
        else min_word_threshold
    )
    return DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(
            threshold=threshold, min_word_threshold=min_word_threshold
        ),
        options=_MD_OPTIONS,
    )


def _sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned or "page"


def _slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    domain = _sanitize_filename(parsed.netloc or "")
    title = None
    if parsed.path.endswith("/index.php"):
        params = parse_qs(parsed.query)
        title = params.get("title", [None])[0]
    if not title:
        title = unquote(parsed.path.strip("/").split("/")[-1])
    title_slug = _sanitize_filename(title or parsed.netloc or "page")
    if domain:
        return f"{domain}_{title_slug}"
    return title_slug


def _apply_optional_config(config_obj: object, values: dict[str, object]) -> None:
    for key, value in values.items():
        if hasattr(config_obj, key):
            try:
                setattr(config_obj, key, value)
            except Exception:
                continue


def _extract_capture_bytes(value: object) -> bytes | None:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        if value.startswith("data:") and "," in value:
            value = value.split(",", 1)[1]
        try:
            return base64.b64decode(value, validate=True)
        except Exception:
            try:
                return base64.b64decode(value)
            except Exception:
                return None
    if isinstance(value, dict):
        for key in ("data", "base64"):
            nested = value.get(key)
            if isinstance(nested, bytes):
                return nested
            if isinstance(nested, str):
                if nested.startswith("data:") and "," in nested:
                    nested = nested.split(",", 1)[1]
                try:
                    return base64.b64decode(nested, validate=True)
                except Exception:
                    try:
                        return base64.b64decode(nested)
                    except Exception:
                        continue
    return None


def _save_capture_result(
    result: object,
    *,
    output_path: Path,
    candidates: tuple[str, ...],
) -> Path | None:
    for attr in candidates:
        value = getattr(result, attr, None)
        if not value:
            continue
        if isinstance(value, (str, Path)):
            if isinstance(value, str) and (value.startswith("data:") or len(value) > 512):
                data = _extract_capture_bytes(value)
                if data:
                    output_path.write_bytes(data)
                    return output_path
            candidate_path = Path(value)
            if candidate_path.exists():
                if candidate_path.resolve() != output_path.resolve():
                    shutil.copyfile(candidate_path, output_path)
                return output_path
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, (str, Path)):
                candidate_path = Path(first)
                if candidate_path.exists():
                    shutil.copyfile(candidate_path, output_path)
                    return output_path
        data = _extract_capture_bytes(value)
        if data:
            output_path.write_bytes(data)
            return output_path
    return None


def _write_pdf_from_png(
    png_path: Path, pdf_path: Path, *, resolution: float = 150.0
) -> Path | None:
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        with Image.open(png_path) as image:
            image = image.convert("RGB")
            image.save(pdf_path, "PDF", resolution=resolution)
        return pdf_path
    except Exception:
        return None


def _build_print_scale_js(scale: float) -> str:
    scaled_width = 100.0 / scale if scale else 100.0
    return (
        "(function() {"
        "var id='crawl4ai-print-scale';"
        "var style=document.getElementById(id);"
        "if(!style){style=document.createElement('style');style.id=id;document.head.appendChild(style);}"
        "style.textContent="
        "'@page{margin:0;}@media print{html,body{margin:0;padding:0;}"
        "body{transform:scale("
        + str(scale)
        + ");transform-origin:top left;width:"
        + str(scaled_width)
        + "%;}}';"
        "})();"
    )


def _looks_like_empty_html(html: str) -> bool:
    if not html or not html.strip():
        return True
    normalized = "".join(html.split()).lower()
    if normalized in ("<html></html>", "<html><head></head><body></body></html>"):
        return True
    if normalized in (
        "<divclass='crawl4ai-result'></div>",
        "<divclass=\"crawl4ai-result\"></div>",
    ):
        return True
    if "<body" not in normalized and "<div" not in normalized:
        return True
    return False


def _looks_like_gateway_timeout(html: str) -> bool:
    if not html:
        return False
    lowered = html.lower()
    return (
        "gateway time-out" in lowered
        or "gateway timeout" in lowered
        or "504 gateway" in lowered
        or ">504<" in lowered
    )


def _extract_text_value(value: object) -> str:
    if isinstance(value, str) and value.strip():
        normalized = "".join(value.split()).lower()
        if normalized in ("<html></html>", "<html><head></head><body></body></html>"):
            return ""
        if normalized in (
            "<divclass='crawl4ai-result'></div>",
            "<divclass=\"crawl4ai-result\"></div>",
        ):
            return ""
        if value.lstrip().lower().startswith("<html") and _looks_like_empty_html(value):
            return ""
        return value
    if isinstance(value, dict):
        for key in (
            "raw_markdown",
            "markdown_with_citations",
            "references_markdown",
            "markdown",
            "content",
            "text",
            "data",
            "raw",
        ):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
    if hasattr(value, "raw_markdown"):
        candidate = getattr(value, "raw_markdown", "")
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    if hasattr(value, "markdown_with_citations"):
        candidate = getattr(value, "markdown_with_citations", "")
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return ""


def _get_result_html(result: object) -> str:
    for attr in ("html", "cleaned_html", "fit_html"):
        value = getattr(result, attr, None)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _extract_best_text(
    result: object,
    *,
    prefer_fit_markdown: bool = False,
    prefer_extracted_content: bool = False,
) -> str:
    if prefer_extracted_content:
        extracted = _extract_text_value(getattr(result, "extracted_content", None))
        if extracted:
            return str(extracted)

    if prefer_fit_markdown:
        markdown = getattr(result, "markdown", None)
        if hasattr(markdown, "fit_markdown"):
            fit_markdown = getattr(markdown, "fit_markdown")
            if isinstance(fit_markdown, str) and fit_markdown.strip():
                return fit_markdown
        if isinstance(markdown, dict):
            fit_markdown = markdown.get("fit_markdown")
            if isinstance(fit_markdown, str) and fit_markdown.strip():
                return fit_markdown

    for attr in (
        "markdown",
        "markdown_v2",
        "text",
        "cleaned_html",
        "html",
        "extracted_content",
    ):
        value = getattr(result, attr, None)
        extracted = _extract_text_value(value)
        if extracted:
            return str(extracted)
    return ""


def _looks_like_html(text: str) -> bool:
    if not text:
        return False
    return text.lstrip("\ufeff \t\r\n").startswith("<")


def _structured_content_size(payload: dict) -> int:
    total = 0
    for section in payload.get("sections", []):
        for entry in section.get("content", []):
            total += len(str(entry))
        for table in section.get("tables", []):
            for row in table:
                total += sum(len(str(cell)) for cell in row)
    return total


def _build_moegirl_render_url(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.netloc or not parsed.path:
        return None
    if not parsed.netloc.endswith("mzh.moegirl.org.cn"):
        return None
    title = None
    if parsed.path.endswith("/index.php"):
        params = parse_qs(parsed.query)
        title = params.get("title", [None])[0]
    else:
        path = parsed.path.strip("/")
        if path:
            title = unquote(path)
    if not title:
        return None
    return f"{parsed.scheme}://{parsed.netloc}/index.php?title={quote(title)}&action=render"


def _extract_mediawiki_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    main = (
        soup.select_one(".mw-parser-output")
        or soup.select_one("#mw-content-text")
        or soup.body
    )
    if not main:
        return ""
    return main.get_text("\n", strip=True)


def _has_mediawiki_content(html: str) -> bool:
    if not html or not html.strip():
        return False
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one(".mw-parser-output") or soup.select_one("#mw-content-text")
    if not main:
        return False
    if main.find("table"):
        return True
    text = main.get_text(" ", strip=True)
    return len(text) > 80


def _node_to_text(node: object) -> str:
    if not getattr(node, "name", None):
        return ""
    if node.name in ("ul", "ol"):
        items = [
            item.get_text(" ", strip=True)
            for item in node.find_all("li", recursive=False)
        ]
        return "\n".join(f"- {item}" for item in items if item)
    if node.name == "dl":
        lines = []
        for term in node.find_all("dt", recursive=False):
            desc = term.find_next_sibling("dd")
            term_text = term.get_text(" ", strip=True)
            desc_text = desc.get_text(" ", strip=True) if desc else ""
            if term_text or desc_text:
                lines.append(f"{term_text}: {desc_text}".strip(": "))
        return "\n".join(lines)
    return node.get_text("\n", strip=True)


def _table_to_rows(table: object) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [
            cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])
        ]
        if cells:
            rows.append(cells)
    return rows


_HEADING_TAGS = ("h2", "h3", "h4")
_BLOCK_TAGS = ("p", "ul", "ol", "dl", "blockquote", "table")
_NOISE_SNIPPETS = (
    "展开/折叠",
    "啊咧？！视频不见了！",
    "服务器切换",
    "衣装切换",
    "翻译进行中",
    "按\"Ctrl+D\"",
    "WIKI功能→编辑",
    "WIKI功能->编辑",
    "首页",
)

def _strip_hidden_elements(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(True):
        attrs = tag.attrs or {}
        if "hidden" in attrs:
            tag.decompose()
            continue
        if attrs.get("aria-hidden") == "true":
            tag.decompose()
            continue
        style = attrs.get("style", "")
        if style:
            normalized = style.replace(" ", "").lower()
            if "display:none" in normalized or "visibility:hidden" in normalized or "opacity:0" in normalized:
                tag.decompose()


def _collect_blocks(root: BeautifulSoup) -> list:
    blocks: list = []

    def walk(node: object) -> None:
        for child in getattr(node, "children", []):
            if not getattr(child, "name", None):
                continue
            if child.name in _HEADING_TAGS or child.name in _BLOCK_TAGS:
                blocks.append(child)
                continue
            if child.name == "div":
                if not child.find(list(_HEADING_TAGS + _BLOCK_TAGS), recursive=True):
                    blocks.append(child)
                    continue
            walk(child)

    walk(root)
    return blocks


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _filter_content_entries(entries: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        compact = _normalize_text(entry)
        if not compact:
            continue
        if len(compact) <= 1:
            continue
        if any(snippet in compact for snippet in _NOISE_SNIPPETS):
            continue
        key = compact.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(entry)
    return cleaned


def _extract_mediawiki_structured(html: str, *, source_url: str) -> dict:
    if not html:
        return {}
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.select("script, style, noscript, textarea"):
        tag.decompose()
    for tag in soup.select(
        ".mw-editsection, .toc, .navbox, .navbar, .metadata, #mw-navigation, #footer, .ads, .comments"
    ):
        tag.decompose()
    _strip_hidden_elements(soup)

    title_node = soup.select_one("#firstHeading") or soup.select_one("title")
    title = title_node.get_text(" ", strip=True) if title_node else ""
    if not title:
        parsed = urlparse(source_url)
        if parsed.path.endswith("/index.php"):
            params = parse_qs(parsed.query)
            title = params.get("title", [""])[0]
        else:
            title = unquote(parsed.path.strip("/").split("/")[-1])
    root = (
        soup.select_one(".mw-parser-output")
        or soup.select_one("#mw-content-text")
        or soup.body
    )
    if not root:
        return {}

    elements = _collect_blocks(root)

    sections: list[dict[str, object]] = []
    current = {"heading": "intro", "content": [], "tables": []}
    for child in elements:
        if child.name in ("h2", "h3", "h4"):
            if current["content"] or current["tables"]:
                current["content"] = _filter_content_entries(current["content"])
                sections.append(current)
            heading = child.get_text(" ", strip=True) or "section"
            current = {"heading": heading, "content": [], "tables": []}
            continue
        if child.name == "table":
            rows = _table_to_rows(child)
            if rows:
                current["tables"].append(rows)
            continue
        if child.name in ("p", "ul", "ol", "dl", "blockquote", "div"):
            text = _node_to_text(child)
            if text:
                current["content"].append(text)

    if current["content"] or current["tables"]:
        current["content"] = _filter_content_entries(current["content"])
        sections.append(current)

    if "wiki.biligame.com/umamusume" in source_url:
        for section in sections:
            cleaned_content = []
            for entry in section["content"]:
                cleaned = _strip_json_blocks(str(entry), _BILIGAME_JSON_MARKERS).strip()
                if cleaned:
                    cleaned_content.append(cleaned)
            section["content"] = cleaned_content

    summary = ""
    for section in sections:
        summary_parts = section["content"][:2]
        summary = "\n".join(summary_parts).strip()
        if summary:
            break

    return {
        "title": title,
        "summary": summary,
        "sections": sections,
        "source_url": source_url,
    }


def _build_run_config(
    use_proxy: bool,
    *,
    css_selector: str | None = None,
    anti_bot: bool = False,
    wait_for_selector: str | None = None,
    wait_until: str | None = None,
    session_id: str | None = None,
    page_timeout_ms: int | None = None,
    markdown_generator: DefaultMarkdownGenerator | None = None,
    extraction_strategy: object | None = None,
) -> CrawlerRunConfig:
    proxy_url = config.proxy_url()
    proxy = (
        SingleProxyRotationStrategy(ProxyConfig(server=proxy_url))
        if proxy_url and use_proxy
        else None
    )
    run_config = CrawlerRunConfig(
        markdown_generator=markdown_generator or _md_generator,
        extraction_strategy=extraction_strategy,
        proxy_rotation_strategy=proxy,
        excluded_selector=".ads, .comments, #sidebar, #mw-navigation, #footer",
        css_selector=css_selector,
        word_count_threshold=5,
        wait_until=wait_until or ("commit" if anti_bot else "domcontentloaded"),
        wait_for=wait_for_selector or css_selector or "body",
        wait_for_timeout=60000 if anti_bot else None,
        page_timeout=page_timeout_ms
        if page_timeout_ms is not None
        else (60000 if anti_bot else None),
        delay_before_return_html=3.0 if anti_bot else 2.0,
        remove_overlay_elements=True,
        magic=True,
        scan_full_page=True,
        user_agent=_REAL_USER_AGENT,
        simulate_user=anti_bot,
        override_navigator=anti_bot,
    )
    if session_id:
        _apply_optional_config(run_config, {"session_id": session_id})
    if anti_bot:
        _apply_optional_config(run_config, {"cache_mode": "BYPASS"})
        if getattr(run_config, "js_code", None) is None:
            _apply_optional_config(run_config, {"js_code": _STEALTH_JS})
    return run_config


def _build_capture_run_config(
    use_proxy: bool,
    *,
    css_selector: str | None,
    anti_bot: bool,
    wait_for_selector: str | None,
    wait_until: str | None,
    session_id: str | None,
    page_timeout_ms: int | None,
    png_path: Path,
    pdf_path: Path | None,
    capture_screenshot: bool,
    capture_pdf: bool,
    screenshot_wait_for: float | None,
    delay_before_return_html: float | None,
    wait_for_images: bool | None,
    print_scale: float | None,
) -> CrawlerRunConfig:
    run_config = _build_run_config(
        use_proxy,
        css_selector=css_selector,
        anti_bot=anti_bot,
        wait_for_selector=wait_for_selector,
        wait_until=wait_until,
        session_id=session_id,
        page_timeout_ms=page_timeout_ms,
        markdown_generator=None,
        extraction_strategy=None,
    )
    run_config.screenshot = bool(capture_screenshot)
    run_config.pdf = bool(capture_pdf)
    run_config.verbose = False
    if screenshot_wait_for is not None:
        run_config.screenshot_wait_for = screenshot_wait_for
    if delay_before_return_html is not None:
        run_config.delay_before_return_html = delay_before_return_html
    if wait_for_images is not None:
        run_config.wait_for_images = wait_for_images
    if print_scale is not None and print_scale > 0:
        scale_js = _build_print_scale_js(print_scale)
        existing_js = getattr(run_config, "js_code", None)
        if existing_js:
            if isinstance(existing_js, list):
                existing_js.append(scale_js)
                run_config.js_code = existing_js
            else:
                run_config.js_code = [existing_js, scale_js]
        else:
            run_config.js_code = scale_js
    if capture_screenshot:
        _apply_optional_config(
            run_config,
            {
                "screenshot": True,
                "take_screenshot": True,
                "capture_screenshot": True,
                "screenshot_full_page": True,
                "full_page": True,
                "screenshot_path": str(png_path),
                "screenshot_file": str(png_path),
            },
        )
    if capture_pdf and pdf_path:
        _apply_optional_config(
            run_config,
            {
                "pdf": True,
                "save_pdf": True,
                "pdf_path": str(pdf_path),
                "pdf_file": str(pdf_path),
            },
        )
    return run_config


async def _crawl_with_config(
    url: str,
    *,
    target_url: str | None,
    source_url: str | None,
    use_proxy: bool,
    css_selector: str | None,
    wait_for_selector: str | None,
    anti_bot: bool,
    structured: bool,
    allow_render_fallback: bool,
    headless: bool = True,
    markdown_generator: DefaultMarkdownGenerator | None,
    extraction_strategy: object | None,
    prefer_fit_markdown: bool,
    prefer_extracted_content: bool,
    timeout_s: float | None,
) -> str:
    crawl_url = target_url or url
    source_url = source_url or url
    timeout_s = _resolve_timeout(timeout_s)
    headers = {
        "User-Agent": _REAL_USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/",
    }
    user_data_dir = _resolve_user_data_dir()
    browser_cfg = BrowserConfig(
        headless=headless,
        user_agent=_REAL_USER_AGENT,
        viewport_width=1920,
        viewport_height=1080,
        headers=headers,
        use_managed_browser=bool(user_data_dir),
        user_data_dir=user_data_dir,
        extra_args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
        ],
        enable_stealth=anti_bot,
    )
    async with AsyncWebCrawler(config=browser_cfg, verbose=False) as crawler:
        result = await _await_with_timeout(
            crawler.arun(
                url=crawl_url,
                config=_build_run_config(
                    use_proxy,
                    css_selector=css_selector,
                    anti_bot=anti_bot,
                    wait_for_selector=wait_for_selector,
                    markdown_generator=markdown_generator,
                    extraction_strategy=extraction_strategy,
                ),
            ),
            timeout_s,
        )
        content = _extract_best_text(
            result,
            prefer_fit_markdown=prefer_fit_markdown,
            prefer_extracted_content=prefer_extracted_content,
        )
        html_snapshot = _get_result_html(result)
        if structured and _looks_like_html(content):
            content = ""

        if structured:
            if not content and html_snapshot:
                content = _extract_mediawiki_text(html_snapshot)

            if css_selector and not content:
                fallback_result = await _await_with_timeout(
                    crawler.arun(
                        url=crawl_url,
                        config=_build_run_config(
                            use_proxy,
                            css_selector=None,
                            anti_bot=anti_bot,
                            wait_for_selector="body",
                            wait_until=None,
                            markdown_generator=markdown_generator,
                            extraction_strategy=extraction_strategy,
                        ),
                    ),
                    timeout_s,
                )
                fallback_html = _get_result_html(fallback_result)
                fallback_content = _extract_best_text(
                    fallback_result,
                    prefer_fit_markdown=prefer_fit_markdown,
                    prefer_extracted_content=prefer_extracted_content,
                )
                if not fallback_content and fallback_html:
                    fallback_content = _extract_mediawiki_text(fallback_html)
                if fallback_content:
                    content = fallback_content
                if fallback_html and (
                    _looks_like_empty_html(html_snapshot)
                    or len(fallback_html) > len(html_snapshot)
                ):
                    html_snapshot = fallback_html

            html_ready = (
                html_snapshot
                and not _looks_like_empty_html(html_snapshot)
                and _has_mediawiki_content(html_snapshot)
            )
            if not html_ready and allow_render_fallback:
                render_url = _build_moegirl_render_url(source_url)
                if render_url and render_url != crawl_url:
                    render_result = await _await_with_timeout(
                        crawler.arun(
                            url=render_url,
                            config=_build_run_config(
                                use_proxy,
                                css_selector=css_selector,
                                anti_bot=anti_bot,
                                wait_for_selector=wait_for_selector,
                                wait_until=None,
                                markdown_generator=markdown_generator,
                                extraction_strategy=extraction_strategy,
                            ),
                        ),
                        timeout_s,
                    )
                    render_html = _get_result_html(render_result)
                    if render_html:
                        html_snapshot = render_html
                        html_ready = _has_mediawiki_content(render_html)
                        if not content and html_ready:
                            content = _extract_mediawiki_text(render_html)

            if html_ready:
                structured_payload = _extract_mediawiki_structured(
                    html_snapshot, source_url=source_url
                )
                if structured_payload:
                    size = _structured_content_size(structured_payload)
                    if size >= 300 or not content:
                        return json.dumps(
                            structured_payload, ensure_ascii=False, indent=2
                        )

        if content:
            return _post_process_content(url, content)
        return ""


async def _crawl_page_visual(
    url: str,
    *,
    target_url: str | None,
    source_url: str | None,
    use_proxy: bool,
    css_selector: str | None,
    wait_for_selector: str | None,
    anti_bot: bool,
    output_dir: Path,
    capture_pdf: bool,
    screenshot_wait_for: float | None,
    delay_before_return_html: float | None,
    wait_for_images: bool | None,
    preload_url: str | None = None,
    preload_delay_s: float | None = None,
    wait_until: str | None = None,
    page_timeout_ms: int | None = None,
    session_id: str | None = None,
    headless: bool = True,
    pdf_from_png: bool = False,
    print_scale: float | None = None,
    timeout_s: float | None = None,
) -> dict[str, str]:
    crawl_url = target_url or url
    source_url = source_url or url
    output_dir.mkdir(parents=True, exist_ok=True)
    timeout_s = _resolve_timeout(timeout_s)
    slug = _slug_from_url(source_url)
    png_path = output_dir / f"{slug}.png"
    pdf_path = output_dir / f"{slug}.pdf" if capture_pdf else None

    headers = {
        "User-Agent": _REAL_USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.google.com/",
    }
    user_data_dir = _resolve_user_data_dir()
    browser_cfg = BrowserConfig(
        headless=headless,
        user_agent=_REAL_USER_AGENT,
        viewport_width=1920,
        viewport_height=1080,
        headers=headers,
        use_managed_browser=bool(user_data_dir),
        user_data_dir=user_data_dir,
        extra_args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
        ],
        enable_stealth=anti_bot,
    )
    async with AsyncWebCrawler(config=browser_cfg, verbose=True) as crawler:
        if preload_url:
            try:
                preload_timeout = timeout_s if timeout_s and timeout_s > 0 else None
                if preload_timeout:
                    preload_timeout = min(preload_timeout, 60.0 if anti_bot else 20.0)
                await _await_with_timeout(
                    crawler.arun(
                        url=preload_url,
                        config=_build_run_config(
                            use_proxy,
                            css_selector=None,
                            anti_bot=False,
                            wait_for_selector="body",
                            wait_until="commit",
                            session_id=session_id,
                            page_timeout_ms=page_timeout_ms,
                            markdown_generator=None,
                            extraction_strategy=None,
                        ),
                    ),
                    preload_timeout,
                )
                if preload_delay_s:
                    await asyncio.sleep(preload_delay_s)
            except Exception as exc:
                print(f"Warning: preload url failed: {exc}")

        async def run_capture(
            selector: str | None,
            wait_for: str | None,
            *,
            capture_screenshot: bool,
            capture_pdf: bool,
            print_scale_override: float | None,
        ) -> tuple[Path | None, Path | None]:
            max_retries = 2 if anti_bot else 1
            result = None
            last_error: Exception | None = None
            for attempt in range(max_retries):
                try:
                    if max_retries > 1:
                        print(f"Attempt {attempt + 1}/{max_retries} to load page.")
                    attempt_timeout = timeout_s
                    if timeout_s and timeout_s > 0:
                        if anti_bot:
                            attempt_timeout = 60.0 if attempt == 0 else min(timeout_s, 30.0)
                        else:
                            attempt_timeout = min(timeout_s, 25.0)
                    result = await _await_with_timeout(
                        crawler.arun(
                            url=crawl_url,
                            config=_build_capture_run_config(
                                use_proxy,
                                css_selector=selector,
                                anti_bot=anti_bot,
                                wait_for_selector=wait_for,
                                wait_until=wait_until,
                                session_id=session_id,
                                page_timeout_ms=page_timeout_ms,
                                png_path=png_path,
                                pdf_path=pdf_path,
                                capture_screenshot=capture_screenshot,
                                capture_pdf=capture_pdf,
                                screenshot_wait_for=screenshot_wait_for,
                                delay_before_return_html=delay_before_return_html,
                                wait_for_images=wait_for_images,
                                print_scale=print_scale_override,
                            ),
                        ),
                        attempt_timeout,
                    )
                    html_snapshot = _get_result_html(result)
                    if html_snapshot and _looks_like_gateway_timeout(html_snapshot):
                        raise RuntimeError("Gateway timeout detected; retrying.")
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < max_retries - 1:
                        print(f"Attempt {attempt + 1} failed: {exc}. Retrying...")
                        await asyncio.sleep(2.0)
                        continue
                    raise
            if result is None and last_error is not None:
                raise last_error
            png_saved = None
            if capture_screenshot:
                png_saved = _save_capture_result(
                    result, output_path=png_path, candidates=_CAPTURE_PNG_ATTRS
                )
            pdf_saved = None
            if capture_pdf and pdf_path:
                pdf_saved = _save_capture_result(
                    result, output_path=pdf_path, candidates=_CAPTURE_PDF_ATTRS
                )
                if not pdf_saved:
                    pdf_bytes = getattr(result, "pdf", None)
                    if isinstance(pdf_bytes, (bytes, bytearray)) and pdf_bytes:
                        pdf_path.write_bytes(bytes(pdf_bytes))
                        pdf_saved = pdf_path
            return png_saved, pdf_saved

        if print_scale is not None and capture_pdf:
            png_saved, _ = await run_capture(
                css_selector,
                wait_for_selector,
                capture_screenshot=True,
                capture_pdf=False,
                print_scale_override=None,
            )
            if not png_saved:
                png_saved, _ = await run_capture(
                    None,
                    "body",
                    capture_screenshot=True,
                    capture_pdf=False,
                    print_scale_override=None,
                )

            _, pdf_saved = await run_capture(
                css_selector,
                wait_for_selector,
                capture_screenshot=False,
                capture_pdf=True,
                print_scale_override=print_scale,
            )
            if not pdf_saved:
                _, pdf_saved = await run_capture(
                    None,
                    "body",
                    capture_screenshot=False,
                    capture_pdf=True,
                    print_scale_override=print_scale,
                )
        else:
            png_saved, pdf_saved = await run_capture(
                css_selector,
                wait_for_selector,
                capture_screenshot=True,
                capture_pdf=capture_pdf,
                print_scale_override=print_scale,
            )
            if not png_saved and not pdf_saved:
                png_saved, pdf_saved = await run_capture(
                    None,
                    "body",
                    capture_screenshot=True,
                    capture_pdf=capture_pdf,
                    print_scale_override=print_scale,
                )

    if capture_pdf and png_saved and pdf_from_png and pdf_path:
        pdf_saved = _write_pdf_from_png(png_saved, pdf_path) or pdf_saved

    if not png_saved and not pdf_saved:
        raise RuntimeError("Crawl did not return screenshot or pdf output.")

    return {
        "png_path": str(png_saved) if png_saved else "",
        "pdf_path": str(pdf_saved) if pdf_saved else "",
        "source_url": source_url,
    }


async def crawl_page(
    url: str, *, use_proxy: bool = False, timeout_s: float | None = None
) -> str:
    return await _run_with_timeout(
        _crawl_with_config(
            url,
            target_url=None,
            source_url=None,
            use_proxy=use_proxy,
            css_selector=None,
            wait_for_selector=None,
            anti_bot=False,
            structured=False,
            allow_render_fallback=False,
            markdown_generator=None,
            extraction_strategy=None,
            prefer_fit_markdown=False,
            prefer_extracted_content=False,
            timeout_s=timeout_s,
        ),
        timeout_s,
    )


async def crawl_biligame_page(
    url: str, *, use_proxy: bool = False, timeout_s: float | None = None
) -> str:
    return await _run_with_timeout(
        _crawl_with_config(
            url,
            target_url=None,
            source_url=None,
            use_proxy=use_proxy,
            css_selector=_BILIGAME_MAIN_SELECTOR,
            wait_for_selector=_BILIGAME_MAIN_SELECTOR,
            anti_bot=False,
            structured=True,
            allow_render_fallback=False,
            markdown_generator=None,
            extraction_strategy=None,
            prefer_fit_markdown=False,
            prefer_extracted_content=False,
            timeout_s=timeout_s,
        ),
        timeout_s,
    )


async def crawl_moegirl_page(
    url: str, *, use_proxy: bool = True, timeout_s: float | None = None
) -> str:
    render_url = _build_moegirl_render_url(url) or url
    return await _run_with_timeout(
        _crawl_with_config(
            url,
            target_url=render_url,
            source_url=url,
            use_proxy=use_proxy,
            css_selector=_MOEGIRL_MAIN_SELECTOR,
            wait_for_selector=_MOEGIRL_MAIN_SELECTOR,
            anti_bot=True,
            structured=True,
            allow_render_fallback=False,
            markdown_generator=None,
            extraction_strategy=None,
            prefer_fit_markdown=False,
            prefer_extracted_content=False,
            timeout_s=timeout_s,
        ),
        timeout_s,
    )


async def crawl_biligame_page_pruned(
    url: str, *, use_proxy: bool = False, timeout_s: float | None = None
) -> str:
    return await _run_with_timeout(
        _crawl_with_config(
            url,
            target_url=None,
            source_url=None,
            use_proxy=use_proxy,
            css_selector=_BILIGAME_MAIN_SELECTOR,
            wait_for_selector=_BILIGAME_MAIN_SELECTOR,
            anti_bot=False,
            structured=False,
            allow_render_fallback=False,
            markdown_generator=_build_pruning_markdown_generator(),
            extraction_strategy=None,
            prefer_fit_markdown=True,
            prefer_extracted_content=False,
            timeout_s=timeout_s,
        ),
        timeout_s,
    )


async def crawl_moegirl_page_pruned(
    url: str, *, use_proxy: bool = True, timeout_s: float | None = None
) -> str:
    render_url = _build_moegirl_render_url(url) or url
    return await _run_with_timeout(
        _crawl_with_config(
            url,
            target_url=render_url,
            source_url=url,
            use_proxy=use_proxy,
            css_selector=_MOEGIRL_MAIN_SELECTOR,
            wait_for_selector=_MOEGIRL_MAIN_SELECTOR,
            anti_bot=True,
            structured=False,
            allow_render_fallback=False,
            markdown_generator=_build_pruning_markdown_generator(),
            extraction_strategy=None,
            prefer_fit_markdown=True,
            prefer_extracted_content=False,
            timeout_s=timeout_s,
        ),
        timeout_s,
    )


def _choose_capture_path(capture: dict[str, str]) -> str:
    return capture.get("pdf_path") or capture.get("png_path") or ""


async def crawl_biligame_page_visual(
    url: str,
    *,
    use_proxy: bool = False,
    output_dir: Path | None = None,
    workspace: UmamusumeCrawler | str | Path | None = None,
    keep_files: bool = False,
    capture_pdf: bool = True,
    headless: bool = True,
    pdf_from_png: bool = False,
    print_scale: float | None = None,
    timeout_s: float | None = None,
) -> dict[str, str]:
    output_dir, _ = _resolve_output_dir(
        output_dir,
        workspace=workspace,
        keep_files=keep_files,
        require_output_dir=True,
    )
    return await _run_with_timeout(
        _crawl_page_visual(
            url,
            target_url=None,
            source_url=None,
            use_proxy=use_proxy,
            css_selector=_BILIGAME_MAIN_SELECTOR,
            wait_for_selector=_BILIGAME_MAIN_SELECTOR,
            anti_bot=False,
            output_dir=output_dir,
            capture_pdf=capture_pdf,
            screenshot_wait_for=None,
            delay_before_return_html=None,
            wait_for_images=None,
            preload_url=None,
            preload_delay_s=None,
            headless=headless,
            pdf_from_png=pdf_from_png,
            print_scale=print_scale,
            timeout_s=timeout_s,
        ),
        timeout_s,
    )


async def crawl_moegirl_page_visual(
    url: str,
    *,
    use_proxy: bool = True,
    output_dir: Path | None = None,
    workspace: UmamusumeCrawler | str | Path | None = None,
    keep_files: bool = False,
    capture_pdf: bool = True,
    headless: bool = True,
    pdf_from_png: bool = False,
    print_scale: float | None = None,
    timeout_s: float | None = None,
) -> dict[str, str]:
    output_dir, _ = _resolve_output_dir(
        output_dir,
        workspace=workspace,
        keep_files=keep_files,
        require_output_dir=True,
    )
    session_id = f"visual-{_slug_from_url(url)}"
    return await _run_with_timeout(
        _crawl_page_visual(
            url,
            target_url=None,
            source_url=url,
            use_proxy=use_proxy,
            css_selector=_MOEGIRL_MAIN_SELECTOR,
            wait_for_selector=_MOEGIRL_MAIN_SELECTOR,
            anti_bot=True,
            output_dir=output_dir,
            capture_pdf=capture_pdf,
            screenshot_wait_for=6.0,
            delay_before_return_html=6.0,
            wait_for_images=True,
            preload_url="https://mzh.moegirl.org.cn/Mainpage#/flow",
            preload_delay_s=2.0,
            wait_until="commit",
            page_timeout_ms=60000,
            session_id=session_id,
            headless=headless,
            pdf_from_png=pdf_from_png,
            print_scale=print_scale,
            timeout_s=timeout_s,
        ),
        timeout_s,
    )


async def crawl_moegirl_page_visual_markitdown(
    url: str,
    *,
    use_proxy: bool | None = None,
    output_dir: Path | None = None,
    workspace: UmamusumeCrawler | str | Path | None = None,
    keep_files: bool = False,
    capture_pdf: bool = True,
    print_scale: float | None = None,
    headless: bool = False,
    timeout_s: float | None = None,
) -> str:
    async def _run() -> str:
        proxy_flag = bool(config.proxy_url()) if use_proxy is None else use_proxy
        if print_scale is None:
            print_scale_value = 0.65
        else:
            print_scale_value = print_scale
        resolved_output_dir, temp_workspace = _resolve_output_dir(
            output_dir,
            workspace=workspace,
            keep_files=keep_files,
            require_output_dir=False,
        )

        async def _capture_and_convert(headless_flag: bool) -> str:
            capture = await crawl_moegirl_page_visual(
                url,
                use_proxy=proxy_flag,
                output_dir=resolved_output_dir,
                capture_pdf=capture_pdf,
                print_scale=print_scale_value,
                headless=headless_flag,
                timeout_s=timeout_s,
            )
            if capture_pdf:
                target_path = capture.get("pdf_path", "")
                if not target_path and resolved_output_dir:
                    candidate = resolved_output_dir / f"{_slug_from_url(url)}.pdf"
                    if candidate.exists():
                        target_path = str(candidate)
                if not target_path:
                    raise RuntimeError("PDF capture failed; no pdf_path returned.")
            else:
                target_path = _choose_capture_path(capture)
                if not target_path:
                    return ""
            from umamusume_web_crawler.web.process import convert_markitdown

            return convert_markitdown(target_path)

        try:
            content = await _capture_and_convert(headless)
            if content:
                return content
            if headless:
                print(
                    "Warning: headless capture returned empty content; retrying headful."
                )
                return await _capture_and_convert(False)
            return content
        except Exception as exc:
            if headless:
                print(f"Warning: headless capture failed: {exc}. Retrying headful.")
                try:
                    return await _capture_and_convert(False)
                except Exception as retry_exc:
                    print(f"Warning: headful retry failed: {retry_exc}")
                    return ""
            raise
        finally:
            if temp_workspace is not None:
                temp_workspace.cleanup()

    return await _run_with_timeout(_run(), timeout_s)


async def crawl_page_visual_markitdown(
    url: str,
    *,
    use_proxy: bool | None = None,
    output_dir: Path | None = None,
    workspace: UmamusumeCrawler | str | Path | None = None,
    keep_files: bool = False,
    capture_pdf: bool = True,
    timeout_s: float | None = None,
) -> str:
    async def _run() -> str:
        proxy_flag = bool(config.proxy_url()) if use_proxy is None else use_proxy
        resolved_output_dir, temp_workspace = _resolve_output_dir(
            output_dir,
            workspace=workspace,
            keep_files=keep_files,
            require_output_dir=False,
        )
        capture = await _crawl_page_visual(
            url,
            target_url=None,
            source_url=None,
            use_proxy=proxy_flag,
            css_selector=None,
            wait_for_selector="body",
            anti_bot=True,
            output_dir=resolved_output_dir,
            capture_pdf=capture_pdf,
            screenshot_wait_for=4.0,
            delay_before_return_html=4.0,
            wait_for_images=None,
            print_scale=None,
            timeout_s=timeout_s,
        )
        if capture_pdf:
            target_path = capture.get("pdf_path", "")
            if not target_path:
                raise RuntimeError("PDF capture failed; no pdf_path returned.")
        else:
            target_path = _choose_capture_path(capture)
            if not target_path:
                return ""
        from umamusume_web_crawler.web.process import convert_markitdown

        try:
            return convert_markitdown(target_path)
        finally:
            if temp_workspace is not None:
                temp_workspace.cleanup()

    return await _run_with_timeout(_run(), timeout_s)


async def crawl_biligame_page_visual_markitdown(
    url: str,
    *,
    use_proxy: bool | None = None,
    output_dir: Path | None = None,
    workspace: UmamusumeCrawler | str | Path | None = None,
    keep_files: bool = False,
    capture_pdf: bool = True,
    timeout_s: float | None = None,
) -> str:
    async def _run() -> str:
        proxy_flag = bool(config.proxy_url()) if use_proxy is None else use_proxy
        resolved_output_dir, temp_workspace = _resolve_output_dir(
            output_dir,
            workspace=workspace,
            keep_files=keep_files,
            require_output_dir=False,
        )
        capture = await crawl_biligame_page_visual(
            url,
            use_proxy=proxy_flag,
            output_dir=resolved_output_dir,
            capture_pdf=capture_pdf,
            timeout_s=timeout_s,
        )
        if capture_pdf:
            target_path = capture.get("pdf_path", "")
            if not target_path:
                raise RuntimeError("PDF capture failed; no pdf_path returned.")
        else:
            target_path = _choose_capture_path(capture)
            if not target_path:
                return ""
        from umamusume_web_crawler.web.process import convert_markitdown

        try:
            return convert_markitdown(target_path)
        finally:
            if temp_workspace is not None:
                temp_workspace.cleanup()

    return await _run_with_timeout(_run(), timeout_s)
