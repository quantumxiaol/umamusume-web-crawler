# 项目说明

首次使用请从 [README](../README.md) 开始。这里收录各入口的能力、完整参数、Python 接口和开发相关说明。

## 入口与能力

| 能力 | Python API | 主 CLI `umamusume-crawler` | MCP `umamusume-mcp` | Wiki 查询 Skill |
| --- | --- | --- | --- | --- |
| 四站 Wiki 标题搜索 | 有 | 无独立搜索子命令 | 有 | 有 |
| 四站 Wiki 正文 | 有 | 有 | 有 | 有 |
| Umapyoi 搜索、档案、资源索引 | 有 | 有 | 有 | 有 |
| 角色与衣装索引更新 | 有 | 有 | 无 | 无 |
| Biligame 角色音频、图片下载 | 有 | 有 | 无 | 无 |
| Biligame 小人 PNG 批量下载 | 有 | 有 | 无 | 通过主 CLI |
| umamusu.wiki 分类图片下载 | 有 | 无 | 有 | 有 |
| Google 搜索 | 手动调用 | 无 | 无 | 无 |
| 视觉抓取 | 有 | 有 | 无 | 无 |

四站指 Biligame、萌娘百科、umamusu.wiki 和 wikiru；wikiru 搜索仅覆盖角色索引，使用日文名。CLI、MCP 和 Wiki Skill 共用正文提取逻辑，正文中的关联子页保留为链接，不递归抓取。旧 `max_depth` / `max_pages` 参数在 MCP 和 Wiki Skill 中仅兼容接收。

同人小说和角色提示词两个写作 Skill 在 Wiki 查询之上组织创作流程，见下文 [Skill](#skill)。

## 安装与环境

需要 Python 3.12 或更高版本。在项目根目录用锁定依赖安装：

```bash
uv sync --frozen
```

本文命令中的 `umamusume-crawler`、`umamusume-mcp` 和 `python` 可用 `uv run` 执行；也可以先激活项目虚拟环境。

| 环境变量 | 用途 |
| --- | --- |
| `HTTP_PROXY` / `HTTPS_PROXY` | 代理地址；命令行 `--no-proxy` 会禁用代理 |
| `USER_AGENT` | 请求标识，默认 `UmamusumeWebCrawler/1.0` |
| `CRAWLER_TIMEOUT_S` | 请求超时设置 |
| `CRAWLER_CACHE_DIR` | HTTP 缓存目录，默认 `results/.http-cache` |
| `CRAWLER_USER_DATA_DIR` | 浏览器用户数据目录，用于浏览器抓取 |
| `GOOGLE_API_KEY` / `GOOGLE_CSE_ID` | 手动调用 Google API 搜索时使用，Wiki 查询不需要 |

CLI 和 MCP 入口会读取 `.env` 并更新配置。作为 Python 库调用时，需要自行加载环境变量；若在导入包后才加载 `.env`，再调用 `config.update_from_env()` 更新配置。

常规 Wiki 和 Umapyoi 查询使用 HTTP 请求。使用下文的 [视觉抓取](#历史方案--保留能力) 时，还需安装浏览器：

```bash
uv run playwright install
```

## 代码结构

核心文件：

- [src/umamusume_web_crawler/cli.py](../src/umamusume_web_crawler/cli.py)
  主 CLI 入口。支持正文、角色索引、资源下载与 Umapyoi JSON 输出。
- [src/umamusume_web_crawler/mcp/server.py](../src/umamusume_web_crawler/mcp/server.py)
  MCP 服务与工具定义。
- [src/umamusume_web_crawler/web/biligame.py](../src/umamusume_web_crawler/web/biligame.py)
  Biligame MediaWiki API 访问。
- [src/umamusume_web_crawler/web/moegirl.py](../src/umamusume_web_crawler/web/moegirl.py)
  Moegirl API 访问。
- [src/umamusume_web_crawler/web/umamusu_wiki.py](../src/umamusume_web_crawler/web/umamusu_wiki.py)
  `umamusu.wiki` 搜索、抓取、分类图片下载。
- [src/umamusume_web_crawler/web/biligame_assets.py](../src/umamusume_web_crawler/web/biligame_assets.py)
  Biligame 角色音频/图片批量下载。
- [src/umamusume_web_crawler/web/biligame_chibi.py](../src/umamusume_web_crawler/web/biligame_chibi.py)
  Biligame 互动小人 PNG 下载，区分游戏衣装与图片资源衣装，校验后写入并保存断点。
- [src/umamusume_web_crawler/web/character_targets.py](../src/umamusume_web_crawler/web/character_targets.py)
  两种 Biligame 下载流程共用的角色/衣装索引读取。
- [src/umamusume_web_crawler/web/character_index.py](../src/umamusume_web_crawler/web/character_index.py)
  官网角色名单与 Biligame 角色/衣装索引合并。
- [src/umamusume_web_crawler/web/search.py](../src/umamusume_web_crawler/web/search.py)
  Google 搜索封装。
- [skills/umamusume-wiki-crawler/SKILL.md](../skills/umamusume-wiki-crawler/SKILL.md)
  skill 说明。
- [skills/umamusume-wiki-crawler/scripts/crawl.py](../skills/umamusume-wiki-crawler/scripts/crawl.py)
  skill 使用的 CLI 包装器，只处理参数、进度和输出；查询与分类图片下载都调用包内 `web/tools.py`，下载循环在 `web/umamusu_wiki.py`。

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

### Biligame 互动小人 PNG

```python
from umamusume_web_crawler.web.biligame_chibi import download_biligame_chibi

summary = await download_biligame_chibi(
    characters=["丸善斯基", "1003"],  # 省略则下载本地索引全部已实装角色
    output_dir="results/biligame_chibi",
    characters_json="umamusume_characters.json",
    base_only=False,                # 默认包括换装，无需 include_variants
    refresh_existing=False,
    request_delay=5,                # 同主机实际请求间隔；页面/文件信息 API 与图片均适用
    page_delay=10,                  # 衣装页之间的等待
    use_proxy=False,
    progress=print,                 # 可省略，库默认不打印
)
assert summary["pages_pending"] == 0, summary["errors"]
```

对应 CLI 为 `--task biligame-chibi`，用 `--chibi-output` 指定目录，`--character` 可重复，支持中文名、英文名或角色 ID；不需要 `--name`。

```bash
# 指定多个角色，默认同时下载原皮和换装
uv run umamusume-crawler --task biligame-chibi --character 丸善斯基 --character 1003 --no-proxy

# 只下载原皮，并指定目录
uv run umamusume-crawler --task biligame-chibi --character Maruzensky --chibi-output ./my_chibi --base-only --no-proxy

# 重新检查站点图片版本；未变化时复用本地文件
uv run umamusume-crawler --task biligame-chibi --character 丸善斯基 --refresh-existing --no-proxy

# 省略角色参数时下载本地索引中的全部已实装角色
uv run umamusume-crawler --task biligame-chibi --request-delay 10 --page-delay 20 --no-proxy
```

默认目录示例：

```text
results/biligame_chibi/
├── .chibi_manifest.json
└── 1004_丸善斯基/
    ├── 100401_原皮/
    │   ├── Petit_chr_1004_100401_0010.png
    │   └── Petit_chr_1004_100401_0011.png
    ├── 100402_【ぶっとび☆さまーナイト】/
    │   ├── Petit_chr_1004_100430_0010.png
    │   └── Petit_chr_1004_100430_0011.png
    └── 100403_【祝ひ寿ぐ神速天女】/
        ├── Petit_chr_1004_100410_0010.png
        └── Petit_chr_1004_100410_0011.png
```

衣装目录使用游戏衣装 ID，文件名使用图片资源衣装 ID，两者可能不同。例如丸善斯基夏日换装对应 `100402 → 100430`。下载器读取页面实际引用，不按游戏衣装 ID 猜图片地址。

通过 `action=parse` 查找 Qchar 小人引用，再用 `imageinfo` 取得原始 PNG 地址和源文件版本。两种 API 请求均带项目 UA、JSON Accept 和同 Wiki Referer。HTTP 错误保留处理阶段、状态码及 `Server` / `EO-LOG-UUID` 等诊断头，供排查边缘拦截；不保存 Cookie。目录按 `角色ID_中文名/游戏衣装ID_衣装名/` 分组，原皮衣装名为 `原皮`；PNG 文件名保留页面引用的资源 ID。状态编号沿用 `0010`、`0011`，不解释为前后视角。

输出根目录内的 `.chibi_manifest.json` 以 `角色ID:游戏衣装ID` 为键，记录 `is_base`、`page_title`、`source_page`、`resource_costume_id`；每张图保存相对路径、源文件标题/URL/版本哈希、本地 SHA-256、尺寸及格式。`complete` 表示当前衣装所有已发现图片下载成功且包含这两个状态；缺图/失败记作 `partial`。同一输出目录使用进程文件锁，防止并发覆盖下载记录。

`pages_complete` 包含本次下载完成及已校验跳过的衣装；`pages_skipped` 表示无需访问站点的衣装。`images_downloaded`/`images_reused` 分别是本次下载与访问页面后复用的图片数；`pages_pending` 包括缺图、失败及限流停止后未处理的衣装。CLI 遇到未完成项返回退出码 `1`。常规重跑校验本地 SHA-256 并修复缺失/损坏文件；`refresh_existing=True` 绕过页面/API 缓存，对比源版本更新图片。断点按图片保存，失败不会覆盖已有有效 PNG。

默认同主机实际请求间隔 5 秒（最低 2 秒），衣装页间隔 10 秒；分别由 `--request-delay`、`--page-delay` 调整。页面 API、文件信息 API 和图片下载都遵守请求间隔，命中缓存不访问站点。首条请求立即发出，delay 控制后续请求的间隔；临时网络错误最多重试一次。PNG 在写入前检查格式、尺寸与完整性，校验成功后原子替换文件。

遇到 `403/429/567` 或要求稍后重试的响应会停止并保留进度。错误记录包括 `page_html`、`image_info` 或 `image_download:状态编号` 阶段，便于确认失败位置；稍后重跑同一命令即可续传。HTTP 567 的排查记录见 [开发日志](devlog.md#http-567-的排查)。

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

Wiki 搜索和分类图片下载可通过 Python API、MCP 或 Wiki Skill 调用；Google 搜索仅提供 Python 函数。

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

三个 Skill 均随本项目使用：

| Skill | 用途 | 默认输出 |
| --- | --- | --- |
| [umamusume-wiki-crawler](../skills/umamusume-wiki-crawler/SKILL.md) | 搜索、获取 Wiki 正文、查询资源 | 查询脚本返回 JSON，由助手按任务使用 |
| [umamusume-fanfic-writer](../skills/umamusume-fanfic-writer/SKILL.md) | 根据角色资料与用户构思写同人小说 | `results/novel/角色名_同人标题.md` |
| [umamusume-roleplay-prompt-writer](../skills/umamusume-roleplay-prompt-writer/SKILL.md) | 生成或修改角色扮演提示词 | `results/roleplay_prompt/<English_Name>.md` |

两个写作 Skill 依赖 Wiki 查询；如有匹配的 `results/character_story/` 本地剧情，也会结合原场景核对人设、关系与称呼。用户可在任务中指定其他输出路径。

角色提示词正文供模型整份读取，来源、称呼核对和开场素材保存到 `results/roleplay_prompt/_notes/<English_Name>.md`。`Almond_Eye.md` 是杏目的文件名示例，其他角色使用各自英文名。正文格式与现有角色构建器的衔接见 [输出格式](../skills/umamusume-roleplay-prompt-writer/references/output-format.md)；旧文件保留原位置，Skill 不自动迁移目录。

Wiki 查询统一入口：

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
- Biligame 小人 PNG 使用主 CLI 的 `--task biligame-chibi`；原皮/换装与续跑说明见 `SKILL.md`
- 其他 Biligame 角色音频/图片下载仍使用主 CLI 的 `--task biligame-assets`
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

CI 使用显式测试列表。离线解析和功能回归必须通过，五个站点的真实访问探测只报告告警：

| CI job | 验证范围 | 是否联网 |
| --- | --- | --- |
| `Unit tests (offline)` | 解析、索引、配置、资源处理等确定性单元测试 | 否 |
| `Availability (advisory) / Biligame` | 标题搜索、正文及 MCP 正文工具 | 是 |
| `Availability (advisory) / Moegirl (萌娘百科)` | 标题搜索、公开 HTML 正文及 MCP 正文工具 | 是 |
| `Availability (advisory) / umamusu.wiki` | 标题搜索、正文及 MCP 正文工具 | 是 |
| `Availability (advisory) / wikiru` | 日文角色搜索、正文及 MCP 正文工具 | 是 |
| `Availability (advisory) / Umapyoi` | 搜索、档案、资源索引及对应的三个 MCP 工具 | 是 |

离线测试用固定 HTML/JSON 样本和 mock 验证正文、折叠台词、表格对应关系、字段提取、MCP 工具结果及 HTTP 错误处理。解析失败仍会使 CI 失败，不依赖外站可用性，也不需要先访问站点录制响应。

联网探测先检查 Python 客户端，成功后启动 MCP 服务并检查工具调用。两个联网 pytest 步骤设置 `continue-on-error: true`：HTTP 拒绝访问、超时、接口错误、缺少字段或正文断言失败都会保留在报告中，并产生 Actions warning，但不使 CI 失败。测试断言没有放宽，JUnit 中仍记录真实失败；本地直接运行这些联网测试时仍返回非零退出码。依赖安装、本地 MCP 服务启动等步骤仍按正常错误处理。

每个联网 pytest 步骤使用 `--maxfail=1`，遇到首个失败便停止；不清空同主机的冷却和限速状态来继续请求。MCP 步骤依据来源步骤的实际 `outcome` 判断，来源失败时报告 `skipped`（未验证），不会因为忽略错误后的 `conclusion: success` 又发起请求。离线传输测试通过 fixture 隔离状态，和真实探测的冷却策略分开处理。

矩阵设置 `fail-fast: false`，一个站点失败不会取消其他站点；最多同时探测两个站点。Actions 摘要分别列出来源调用、MCP 服务和 MCP 工具的实际结果；每站的 `source-check-<site>` 附件保存 JUnit 测试报告与已产生的 MCP 日志。可用性任务显示绿色只表示没有阻断 CI，站点是否可用要看摘要和告警。探测范围是现有代表页面和接口，不能证明全站内容都正常。

HTTP 错误会记录响应中的 `CF-Ray`、`cf-mitigated` 和错误页标题（若有），与状态码一起出现在步骤日志、JUnit 报告和工具返回的错误信息中。标题只从 HTML 错误响应的前 8 KiB 提取，压成单行并截到 200 字符；不保存完整错误页、Cookie 或验证脚本。标题读取失败时仍保留原始 HTTP 错误，不为诊断重新请求。小人下载的错误记录也保留这些诊断信息。

推送和 PR 会自动运行，也可在 Actions 中使用 **Run workflow** 手动复查。MCP 集成测试只有在 `RUN_MCP_INTEGRATION=1` 时执行。wikiru/Umapyoi 直接联网测试需 `RUN_SOURCE_INTEGRATION=1`。CI 设置这些变量；新来源本地测试默认跳过联网部分。每个站点从空缓存开始，Python 和 MCP 在同一 job 内共享响应缓存，避免重复请求。

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
