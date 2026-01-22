from __future__ import annotations

import json
import re
from typing import Dict, Tuple

_INFOBOX_MARKERS = ("角色信息", "infobox")
_SECTION_PATTERN = re.compile(r"^(={2,})\s*(.+?)\s*\1\s*$")


def _clean_template(content: str, *, site: str | None) -> str:
    parts = [part.strip() for part in content.split("|")]
    if not parts:
        return ""
    name = parts[0]
    params = [part for part in parts[1:] if part]

    if name in ("提示", "notice", "tip"):
        # Bwiki uses 提示模板承载翻译/警告信息，保留正文参数
        for param in params:
            if "=" in param:
                continue
            return param
        return ""

    if name in ("lang", "lj", "ruby"):
        for param in reversed(params):
            if param and "=" not in param:
                return param
        return ""

    if site == "biligame":
        # Bwiki 页面倾向于用模板包裹字段，尽量保留最后可见文本
        for param in reversed(params):
            if param and "=" not in param:
                return param
        return ""

    # 默认策略：保留最后一个非空参数
    for param in reversed(params):
        if param and "=" not in param:
            return param
    return ""


def clean_wiki_value(text: str, *, site: str | None = None) -> str:
    """温和清洗 Wiki 文本，尽量保留内容。"""
    if not text:
        return ""
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"'{2,5}(.*?)'{2,5}", r"\1", text)
    text = re.sub(r"<(br|BR|Br)\s*/?>", "\n", text)

    def replace_template(match: re.Match[str]) -> str:
        return _clean_template(match.group(1), site=site)

    text = re.sub(r"\{\{(.*?)\}\}", replace_template, text)
    text = re.sub(r"<.*?>", "", text)
    return text.strip()


def clean_wikitext_for_llm(text: str, *, site: str | None = None) -> str:
    """轻量清洗：保留结构与内容，只去噪音。"""
    if not text:
        return ""

    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"[\1]", text)
    text = re.sub(r"<ref[^>]*>(.*?)</ref>", r" (\1) ", text, flags=re.DOTALL)
    text = re.sub(r"<ref[^>]*/>", "", text)
    text = re.sub(r"<(br|BR|Br)\s*/?>", "\n", text)
    text = re.sub(
        r"</?(div|span|center|font|big|small|table|tr|td|th)[^>]*>", " ", text
    )

    def replace_template(match: re.Match[str]) -> str:
        content = match.group(1).strip()
        if content.startswith(":"):
            return f"\n> 🔗 **关联页面**: {content[1:].strip()}\n"
        return _clean_template(content, site=site)

    for _ in range(3):
        text = re.sub(r"\{\{(.*?)\}\}", replace_template, text)

    def heading_replace(match: re.Match[str]) -> str:
        level = len(match.group(1))
        title = match.group(2).strip()
        return f"{'#' * level} {title}"

    text = re.sub(r"^(=+)\s*(.*?)\s*\1$", heading_replace, text, flags=re.MULTILINE)

    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("|") and "=" in stripped:
            key, val = stripped[1:].split("=", 1)
            key = key.strip()
            val = val.strip()
            if key and val:
                lines.append(f"- **{key}**: {val}")
            else:
                lines.append(stripped)
        else:
            lines.append(stripped)
    return "\n".join(lines).strip()


def _extract_infobox_block(wikitext: str) -> Tuple[str, int, int]:
    if not wikitext:
        return "", -1, -1
    for match in re.finditer(r"\{\{", wikitext):
        start = match.start()
        preview = wikitext[start : start + 120].lower()
        if not any(marker in preview for marker in _INFOBOX_MARKERS):
            continue
        depth = 0
        i = start
        while i < len(wikitext):
            if wikitext.startswith("{{", i):
                depth += 1
                i += 2
                continue
            if wikitext.startswith("}}", i):
                depth -= 1
                i += 2
                if depth == 0:
                    return wikitext[start:i], start, i
                continue
            i += 1
    return "", -1, -1


def _parse_infobox_fields(infobox_raw: str, *, site: str | None) -> Dict[str, str]:
    data: Dict[str, str] = {}
    current_key = ""
    buffer: list[str] = []
    for raw_line in infobox_raw.splitlines():
        line = raw_line.rstrip()
        if line.startswith("|") and "=" in line:
            if current_key:
                value = "\n".join(buffer).strip()
                cleaned = clean_wiki_value(value, site=site)
                if cleaned:
                    data[current_key] = cleaned
            key, value = line[1:].split("=", 1)
            current_key = key.strip()
            buffer = [value.strip()]
        elif current_key:
            buffer.append(line.strip())
    if current_key:
        value = "\n".join(buffer).strip()
        cleaned = clean_wiki_value(value, site=site)
        if cleaned:
            data[current_key] = cleaned
    return data


def _extract_transclusions(wikitext: str) -> list[str]:
    titles: list[str] = []
    for match in re.finditer(r"\{\{:\s*([^}|]+)", wikitext):
        title = match.group(1).strip()
        if title and title not in titles:
            titles.append(title)
    return titles


def _split_sections(wikitext: str, *, site: str | None) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_heading = "intro"
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        raw = "\n".join(buffer).strip()
        cleaned = clean_wiki_value(raw, site=site)
        if cleaned:
            sections.append({"heading": current_heading, "content": cleaned})

    for line in wikitext.splitlines():
        match = _SECTION_PATTERN.match(line)
        if match:
            flush()
            current_heading = match.group(2).strip() or "section"
            buffer = []
            continue
        buffer.append(line)
    flush()
    return sections


def parse_wiki_page(
    wikitext: str, *, site: str | None = None
) -> Dict[str, str | Dict[str, str] | list[dict[str, str]] | list[str]]:
    """解析整页内容，返回 infobox + intro + raw_text + raw_wikitext + sections + transclusions。"""
    if not wikitext:
        return {
            "infobox": {},
            "intro": "",
            "raw_text": "",
            "raw_wikitext": "",
            "sections": [],
            "transclusions": [],
        }

    infobox_raw, start, end = _extract_infobox_block(wikitext)
    remaining_text = wikitext
    infobox_data: Dict[str, str] = {}
    if infobox_raw:
        infobox_data = _parse_infobox_fields(infobox_raw, site=site)
        remaining_text = (wikitext[:start] + wikitext[end:]).strip()

    transclusions = _extract_transclusions(remaining_text)
    sections = _split_sections(remaining_text, site=site)
    intro_text = sections[0]["content"] if sections else ""
    raw_text = "\n\n".join(
        f"{section['heading']}\n{section['content']}" if section["heading"] != "intro" else section["content"]
        for section in sections
    ).strip()

    return {
        "infobox": infobox_data,
        "intro": intro_text,
        "raw_text": raw_text,
        "raw_wikitext": remaining_text,
        "sections": sections,
        "transclusions": transclusions,
    }


def parse_wiki_infobox(wikitext: str, *, site: str | None = None) -> Dict[str, str]:
    """兼容旧接口：仅返回信息框字段。"""
    payload = parse_wiki_page(wikitext, site=site)
    return payload.get("infobox", {})  # type: ignore[return-value]


def wiki_page_to_markdown(
    title: str, page: Dict[str, str | Dict[str, str] | list[dict[str, str]] | list[str]]
) -> str:
    heading = title.strip() if title else "Wiki Page"
    lines = [f"# {heading}"]
    intro = page.get("intro", "")
    if intro:
        lines.extend(["", "## Intro", str(intro)])
    infobox = page.get("infobox", {})
    lines.extend(["", "## Infobox"])
    if isinstance(infobox, dict) and infobox:
        lines.extend(["| Key | Value |", "| --- | --- |"])
        for key, value in infobox.items():
            safe_value = str(value).replace("\n", "<br>")
            lines.append(f"| {key} | {safe_value} |")
    else:
        lines.append("_No infobox fields found._")
    raw_text = page.get("raw_text", "")
    if raw_text:
        lines.append("")
        lines.append("## Body")
        sections = page.get("sections", [])
        if isinstance(sections, list) and sections:
            for section in sections:
                if not isinstance(section, dict):
                    continue
                section_heading = section.get("heading", "section")
                section_content = section.get("content", "")
                if section_heading and section_heading != "intro":
                    lines.append(f"### {section_heading}")
                if section_content:
                    lines.append(str(section_content))
                    lines.append("")
        else:
            lines.append(str(raw_text))
    transclusions = page.get("transclusions", [])
    if isinstance(transclusions, list) and transclusions:
        lines.append("## Transclusions")
        for title in transclusions:
            lines.append(f"- {title}")
    return "\n".join(lines)


def wiki_page_to_llm_markdown(
    title: str,
    page: Dict[str, str | Dict[str, str] | list[dict[str, str]] | list[str]],
    *,
    site: str | None = None,
) -> str:
    heading = title.strip() if title else "Wiki Page"
    lines = [f"# {heading}"]
    infobox = page.get("infobox", {})
    if isinstance(infobox, dict) and infobox:
        lines.extend(["", "## Infobox"])
        for key, value in infobox.items():
            safe_value = str(value).replace("\n", " ")
            lines.append(f"- **{key}**: {safe_value}")
    raw_wikitext = page.get("raw_wikitext", "")
    if raw_wikitext:
        cleaned = clean_wikitext_for_llm(str(raw_wikitext), site=site)
        if cleaned:
            lines.extend(["", "## Body", cleaned])
    transclusions = page.get("transclusions", [])
    if isinstance(transclusions, list) and transclusions:
        lines.append("")
        lines.append("## Transclusions")
        for title in transclusions:
            lines.append(f"- {title}")
    return "\n".join(lines)


if __name__ == "__main__":
    raw_api_text_moegirl = """
{{Umamusumetop}}
{{赛马娘角色信息2
|主印象色=#3376D2
|中文名=东海帝王
|日文名=トウカイテイオー
|图片=92042198 p0.jpg
|声优=Machico
|身高=150
|三围=B77 W54 H76
|生日=4/20
|萌点=[[马娘]]、[[兽耳]]
|简介=这是第一行。
这是第二行。
这是第三行。
}}
'''东海帝王'''是[[Cygames]]制作的...
== 生平 ==
出生于北海道...
"""

    clean_data = parse_wiki_page(raw_api_text_moegirl, site="moegirl")
    print("⬇️ 清洗后的结构化数据 ⬇️")
    print(json.dumps(clean_data, indent=4, ensure_ascii=False))
