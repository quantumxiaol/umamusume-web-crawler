# Umamusume Web Crawler

围绕 3 个赛马娘 Wiki 的搜索、抓取与部分资源下载工具集：

- `wiki.biligame.com/umamusume`
- `mzh.moegirl.org.cn`
- `umamusu.wiki`

同时保留 Google 搜索能力，以及一套不再作为主流程推荐的视觉抓取方案。

## 当前定位

当前代码的主线能力是：

- 三站 wiki 的标题搜索
- 三站 wiki 的页面抓取与 Markdown 化
- 部分资源下载
  - Biligame：角色音频/图片批量下载
  - umamusu.wiki：分类图片批量下载
- Google 搜索

不再作为主流程推荐的能力：

- Crawl4AI 视觉抓取
- PDF -> MarkItDown 路线
- 通用网页直接抓取

这些能力仍然保留在代码里，但 README 将它们放在“历史方案 / 保留能力”里，不作为默认推荐用法。

## 能力矩阵

| 能力 | Python API | 主 CLI `umamusume-crawler` | MCP `umamusume-mcp` | Skill `skills/umamusume-wiki-crawler` |
| :--- | :--- | :--- | :--- | :--- |
| Google 搜索 | 有 | 无独立入口 | 有 | 无 |
| Biligame 标题搜索 | 有 | 无独立搜索子命令 | 有 | 有 |
| Moegirl 标题搜索 | 有 | 无独立搜索子命令 | 有 | 有 |
| umamusu.wiki 标题搜索 | 有 | 无独立搜索子命令 | 有 | 有 |
| Biligame 页面抓取 | 有 | 有 | 有 | 有 |
| Moegirl 页面抓取 | 有 | 有 | 有 | 有 |
| umamusu.wiki 页面抓取 | 有 | 有 | 有 | 有 |
| Biligame 角色音频/图片下载 | 有 | 有 | 无 | 无 |
| umamusu.wiki 分类图片下载 | 有 | 无 | 有 | 有 |
| 视觉抓取 | 有 | 有 | 无 | 无 |

补充说明：

- 主 CLI 现在是两个任务：
  - `--task page`：页面抓取
  - `--task biligame-assets`：Biligame 角色音频/图片下载
- skill 目前只封装三站 wiki 搜索/抓取和 `umamusu.wiki` 分类图片下载，不包含 Google 搜索，也不包含 Biligame 角色资源下载。
- MCP 目前包含 Google 搜索、三站 wiki 搜索/抓取、`umamusu.wiki` 分类图片下载，不包含 Biligame 角色资源下载。

## 代码结构

核心文件：

- [src/umamusume_web_crawler/cli.py](/Users/quantumxiaol/Desktop/dev/umamusume-web-crawler/src/umamusume_web_crawler/cli.py:1)
  主 CLI 入口。支持页面抓取和 `biligame-assets` 两类任务。
- [src/umamusume_web_crawler/mcp/server.py](/Users/quantumxiaol/Desktop/dev/umamusume-web-crawler/src/umamusume_web_crawler/mcp/server.py:1)
  MCP 服务与工具定义。
- [src/umamusume_web_crawler/web/biligame.py](/Users/quantumxiaol/Desktop/dev/umamusume-web-crawler/src/umamusume_web_crawler/web/biligame.py:1)
  Biligame MediaWiki API 访问。
- [src/umamusume_web_crawler/web/moegirl.py](/Users/quantumxiaol/Desktop/dev/umamusume-web-crawler/src/umamusume_web_crawler/web/moegirl.py:1)
  Moegirl API 访问。
- [src/umamusume_web_crawler/web/umamusu_wiki.py](/Users/quantumxiaol/Desktop/dev/umamusume-web-crawler/src/umamusume_web_crawler/web/umamusu_wiki.py:1)
  `umamusu.wiki` 搜索、抓取、分类图片下载。
- [src/umamusume_web_crawler/web/biligame_assets.py](/Users/quantumxiaol/Desktop/dev/umamusume-web-crawler/src/umamusume_web_crawler/web/biligame_assets.py:1)
  Biligame 角色音频/图片批量下载。
- [src/umamusume_web_crawler/web/search.py](/Users/quantumxiaol/Desktop/dev/umamusume-web-crawler/src/umamusume_web_crawler/web/search.py:1)
  Google 搜索封装。
- [skills/umamusume-wiki-crawler/skill.md](/Users/quantumxiaol/Desktop/dev/umamusume-web-crawler/skills/umamusume-wiki-crawler/skill.md:1)
  skill 说明。
- [skills/umamusume-wiki-crawler/scripts/crawl.py](/Users/quantumxiaol/Desktop/dev/umamusume-web-crawler/skills/umamusume-wiki-crawler/scripts/crawl.py:1)
  skill 使用的 CLI 包装器。

包装入口：

- `python main.py`
- `python mcpserver.py`
- `umamusume-crawler`
- `umamusume-mcp`

## 安装与环境

```bash
uv lock
uv sync
source .venv/bin/activate
playwright install
```

环境变量：

- `GOOGLE_API_KEY`
- `GOOGLE_CSE_ID`
- `HTTP_PROXY` / `HTTPS_PROXY`
- `CRAWLER_TIMEOUT_S`
- `CRAWLER_USER_DATA_DIR`

说明：

- `GOOGLE_API_KEY` / `GOOGLE_CSE_ID` 只在 Google 搜索相关能力中需要。
- 三站 wiki 的 API 抓取本身不依赖 Google。
- `main.py` 与 `mcpserver.py` 会自动尝试加载当前目录 `.env`。
- 作为 Python 库调用时，不会自动读取 `.env`，请自行 `load_dotenv()` 或直接传环境变量。

## Python API

### 1. 三站 wiki 搜索与抓取

```python
from umamusume_web_crawler.web.biligame import (
    search_biligame_titles,
    fetch_biligame_wikitext_expanded,
)
from umamusume_web_crawler.web.moegirl import (
    search_moegirl_titles,
    fetch_moegirl_wikitext_expanded,
)
from umamusume_web_crawler.web.umamusu_wiki import (
    search_umamusu_titles,
    fetch_umamusu_wikitext_expanded,
)
from umamusume_web_crawler.web.parse_wiki_infobox import (
    parse_wiki_page,
    wiki_page_to_llm_markdown,
)

titles = await search_biligame_titles("东海帝皇")
target = titles[0]
wikitext = await fetch_biligame_wikitext_expanded(target, max_depth=1, max_pages=5)
page = parse_wiki_page(wikitext, site="biligame")
markdown = wiki_page_to_llm_markdown(target, page, site="biligame")
```

同理可替换为：

- `search_moegirl_titles` + `fetch_moegirl_wikitext_expanded`
- `search_umamusu_titles` + `fetch_umamusu_wikitext_expanded`

### 2. Biligame 角色音频/图片下载

```python
from umamusume_web_crawler.web.biligame_assets import (
    crawl_biligame_character_assets,
    load_characters_from_json,
)

targets = {"特别周": "Special Week", "东海帝皇": "Tokai Teio"}

summary = await crawl_biligame_character_assets(
    targets,
    audio_output_root="results/voicedata",
    image_output_root="results/imagedata/characters",
    request_delay=0.2,
    page_delay=0.5,
    concurrency=4,
)

# 或从 json 读取
targets = load_characters_from_json("umamusume_characters.json")
```

默认目录结构：

- `results/voicedata/<English Name>/...`
- `results/imagedata/characters/<English Name>/...`

### 3. umamusu.wiki 分类图片下载

```python
from umamusume_web_crawler.web.umamusu_wiki import download_umamusu_category_images

downloads = await download_umamusu_category_images(
    "Category:Game_Backgrounds",
    output_dir="results/umamusu/backgrounds",
    delay_s=0.5,
    max_files=10,
)
```

### 4. Google 搜索

```python
from umamusume_web_crawler.web.search import (
    google_search_urls,
    google_search_page_urls,
)

results = google_search_urls("爱慕织姬 site:wiki.biligame.com/umamusume", num=5)

# Google API 不可用时，可退化为结果页解析
fallback = google_search_page_urls(
    "爱慕织姬 site:mzh.moegirl.org.cn",
    num=5,
    use_proxy=True,
)
```

## 主 CLI

主 CLI 命令：

```bash
umamusume-crawler ...
# 或
python main.py ...
```

### 1. 页面抓取

默认任务是 `--task page`，用于三站 wiki 页面抓取。

示例：

```bash
umamusume-crawler \
  --url "https://wiki.biligame.com/umamusume/东海帝皇"

umamusume-crawler \
  --url "https://mzh.moegirl.org.cn/东海帝王" \
  --mode moegirl

umamusume-crawler \
  --url "https://umamusu.wiki/List_of_Characters" \
  --mode umamusu
```

输出：

- 默认写入 `results/crawl.md`
- 可通过 `--output -` 输出到 stdout

相关参数：

- `--url`
- `--mode auto|biligame|moegirl|umamusu|generic`
- `--output`
- `--use-proxy` / `--no-proxy`

### 2. Biligame 角色资源下载

`--task biligame-assets` 用于批量下载 Biligame 角色音频和图片。

示例：

```bash
# 按默认 umamusume_characters.json 批量抓取
umamusume-crawler \
  --task biligame-assets

# 单角色，只抓图片
umamusume-crawler \
  --task biligame-assets \
  --character 特别周 \
  --name "Special Week" \
  --skip-audio

# 自定义输出目录
umamusume-crawler \
  --task biligame-assets \
  --audio-output data/voices \
  --image-output data/images \
  --asset-summary-output results/biligame_assets.json
```

默认输出目录：

- `results/voicedata/<角色>/`
- `results/imagedata/characters/<角色>/`

相关参数：

- `--audio-output`
- `--image-output`
- `--skip-audio`
- `--skip-images`
- `--character`
- `--name`
- `--characters-json`
- `--dump-html`
- `--request-delay`
- `--page-delay`
- `--concurrency`
- `--asset-summary-output`

### 主 CLI 不包含的能力

当前主 CLI 没有独立子命令去做：

- 三站 wiki 标题搜索
- Google 搜索
- `umamusu.wiki` 分类图片下载

这些能力在 Python API、MCP 或 skill 中可用。

## MCP

启动：

```bash
umamusume-mcp --http -p 7777
# 或
python mcpserver.py --http -p 7777
```

当前 MCP 工具：

- `web_search_google(query)`
- `crawl_google_page(query, num?, use_proxy?)`
- `biligame_wiki_seaech(keyword, limit?, use_proxy?)`
- `moegirl_wiki_search(keyword, limit?, use_proxy?)`
- `umamusu_wiki_search(keyword, limit?, use_proxy?)`
- `crawl_biligame_wiki(url, max_depth?, max_pages?, use_proxy?)`
- `crawl_moegirl_wiki(url, max_depth?, max_pages?, use_proxy?)`
- `crawl_umamusu_wiki(url, max_depth?, max_pages?, use_proxy?)`
- `download_umamusu_category_images(category, output_dir?, max_files?, delay_s?, use_proxy?)`

说明：

- MCP 目前不暴露 Biligame 角色音频/图片下载。
- MCP 目前不暴露视觉抓取。
- `biligame_wiki_seaech` 保留了当前代码中的拼写，调用时需要按这个名字写。

调用示例：

```json
{
  "tool": "crawl_umamusu_wiki",
  "args": {
    "url": "https://umamusu.wiki/List_of_Characters",
    "max_depth": 1,
    "max_pages": 5,
    "use_proxy": false
  }
}
```

## Skill

当前 skill：

- [skills/umamusume-wiki-crawler/skill.md](/Users/quantumxiaol/Desktop/dev/umamusume-web-crawler/skills/umamusume-wiki-crawler/skill.md:1)

统一入口：

```bash
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py <tool> [args]
```

当前 skill 子命令：

- `biligame_wiki_search`
- `moegirl_wiki_search`
- `umamusu_wiki_search`
- `crawl_biligame_wiki`
- `crawl_moegirl_wiki`
- `crawl_umamusu_wiki`
- `download_umamusu_category_images`

说明：

- skill 没有 Google 搜索
- skill 没有 Biligame 角色音频/图片下载
- skill 主要面向“先搜索，再抓取，再回答”的 agent 工作流

示例：

```bash
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py \
  biligame_wiki_search "东海帝皇" --limit 5

uv run python skills/umamusume-wiki-crawler/scripts/crawl.py \
  crawl_umamusu_wiki "https://umamusu.wiki/List_of_Characters"

uv run python skills/umamusume-wiki-crawler/scripts/crawl.py \
  download_umamusu_category_images "Category:Game_Backgrounds" \
  --output-dir results/umamusu/backgrounds
```

## 推荐主流程

当前推荐使用顺序：

1. 三站 wiki 内容查询：优先走 MediaWiki API 搜索 + 抓取
2. Biligame 角色资源：走 `biligame-assets`
3. `umamusu.wiki` 分类资源：走分类图片下载
4. 只有在 API 路径不满足时，才考虑视觉抓取

站点建议：

- 游戏数值、技能、支援卡、育成事件：Biligame
- 背景、梗、人物经历、历史原型：Moegirl
- 英文社区整理页、总表、分类图库：umamusu.wiki

## 历史方案 / 保留能力

项目里仍然保留了一套视觉抓取链路：

- `crawl_biligame_page_visual_markitdown`
- `crawl_moegirl_page_visual_markitdown`
- `crawl_page_visual_markitdown`
- 以及对应的 PDF/PNG capture 函数

这些函数仍可调用，也仍可通过主 CLI 的 `--visual` 触发，但它们现在更适合被看作：

- 历史探索结果
- 兼容保留能力
- API 路径失效时的备用方案

而不是当前推荐主流程。

保留这部分的原因：

- 过去曾用于解决 Bwiki / 萌百复杂页面排版还原问题
- 某些特殊页面视觉抓取仍可能比 API 更完整
- 相关测试与代码仍然存在，删除成本高于保留成本

示例：

```bash
umamusume-crawler \
  --url "https://wiki.biligame.com/umamusume/东海帝皇" \
  --visual
```

## 测试

部分相关测试：

- `tests/test_biligame_assets.py`
- `tests/test_biligame_crawler.py`
- `tests/test_moegirl_crawler.py`
- `tests/test_umamusu_wiki.py`
- `tests/test_search_title.py`
- `tests/test_mcp_tool_crawler_biligame.py`
- `tests/test_mcp_tool_crawler_moegirl.py`
- `tests/test_visual_capture_pdf.py`

运行示例：

```bash
uv run pytest tests/test_biligame_assets.py
uv run pytest tests/test_umamusu_wiki.py
uv run pytest tests/test_cli_config.py
```

如需测试 MCP，先启动服务：

```bash
python mcpserver.py --http -p 7777
```

## 备注

当前 README 以“代码现状”为准，而不是以早期探索方向为准。

如果后续你把以下能力补进来，也应该同步更新矩阵：

- 主 CLI 的 wiki 搜索入口
- 主 CLI 的 `umamusu.wiki` 分类下载
- MCP 的 Biligame 角色音频/图片下载
- skill 的 Google 搜索或 Biligame 资源下载
