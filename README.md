# Umamusume Web Crawler

提供 Web MCP 搜索/抓取工具与本地 CLI，将网页内容整理为 Markdown。

## 项目总结

- 核心能力：站内搜索 + MediaWiki API 抓取 + 视觉抓取（Crawl4AI → PDF → MarkItDown）
- 目标站点：Bilibili Wiki / 萌娘百科 + 通用网页
- 运行形态：本地 CLI、Python 包调用、MCP 服务
- 主要特性：可选代理、超时控制、中间文件持久化、可展开 Transclusion 子页面

## 项目结构

```
umamusume-web-crawler/
|-- src/
|   |-- umamusume_web_crawler/
|   |   |-- __init__.py                  # 包入口
|   |   |-- cli.py                       # CLI 入口
|   |   |-- config.py                    # 环境变量配置
|   |   |-- mcp/
|   |   |   |-- __init__.py              # MCP 包入口
|   |   |   |-- server.py                # Web MCP 服务（搜索 + 抓取工具）
|   |   |-- web/
|   |   |   |-- __init__.py              # Web 子模块入口
|   |   |   |-- crawler.py               # Crawl4AI 抓取封装
|   |   |   |-- biligame.py              # Bilibili Wiki API 访问
|   |   |   |-- moegirl.py               # 萌娘百科 API 访问
|   |   |   |-- parse_wiki_infobox.py    # Wiki 解析与 Markdown 渲染
|   |   |   |-- process.py               # MarkItDown 转换封装
|   |   |   |-- search.py                # Google 搜索封装
|   |   |   |-- smart_split.py           # 分段工具
|-- tests/
|   |-- test_biligame_crawler.py         # Bilibili Wiki 抓取测试
|   |-- test_crawler.py                  # 通用爬虫测试
|   |-- test_google.py                   # Google 搜索测试
|   |-- test_mcp_tool_crawler.py         # MCP 抓取工具测试
|   |-- test_mcp_tool_crawler_moegirl.py # MCP 萌娘百科抓取测试
|   |-- test_mcp_tool_google.py          # MCP 搜索工具测试
|   |-- test_moegirl_crawler.py          # 萌娘百科抓取测试
|   |-- test_search_title.py             # 站内搜索测试
|   |-- test_visual_capture_pdf.py       # 视觉抓取 PDF/PNG
|-- .env.example                         # 环境变量模板
|-- main.py                              # CLI 入口
|-- mcpserver.py                         # MCP 入口
|-- pytest.ini                           # pytest 配置
|-- README.md                            # 说明文档
|-- examples/
|-- results/
```

## 环境

使用 uv 管理环境。

```bash
uv lock
uv sync
source .venv/bin/activate
playwright install

cat .env.example > .env
```

在 `.env` 中设置：
- `GOOGLE_API_KEY`
- `GOOGLE_CSE_ID`
- `HTTP_PROXY` / `HTTPS_PROXY`（可选，如访问 google、萌娘百科需要代理时再设置；未设置则直接访问）
- `CRAWLER_TIMEOUT_S`（可选，单次爬取超时秒数，默认 300）
- `CRAWLER_USER_DATA_DIR`（可选，持久化浏览器 profile 目录，用于绕过首次验证/WAF）

说明：作为库使用时不会自动读取 `.env`。请在调用方应用中自行加载环境变量（例如使用 `python-dotenv`），
或直接在系统环境中设置；`python main.py` / `python mcpserver.py` 会自动尝试加载当前目录下的 `.env`。

请在 [Google Cloud 凭证控制台](https://console.cloud.google.com/apis/credentials)中创建GOOGLE_API_KEY，并使用[可编程搜索引擎](https://programmablesearchengine.google.com/controlpanel/create)创建GOOGLE_CSE_ID。

如果你在另一个项目中调用本包，可以用两种方式更新配置：

```python
from umamusume_web_crawler.config import config

# 方式 1：在调用前设置环境变量，然后刷新
config.update_from_env()

# 方式 2：直接覆盖配置（优先级最高）
config.apply_overrides(crawler_timeout_s=180, http_proxy="http://127.0.0.1:7890")
```

## 使用与参数传递（API 优先）

默认推荐走 MediaWiki API（更稳定、无需视觉渲染），用法可直接参考：
- `tests/test_biligame_crawler.py`
- `tests/test_moegirl_crawler.py`

Python API（站内搜索 → 拉取 wikitext → 展开子页面 → 清洗成 Markdown）：

```python
from umamusume_web_crawler.web.moegirl import (
    fetch_moegirl_wikitext_expanded,
    search_moegirl_titles,
)
from umamusume_web_crawler.web.biligame import (
    fetch_biligame_wikitext_expanded,
    search_biligame_titles,
)
from umamusume_web_crawler.web.parse_wiki_infobox import (
    parse_wiki_page,
    wiki_page_to_llm_markdown,
)

# 萌娘百科：搜索标题 → 拉取 wikitext → 展开子页面 → Markdown
titles = await search_moegirl_titles("东海帝王")
target = titles[0] if titles else "东海帝王"
wikitext = await fetch_moegirl_wikitext_expanded(
    target, max_depth=1, max_pages=5
)
page = parse_wiki_page(wikitext, site="moegirl")
md = wiki_page_to_llm_markdown(target, page, site="moegirl")

# Bilibili Wiki：搜索标题 → 拉取 wikitext → 展开子页面 → Markdown
titles = await search_biligame_titles("东海帝皇")
target = titles[0] if titles else "东海帝皇"
wikitext = await fetch_biligame_wikitext_expanded(
    target, max_depth=1, max_pages=5
)
page = parse_wiki_page(wikitext, site="biligame")
md = wiki_page_to_llm_markdown(target, page, site="biligame")
```

说明：
- `workspace` / `output_dir` 是函数参数，不会自动从环境变量读取；如需用环境变量控制，请在调用方读取后传入。
- `timeout_s` 可单次覆盖；默认值来自 `CRAWLER_TIMEOUT_S`。
- `use_proxy` 为 `None` 时会自动跟随 `HTTP_PROXY/HTTPS_PROXY` 配置。
- `CRAWLER_USER_DATA_DIR` 会启用持久化浏览器 profile（复用 Cookie/会话）。
- MediaWiki API 模块也支持 `use_proxy` 参数；萌娘百科直连即可访问时可不启用代理。

如需走“视觉抓取”（Crawl4AI → PDF → MarkItDown），参考旧方案：
```python
from pathlib import Path
from umamusume_web_crawler.web.crawler import (
    crawl_biligame_page_visual_markitdown,
    crawl_biligame_page_visual,
)

content = await crawl_biligame_page_visual_markitdown(
    "https://wiki.biligame.com/umamusume/东海帝皇",
    use_proxy=False,
    workspace="data/cache",
    keep_files=True,
    timeout_s=180,
)

capture = await crawl_biligame_page_visual(
    "https://wiki.biligame.com/umamusume/东海帝皇",
    output_dir=Path("data/capture"),
    capture_pdf=True,
    pdf_from_png=False,
    print_scale=None,
    headless=False,
)
```

CLI 参数：
- `--mode`（auto/biligame/moegirl/generic）
- `--visual`（启用 PDF -> MarkItDown 视觉抓取）
- `--visual-dir`（视觉抓取输出目录）
- `--output`（输出 Markdown 路径，`-` 为 stdout）
- `--use-proxy` / `--no-proxy`
- `--print-scale`（萌娘百科视觉抓取缩放）
- `--headless`（视觉抓取 headless 模式）
- `--capture-pdf` / `--no-capture-pdf`

MCP 工具参数（示例）：

```json
{
  "tool": "crawl_moegirl_wiki",
  "args": {
    "url": "https://mzh.moegirl.org.cn/东海帝王",
    "max_depth": 1,
    "max_pages": 5,
    "use_proxy": true
  }
}
```

```json
{
  "tool": "crawl_biligame_wiki",
  "args": {
    "url": "https://wiki.biligame.com/umamusume/东海帝皇",
    "max_depth": 1,
    "max_pages": 5,
    "use_proxy": false
  }
}
```

与测试脚本一致的 MCP 调用方式（可直接运行）：
- `python tests/test_mcp_tool_crawler_biligame.py -u http://127.0.0.1:7777/mcp/`
- `python tests/test_mcp_tool_crawler_moegirl.py -u http://127.0.0.1:7777/mcp/`
## 运行结果

```
tests/test_biligame_crawler.py Search results for '东海帝皇': ['东海帝皇', '东海帝皇/ボクの武器', '东海帝皇/ボクのやり方', '东海帝皇/伝説のひと幕', '东海帝皇/ゴシップ狂想曲']
Wrote 9994 chars to results/test/biligame_api.md
TEST_RESULT: PASSED
tests/test_moegirl_crawler.py Search results for '东海帝王': ['东海帝王']
Wrote 58140 chars to results/test/moegirl_api.md
TEST_RESULT: PASSED
```

使用API可以返回。

## 爬虫流程（现行）

当前 MCP 默认走 MediaWiki API 抓取，再做结构化清洗输出 Markdown：

1) 调用 Wiki API 拉取 wikitext。
2) 解析 infobox/sections/transclusion 并转成 Markdown（可选 LLM 友好渲染）。
3) MCP 工具 `crawl_biligame_wiki` / `crawl_moegirl_wiki` 返回 Markdown。

说明：
- 视觉抓取方案仍保留，可通过 CLI `--visual` 或 Python API 调用。
- Bwiki/萌娘百科可通过 `fetch_*_wikitext_expanded` 展开子页面，提升内容完整度。

## 探索经过（简述）

- 尝试过 HTML 清洗与结构化提取（去脚本、过滤噪声、分块等），但 Bwiki 页面噪声与动态结构导致效果不稳定。
- 引入 Pruning 抽取后仍有缺失与重复问题。
- 改为“截图成 PDF -> MarkItDown”后，PDF + MarkItDown 的正文提取更完整，作为当前主线路。

## 运行

1) 启动 Web MCP 服务

```bash
python mcpserver.py --http -p 7777
```

2) 本地 CLI 抓取页面

```bash
python main.py --url "https://wiki.biligame.com/umamusume/东海帝皇" --mode biligame
python main.py --url "https://mzh.moegirl.org.cn/东海帝王" --mode moegirl --visual
```

输出会写入 `results/crawl.md`（或使用 `--output` 指定）。

### 方式 3：命令行参数（仅限 CLI）

如果你使用 `umamusume-crawler` 命令行工具，可以直接传递参数：

```bash
umamusume-crawler --url "..." --google-api-key "YOUR_KEY" --google-cse-id "YOUR_ID"
```

## 集成指南（作为依赖库使用）

如果通过 git 或 path 依赖将本包集成到你的项目中（例如使用 `uv`）：

```toml
[tool.uv.sources]
umamusume-web-crawler = { git = "https://github.com/quantumxiaol/umamusume-web-crawler" }
```

**注意**：作为库引用时，它**不会**自动读取你的 `.env`。你需要手动传递配置。

### 推荐做法：在项目入口处注入配置

在你的主程序或初始化模块中（例如 `main.py` 或 `boot.py`）：

```python
from umamusume_web_crawler.config import config as crawler_config

# 假设你从自己的配置系统（如 config.py 或 os.environ）获取了 Key
MY_GOOGLE_API_KEY = "..."
MY_GOOGLE_CSE_ID = "..."

# 方式 1：手动传递值（最稳健）
crawler_config.apply_overrides(
    google_api_key=MY_GOOGLE_API_KEY,
    google_cse_id=MY_GOOGLE_CSE_ID,
    # 可选：如果需要代理
    http_proxy="http://127.0.0.1:7890", 
    https_proxy="http://127.0.0.1:7890",
)

# 方式 2：如果你已经加载了环境变量（例如使用了 python-dotenv）
# crawler_config.update_from_env() 
```

## 在其他项目中使用 MCP 服务（API 优先）

1) 安装依赖（在你的项目中）

```bash
pip install umamusume-web-crawler
```

安装后，你可以直接使用命令行工具启动服务：

```bash
# 自动加载当前目录下的 .env 文件
umamusume-mcp --http -p 7777
```

2) 配置环境变量

你可以创建一个 `.env` 文件，`umamusume-mcp` 和 `umamusume-crawler` 会自动加载它：

```env
GOOGLE_API_KEY=xxx
GOOGLE_CSE_ID=xxx
```

或者在运行命令前设置环境变量：

4) 在你的应用里调用 MCP 工具（示例）

```json
{
  "tool": "crawl_moegirl_wiki",
  "args": {
    "url": "https://mzh.moegirl.org.cn/东海帝王",
    "max_depth": 1,
    "max_pages": 5,
    "use_proxy": true
  }
}
```

可直接参考 MCP 调用测试：
- `tests/test_mcp_tool_crawler_biligame.py`
- `tests/test_mcp_tool_crawler_moegirl.py`

可用工具与参数：
- `web_search_google(query)`
- `crawl_google_page(query, num?, use_proxy?)`
- `biligame_wiki_seaech(keyword, limit?, use_proxy?)`
- `moegirl_wiki_search(keyword, limit?, use_proxy?)`
- `crawl_biligame_wiki(url, max_depth?, max_pages?, use_proxy?)`
- `crawl_moegirl_wiki(url, max_depth?, max_pages?, use_proxy?)`

说明：
- MCP 工具默认使用 API 抓取，不生成中间 PDF/PNG。
- `use_proxy=None` 时会自动跟随 `HTTP_PROXY/HTTPS_PROXY`。

## 中间文件（PDF/PNG）存储

视觉抓取默认使用临时目录并在解析完成后自动清理；如需保留中间产物，请显式传递存储位置。

Python 调用示例：

```python
from pathlib import Path
from umamusume_web_crawler.web.crawler import (
    crawl_biligame_page_visual_markitdown,
    crawl_biligame_page_visual,
)

# 1) 临时目录（默认），解析结束自动清理
content = await crawl_biligame_page_visual_markitdown(
    "https://wiki.biligame.com/umamusume/东海帝皇",
)

# 2) 持久化目录（保留 PDF/PNG）
content = await crawl_biligame_page_visual_markitdown(
    "https://wiki.biligame.com/umamusume/东海帝皇",
    workspace="data/crawl_cache",
    keep_files=True,
)

# 3) 只做抓取并保存文件（必须显式指定位置）
capture = await crawl_biligame_page_visual(
    "https://wiki.biligame.com/umamusume/东海帝皇",
    output_dir=Path("data/crawl_capture"),
)
```

CLI 用法：

```bash
python main.py --visual --visual-dir data/crawl_cache \
  --url "https://wiki.biligame.com/umamusume/东海帝皇"
```

## 测试

运行测试前请先启动 MCP 服务：

```bash
python mcpserver.py --http -p 7777
```

```bash
python tests/test_google.py
python tests/test_crawler.py
python tests/test_biligame_crawler.py
python tests/test_moegirl_crawler.py
python tests/test_search_title.py
python tests/test_mcp_tool_crawler.py -u http://127.0.0.1:7777/mcp/
python tests/test_mcp_tool_crawler_biligame.py -u http://127.0.0.1:7777/mcp/
python tests/test_mcp_tool_crawler_moegirl.py -u http://127.0.0.1:7777/mcp/
python tests/test_mcp_tool_google.py -u http://127.0.0.1:7777/mcp/
```

使用 pytest 运行：

```bash
pytest -q
```

说明：Linux (尤其是 CI) 上可用 `xvfb-run` 包裹 `mcpserver.py` 或 `pytest`；
macOS 本地通常无需 `xvfb-run`。

提示：`pytest -q` 会捕获 stdout，只显示用例结果。
若要查看爬取/ToolCall 的输出，使用 `pytest -s` 或直接运行脚本：

```bash
python tests/test_visual_capture_pdf.py
python tests/test_mcp_tool_crawler.py -u http://127.0.0.1:7777/mcp/
```
