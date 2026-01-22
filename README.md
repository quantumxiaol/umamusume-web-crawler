# Umamusume Web Crawler

提供 Web MCP 搜索/抓取工具与本地 CLI，将网页内容整理为 Markdown。

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

## 使用与参数传递

Python API（最灵活）：

```python
from pathlib import Path
from umamusume_web_crawler.web.crawler import (
    crawl_biligame_page_visual_markitdown,
    crawl_biligame_page_visual,
    crawl_moegirl_page_visual_markitdown,
)

# 视觉抓取 + MarkItDown
content = await crawl_biligame_page_visual_markitdown(
    "https://wiki.biligame.com/umamusume/东海帝皇",
    use_proxy=False,          # 可选，默认跟随环境变量代理
    workspace="data/cache",   # 可选，持久化中间 PDF/PNG
    keep_files=True,          # 可选，保留中间文件
    timeout_s=180,            # 可选，覆盖 CRAWLER_TIMEOUT_S
)

# 只抓取 PDF/PNG（必须显式指定 output_dir）
capture = await crawl_biligame_page_visual(
    "https://wiki.biligame.com/umamusume/东海帝皇",
    output_dir=Path("data/capture"),
    capture_pdf=True,
    pdf_from_png=False,
    print_scale=None,
    headless=False,
)
```

说明：
- `workspace` / `output_dir` 是函数参数，不会自动从环境变量读取；如需用环境变量控制，请在调用方读取后传入。
- `timeout_s` 可单次覆盖；默认值来自 `CRAWLER_TIMEOUT_S`。
- `use_proxy` 为 `None` 时会自动跟随 `HTTP_PROXY/HTTPS_PROXY` 配置。

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
    "use_proxy": true,
    "print_scale": 0.65,
    "headless": false
  }
}
```

## 爬虫流程（现行）

当前默认走“网页渲染 -> PDF -> MarkItDown”的视觉抓取流程，效果比纯 HTML 清洗更稳定：

1) Crawl4AI 以浏览器方式渲染页面，输出 PDF/PNG（可走代理）。
2) 使用 MarkItDown 将 PDF 转成 Markdown 文本。
3) MCP 工具 `crawl_biligame_wiki` / `crawl_moegirl_wiki` 返回这份 Markdown 作为抓取结果。

说明：
- 萌娘百科默认 `print_scale=0.65`，用于避免 PDF 被裁切。
- 萌娘百科对 headless 更敏感，默认走 headful；CI 可用 `xvfb-run` 或显式 `headless=true`。

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
python tests/test_mcp_tool_crawler.py -u http://127.0.0.1:7777/mcp/
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
