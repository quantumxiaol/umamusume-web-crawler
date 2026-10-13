# 项目说明

## 代码结构

核心文件：

- [src/umamusume_web_crawler/cli.py](src/umamusume_web_crawler/cli.py)
  主 CLI 入口。支持正文、角色索引、资源下载与 Umapyoi JSON 输出。
- [src/umamusume_web_crawler/mcp/server.py](src/umamusume_web_crawler/mcp/server.py)
  MCP 服务与工具定义。
- [src/umamusume_web_crawler/web/biligame.py](src/umamusume_web_crawler/web/biligame.py)
  Biligame MediaWiki API 访问。
- [src/umamusume_web_crawler/web/moegirl.py](src/umamusume_web_crawler/web/moegirl.py)
  Moegirl API 访问。
- [src/umamusume_web_crawler/web/umamusu_wiki.py](src/umamusume_web_crawler/web/umamusu_wiki.py)
  `umamusu.wiki` 搜索、抓取、分类图片下载。
- [src/umamusume_web_crawler/web/biligame_assets.py](src/umamusume_web_crawler/web/biligame_assets.py)
  Biligame 角色音频/图片批量下载。
- [src/umamusume_web_crawler/web/character_index.py](src/umamusume_web_crawler/web/character_index.py)
  官网角色名单与 Biligame 角色/衣装索引合并。
- [src/umamusume_web_crawler/web/search.py](src/umamusume_web_crawler/web/search.py)
  Google 搜索封装。
- [skills/umamusume-wiki-crawler/skill.md](skills/umamusume-wiki-crawler/skill.md)
  skill 说明。
- [skills/umamusume-wiki-crawler/scripts/crawl.py](skills/umamusume-wiki-crawler/scripts/crawl.py)
  skill 使用的 CLI 包装器。

正文主路径：`wiki_pages.py` 选择来源 → `html_content.py` 保留表格/台词 → `web/tools.py` 组装统一结果，MCP 与 skill 只做入口适配。`http.py` 共享代理、项目 UA、磁盘缓存、按主机串行限速与错误处理。`wikiru.py` 读取 PukiWiki，`umapyoi.py` 读取 JSON API。原有 raw/extracts 函数仍保留，默认正文入口不再使用它们。

包装入口：

- `python main.py`
- `python mcpserver.py`
- `umamusume-crawler`
- `umamusume-mcp`

## Python API

### 1. 四站 wiki 搜索与正文

```python
from umamusume_web_crawler.web.tools import search_wiki
from umamusume_web_crawler.web.wiki_pages import fetch_wiki_page

matches = await search_wiki("biligame", "东海帝皇")
page = await fetch_wiki_page(matches["results"][0]["url"])
markdown = page["markdown"]
infobox = page["infobox"]
ja_page = await fetch_wiki_page("トウカイテイオー", site="wikiru")
```

`site` 支持 `biligame`、`moegirl`、`umamusu`、`wikiru`。Bwiki/umamusu 通过 MediaWiki `action=parse` 获取已展开模板的 HTML；萌娘通过公开页面保留 `extracts` 会省略的表格；wikiru 通过公开 HTML 保留折叠台词，去除评论区。台词所在关联子页仍需单独读取。

`infobox` 是常见档案字段的便捷提取，不覆盖所有站点字段；Markdown 保留正文表格。URL 解析保留子页面路径，wikiru 使用 `?日文标题`，不能拼成 `?title=...`。

### Umapyoi 补充数据

```python
from umamusume_web_crawler.web.umapyoi import (
    search_umapyoi_characters, fetch_umapyoi_character, fetch_umapyoi_resources,
)
results = await search_umapyoi_characters("Tokai Teio")
profile = await fetch_umapyoi_character(1003)
resources = await fetch_umapyoi_resources(1003)
```

档案保留 `null` 与 `missing_fields`，使用 `game_id`，保留来源；不自动合并或覆盖 Wiki。搜索支持日文/英文名和游戏 ID，没有中文别名映射。资源返回衣装、支援卡、图片分组及档案内资源 URL。团体支援卡的主 `chara_id` 可能属于其他成员；按接口归属保留。URL 可失效，统一标记 `unverified`，不下载文件。某资源接口失败时返回 `partial: true` 和 `errors`，不把失败误判为零条数据。

### 2. Biligame 角色音频/图片下载

```python
from umamusume_web_crawler.web.biligame_assets import (
    crawl_biligame_character_assets,
    load_asset_targets_from_json,
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

# 或从 schema-v2 索引读取全部衣装页
targets = load_asset_targets_from_json(
    "umamusume_characters.json",
    include_variants=True,
)
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

### 4. Google 搜索（保留代码，默认关闭）

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

默认任务是 `--task page`，用于四站 wiki 正文抓取。

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
- `--mode auto|biligame|moegirl|umamusu|wikiru|generic`
- `--output`
- `--use-proxy` / `--no-proxy`

### Umapyoi 与日文正文命令

```bash
umamusume-crawler --mode wikiru --url "トウカイテイオー" --output results/teio-ja.md
umamusume-crawler --task umapyoi-search --keyword "Tokai Teio" --output -
umamusume-crawler --task umapyoi-character --game-id 1003 --output results/teio-profile.json
umamusume-crawler --task umapyoi-resources --game-id 1003 --output results/teio-resources.json
```

### 2. 更新角色/衣装索引

`umamusume_characters.json` 是 schema-v2 索引，包含：

- 中文名、稳定英文目录名、日文名
- 官网角色 slug 与是否已实装
- Biligame 角色 ID、衣装 ID 和每个 `【…】` / `〖…〗` 页面标题

当前索引以 Biligame 的“赛马娘一览”为已实装与衣装来源，以官方网站为完整角色和标准英文名来源。尚无 Biligame 页面时，中文名由 `character_name_overrides.json` 人工维护。

```bash
umamusume-crawler \
  --task update-character-index \
  --no-proxy
```

更新不会把官网尚未实装的角色误加入下载目标；新角色无法自动匹配中文名时会打印 `[unresolved]`，此时把一条 `"中文名": "Official English Name"` 加到 `character_name_overrides.json` 后重跑。

### 3. Biligame 角色资源下载

`--task biligame-assets` 用于批量下载 Biligame 角色音频和图片。

示例：

```bash
# 按默认索引批量抓取基础角色页
umamusume-crawler \
  --task biligame-assets

# 汇总下载全部角色的所有衣装立绘到各自英文目录
umamusume-crawler \
  --task biligame-assets \
  --skip-audio \
  --include-variants \
  --trust-existing-character-dirs

# 按同一份索引下载已实装角色的基础页音频
umamusume-crawler \
  --task biligame-assets \
  --skip-images

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

跳过规则：

- 每次成功解析图片页后，文件清单写入 `results/imagedata/characters/.biligame_asset_manifest.json`。
- 纯图片模式（`--skip-audio`）下，若 manifest 中的所有文件仍存在，该衣装页会在启动浏览器前直接跳过，因此不会访问角色页。
- 音频下载也使用 schema-v2 JSON，但只抓每名已实装角色的基础页；图片 manifest 不会跳过音频任务。已有音频文件仍会按文件名复用，但为了发现语音条目仍需访问基础角色页。
- 第一次接管旧目录时可加 `--trust-existing-character-dirs`：非空的基础角色目录会直接登记并跳过；换装页仍会逐页补齐。这个选项表示你确认旧目录完整。
- 要主动检查角色页有没有新增图片，使用 `--refresh-existing`；仍会按本地文件名跳过重复下载。

默认限流策略偏保守：图片单并发、每个实际下载至少等待 1.5 秒、角色页之间至少等待 5 秒，并额外加入最多 25% 的随机抖动。普通错误按 5/10 秒退避；检测到 `403`、`429`、`567` 或 rate-limit 文本时按 60/120 秒退避。连续重试仍受限时会中止整批任务，不继续请求后续页面；稍后重跑即可从 manifest 进度续传。

相关参数：

- `--audio-output`
- `--image-output`
- `--skip-audio`
- `--skip-images`
- `--character`
- `--name`
- `--characters-json`
- `--include-variants`（要求同时使用 `--skip-audio`）
- `--asset-manifest`
- `--trust-existing-character-dirs`
- `--refresh-existing`
- `--dump-html`
- `--request-delay`
- `--page-delay`
- `--concurrency`
- `--max-retries`
- `--retry-base-delay`
- `--rate-limit-delay`
- `--delay-jitter`
- `--continue-on-rate-limit`（不推荐）
- `--asset-summary-output`

### 主 CLI 不包含的能力

当前主 CLI 没有独立子命令去做：

- 四站 wiki 标题搜索
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

- `biligame_wiki_search(keyword, limit?, use_proxy?)`（旧拼写 `biligame_wiki_seaech` 保留兼容）
- `moegirl_wiki_search(keyword, limit?, use_proxy?)`
- `umamusu_wiki_search(keyword, limit?, use_proxy?)`
- `crawl_biligame_wiki(url, max_depth?, max_pages?, use_proxy?)`
- `crawl_moegirl_wiki(url, max_depth?, max_pages?, use_proxy?)`
- `crawl_umamusu_wiki(url, max_depth?, max_pages?, use_proxy?)`
- `wikiru_wiki_search(keyword, limit?, use_proxy?)`
- `crawl_wikiru_wiki(url, max_depth?, max_pages?, use_proxy?)`
- `umapyoi_character_search(keyword, limit?, use_proxy?)`
- `get_umapyoi_character(game_id, use_proxy?)`
- `get_umapyoi_resources(game_id, use_proxy?)`
- `download_umamusu_category_images(category, output_dir?, max_files?, delay_s?, use_proxy?)`

说明：

- MCP 目前不暴露 Biligame 角色音频/图片下载。
- MCP 目前不暴露视觉抓取。
- 保留 `web_search_google` / `crawl_google_page` 函数代码，MCP server 不导入、不注册，没有启用开关；skill 不调用 Google。
- 正文工具返回 `status`、Markdown `result`、`infobox`、`source_url`、`source_format` 和 `transport`；失败返回错误，旧 `max_depth/max_pages` 仅兼容接收。

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

- [skills/umamusume-wiki-crawler/skill.md](skills/umamusume-wiki-crawler/skill.md)

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
- `wikiru_wiki_search` / `crawl_wikiru_wiki`
- `umapyoi_character_search` / `get_umapyoi_character` / `get_umapyoi_resources`
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

1. Wiki 查询：使用统一正文入口，保留来源渲染出的表格与台词
2. Biligame 角色资源：走 `biligame-assets`
3. `umamusu.wiki` 分类资源：走分类图片下载
4. 只有在 API 路径不满足时，才考虑视觉抓取

站点建议：

- 游戏数值、技能、支援卡、育成事件：Biligame
- 背景、梗、人物经历、历史原型：Moegirl
- 英文社区整理页、总表、分类图库：umamusu.wiki
- 日文档案、台词与条件：wikiru（按日文名搜索角色索引）
- 结构化档案、衣装/支援卡/图片索引补充：Umapyoi

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

CI 使用显式测试列表，并按调用层次拆成三个独立 job：

| CI job | 验证范围 | 是否联网 |
| --- | --- | --- |
| `Unit tests (offline)` | 解析、索引、配置、资源处理等确定性单元测试 | 否 |
| `Source clients (4 Wiki + Umapyoi)` | 验证四站搜索与正文、Umapyoi 搜索/档案/资源索引 | 是 |
| `MCP Tool calls (4 Wiki + Umapyoi)` | 启动 MCP HTTP 服务，调用四站正文和 Umapyoi 三类工具，验证未注册 Google | 是 |

MCP 集成测试只有在 `RUN_MCP_INTEGRATION=1` 时执行。wikiru/Umapyoi 直接联网测试需 `RUN_SOURCE_INTEGRATION=1`。CI 设置这些变量；新来源本地测试默认跳过联网部分。CI 的临时运行器从空缓存开始，同一 job 内复用响应，避免重复请求。

Google 联网测试还需显式设置 `RUN_GOOGLE_INTEGRATION=1`，默认跳过。正文/搜索采用按主机至少 2 秒的同进程间隔、磁盘缓存；`403/429/567` 不立即重试并冷却至少 60 秒。多进程间不共享限速状态，请避免同时启动多个批量任务。缓存目录由 `CRAWLER_CACHE_DIR` 控制，正文 TTL 1 小时、Umapyoi/角色索引 24 小时，无过期缓存静默降级。

部分相关测试：

- `tests/test_http.py`
- `tests/test_wiki_content.py`
- `tests/test_umapyoi.py`
- `tests/test_supplemental_sources.py`

- `tests/test_biligame_assets.py`
- `tests/test_biligame_crawler.py`
- `tests/test_moegirl_crawler.py`
- `tests/test_umamusu_wiki.py`
- `tests/test_umamusu_wiki_crawler.py`
- `tests/test_search_title.py`
- `tests/test_mcp_wiki_tools.py`
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

另开终端运行四站及 Umapyoi MCP Tool 集成测试：

```bash
RUN_MCP_INTEGRATION=1 uv run pytest tests/test_mcp_wiki_tools.py
```
