"""Export one Tokai Teio sample per source for manual content inspection."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from umamusume_web_crawler.config import config
from umamusume_web_crawler.web.umapyoi import (
    fetch_umapyoi_character,
    fetch_umapyoi_resources,
)
from umamusume_web_crawler.web.wiki_pages import fetch_wiki_page

SAMPLES = {
    "biligame": "东海帝皇",
    "moegirl": "东海帝王",
    "umamusu": "Tokai_Teio",
    "wikiru": "トウカイテイオー",
    "umapyoi": "1003",
}


def json_section(title: str, payload: dict) -> str:
    return f"## {title}\n\n````json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n````\n"


async def export(args: argparse.Namespace) -> int:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    use_proxy = False if args.no_proxy else True if args.use_proxy else None
    failures = 0
    sites = SAMPLES if args.site == "all" else [args.site]
    for site in sites:
        target = args.output_dir / f"{site}.md"
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        metadata = f"> 导出时间：{timestamp}；缓存模式：{'本次独立缓存' if args.fresh else '允许复用有效缓存'}。\n\n"
        try:
            partial = False
            if site == "umapyoi":
                profile = await fetch_umapyoi_character(1003, use_proxy=use_proxy)
                resources = await fetch_umapyoi_resources(1003, use_proxy=use_proxy)
                partial = resources["partial"]
                content = (
                    "# Tokai Teio / トウカイテイオー — Umapyoi\n\n"
                    f"来源：{profile['source_url']}\n\n"
                    "此站返回 JSON，以下保留档案及资源索引的完整字段，没有模型总结或翻译。"
                    "资源链接未验证，也未下载文件。\n\n"
                    + ("**部分资源接口失败，详见 errors。**\n\n" if partial else "")
                    + json_section("结构化档案", profile) + "\n"
                    + json_section("衣装、支援卡与图片资源索引", resources)
                )
            else:
                page = await fetch_wiki_page(SAMPLES[site], site=site, use_proxy=use_proxy)
                content = page["markdown"]
            target.write_text(metadata + content, encoding="utf-8")
            failures += int(partial)
            status = "PARTIAL" if partial else "OK"
            print(f"[{status}] {site}: {len(content):,} chars -> {target}", flush=True)
        except Exception as exc:
            failures += 1
            # Replace an old sample with an explicit failure so a previous success
            # cannot be mistaken for the current fetch result.
            target.write_text(
                metadata + f"# {site} 获取失败\n\n{exc}\n", encoding="utf-8"
            )
            print(f"[ERROR] {site}: {exc} -> {target}", file=sys.stderr, flush=True)
    return int(failures > 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", choices=["all", *SAMPLES], default="all")
    parser.add_argument("--output-dir", type=Path, default=Path("results/test_raw_crawler"))
    parser.add_argument("--fresh", action="store_true", help="Use a new temporary cache for this run")
    proxy = parser.add_mutually_exclusive_group()
    proxy.add_argument("--no-proxy", action="store_true")
    proxy.add_argument("--use-proxy", action="store_true")
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    config.update_from_env()
    previous_cache = os.environ.get("CRAWLER_CACHE_DIR")
    with TemporaryDirectory(prefix="umamusume-samples-") if args.fresh else nullcontext() as cache:
        try:
            if cache is not None:
                os.environ["CRAWLER_CACHE_DIR"] = cache
            code = asyncio.run(export(args))
        finally:
            if previous_cache is None:
                os.environ.pop("CRAWLER_CACHE_DIR", None)
            else:
                os.environ["CRAWLER_CACHE_DIR"] = previous_cache
    raise SystemExit(code)


if __name__ == "__main__":
    main()
