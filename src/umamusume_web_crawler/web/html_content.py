"""Render article HTML without discarding folded tables or generated dialogue."""

from __future__ import annotations

import re
from copy import copy
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from .http import SourceError


def _clean(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", value).strip()


class HtmlRenderer:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def children(self, node: Tag) -> str:
        return "".join(self.render(child) for child in node.children)

    def render(self, node) -> str:
        if isinstance(node, Comment):
            return ""
        if isinstance(node, NavigableString):
            return re.sub(r"\s+", " ", str(node))
        if not isinstance(node, Tag):
            return ""
        name = node.name
        if name in {"script", "style", "form", "input", "button", "iframe", "noscript"}:
            return ""
        if name == "br":
            return "\n"
        if name == "img":
            return node.get("alt", "")
        if name == "table":
            return self.table_markdown(node)
        text = self.children(node)
        if name == "a":
            href = urljoin(self.base_url, node.get("href", ""))
            if text.strip() and urlparse(href).scheme in {"http", "https"}:
                return f"[{text.strip()}]({href})"
            return text
        if re.fullmatch(r"h[1-6]", name):
            return "\n\n" + "#" * max(2, int(name[1])) + " " + text.strip() + "\n\n"
        if name in {"b", "strong"}:
            return f"**{text.strip()}**" if text.strip() else ""
        if name in {"i", "em"}:
            return f"*{text.strip()}*" if text.strip() else ""
        if name == "li":
            return "\n- " + text.strip() + "\n"
        if name == "pre":
            fence = chr(96) * 3
            return f"\n\n{fence}\n{node.get_text()}\n{fence}\n\n"
        for cls, label in (("voice_text_jp", "日文"), ("voice_text_chs", "简中"),
                           ("voice_text_cht", "繁中")):
            if cls in node.get("class", []):
                return f"\n{label}：{text.strip()}\n"
        if name in {"p", "div", "section", "ul", "ol", "dl", "dt", "dd", "details", "summary"}:
            return "\n" + text.strip() + "\n" if text.strip() else ""
        return text

    def table_rows(self, table: Tag) -> list[list[str]]:
        rows = [row for row in table.find_all("tr") if row.find_parent("table") is table]
        grid: dict[tuple[int, int], str] = {}
        for r, row in enumerate(rows):
            col = 0
            for cell in row.find_all(["th", "td"], recursive=False):
                while (r, col) in grid:
                    col += 1
                text = _clean(self.children(cell))
                try:
                    rowspan = max(1, min(int(cell.get("rowspan", 1)), len(rows) - r))
                    colspan = max(1, min(int(cell.get("colspan", 1)), 64))
                except (TypeError, ValueError):
                    rowspan = colspan = 1
                for dr in range(rowspan):
                    for dc in range(colspan):
                        grid[r + dr, col + dc] = text
                col += colspan
        width = max((c + 1 for _, c in grid), default=0)
        return [[grid.get((r, c), "") for c in range(width)] for r in range(len(rows))]

    def table_markdown(self, table: Tag) -> str:
        rows = self.table_rows(table)
        if not rows or not rows[0]:
            return self.children(table)
        if not any(cell.strip() for row in rows for cell in row):
            return ""
        width = len(rows[0])
        # Neutral headers retain the original first row, including multi-row headers.
        lines = ["| " + " | ".join(f"列{i + 1}" for i in range(width)) + " |",
                 "| " + " | ".join("---" for _ in range(width)) + " |"]
        for row in rows:
            cells = [re.sub(r"\s*\n\s*", "<br>", c).replace("|", "&#124;") for c in row]
            lines.append("| " + " | ".join(cells) + " |")
        caption = table.find("caption", recursive=False)
        prefix = self.children(caption) + "\n\n" if caption else ""
        return "\n\n" + prefix + "\n".join(lines) + "\n\n"


def _remove_from_heading(heading: Tag, root: Tag) -> None:
    # PukiWiki's imperfect markup can nest the comment heading several divs deep.
    current = heading
    while current is not root:
        for sibling in list(current.next_siblings):
            sibling.extract()
        parent = current.parent
        if current is heading:
            current.extract()
        current = parent
        if current is None:
            break


def content_root(html: str, site: str) -> Tag:
    soup = BeautifulSoup(html, "lxml")
    if soup.select_one(".noarticletext"):
        raise SourceError("Wiki article does not exist.")
    root = soup.select_one("#body" if site == "wikiru" else ".mw-parser-output")
    if root is None:
        raise SourceError("Article body missing; source may have returned an access page.")
    # Moegirl embeds the article inside a template element; reparsing restores
    # normal text nodes that BeautifulSoup otherwise excludes from get_text().
    root = BeautifulSoup(str(root), "lxml").select_one("#body" if site == "wikiru" else ".mw-parser-output")
    if site == "wikiru":
        if not root.select("h2, h3, table"):
            raise SourceError("Invalid or missing wikiru article.")
        for heading in root.find_all(["h2", "h3"]):
            if "コメントフォーム" in heading.get_text():
                _remove_from_heading(heading, root)
                break
        # PukiWiki keeps article footnotes outside #body. Include only notes
        # referenced by the retained article, not those from deleted comments.
        references = {urlparse(link.get("href", "")).fragment for link in root.select("a[href]")}
        notes = soup.select_one("#note")
        if notes is not None:
            selected = [anchor for anchor in notes.select("a[id]") if anchor["id"] in references]
            if selected:
                heading = soup.new_tag("h2")
                heading.string = "注釈"
                root.append(heading)
                for anchor in selected:
                    paragraph = soup.new_tag("p")
                    paragraph.append(copy(anchor))
                    for sibling in anchor.next_siblings:
                        if isinstance(sibling, Tag) and (sibling.name == "br" or sibling.get("id", "").startswith("notefoot_")):
                            break
                        paragraph.append(copy(sibling))
                    root.append(paragraph)
    for node in list(root.select("script, style, form, iframe, .mw-editsection, .navbox, .toc, #toc, .contents, .jumpmenu, .anchor_super, .mw-indicators")):
        node.decompose()
    if not root.get_text(strip=True):
        raise SourceError("Article body is empty.")
    return root


_FIELD_NAMES = {name.casefold() for name in (
    "中文名", "日文名", "昵称", "生日", "身高", "体重", "三围", "声优", "CV", "姓名",
    "名前", "誕生日", "身長", "スリーサイズ", "所属寮", "学年", "得意なこと", "苦手なこと",
    "耳のこと", "尻尾のこと", "家族のこと", "靴のサイズ", "キャッチコピー", "Name", "Japanese Name",
    "Birthday", "Height", "Weight", "Three Sizes", "Dorm", "Roommate", "Class", "Voice Actor",
)}


def parse_html_page(html: str, *, title: str, source_url: str, site: str) -> dict:
    root = content_root(html, site)
    renderer = HtmlRenderer(source_url)
    fields: dict[str, str] = {}
    for table in root.find_all("table"):
        rows = renderer.table_rows(table)
        html_rows = [row for row in table.find_all("tr") if row.find_parent("table") is table]
        for index, row in enumerate(rows):
            labels = [re.sub(r"[*\s]+", " ", cell).strip().rstrip("：:") for cell in row]
            known = [i for i, label in enumerate(labels) if label.casefold() in _FIELD_NAMES]
            cells = html_rows[index].find_all(["th", "td"], recursive=False)
            header_row = cells and all(cell.name == "th" for cell in cells)
            if header_row and index + 1 < len(rows):
                for i in known:
                    if rows[index + 1][i]:
                        fields.setdefault(labels[i], rows[index + 1][i])
            elif len(known) == 1:
                i = known[0]
                values = list(dict.fromkeys(c for c in row[i + 1:] if c))
                if values:
                    fields.setdefault(labels[i], " / ".join(values))
    body = _clean(renderer.children(root))
    return {"title": title, "source_url": source_url, "source_format": "rendered_html",
            "infobox": fields, "markdown": f"# {title}\n\n来源：{source_url}\n\n{body}\n"}
