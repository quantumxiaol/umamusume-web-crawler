# Umamusume Web Crawler

围绕赛马娘 Wiki 的正文提取、结构化档案和资源索引工具集：

- `wiki.biligame.com/umamusume`
- `mzh.moegirl.org.cn`
- `umamusu.wiki`
- `umamusume.wikiru.jp`（PukiWiki 公开正文）
- `umapyoi.net`（JSON 档案与资源索引）

Google 函数代码保留；MCP server 不导入、不注册 Google 工具，也没有启用开关；skill 不调用 Google。视觉抓取方案继续保留。

我之前试过crawl4ai ，把网站pdf 化，用markitdown、qwen2.5VL转markdown，做完发现效果还是不好，又看到他们开放了 MediaWiki API接口，发现前面的东西白做了。

## 当前定位

当前代码的主线能力是：

- 四站 wiki 搜索与完整正文 Markdown（wikiru 搜索限角色索引，使用日文名）
- 保留档案表、技能表、折叠台词及来源链接
- Umapyoi 结构化档案、衣装/支援卡/图片索引
- 部分资源下载
  - Biligame：角色音频/图片批量下载
  - umamusu.wiki：分类图片批量下载
- Google 搜索函数保留，可由 Python 手动调用

## 使用

这个项目最早是为了我自己产出赛马娘同人小说/角色扮演提示词的agent工作流设计的，随着agent与skill的发展，那个项目已经没用了，普通人不可能开发一个强过codex、claude code的agent。

### 写小说

```
你有skills/umamusume-wiki-crawler/skill.md ，能够获取角色的wiki 资料。
你需要根据用户构思的小说剧情，结合wiki查到的信息，写一篇完整的小说。
```

[生成小说实例1](./result/Tachyon.md)，爱丽速子，Antigravity + Gemini 3.1 Pro 生成。
[生成小说实例2](./result/钓上来的那颗心.md)，星云天空，Codex + GPT 5.6 sol 生成。

### 写角色扮演提示词

```
你有skills/umamusume-wiki-crawler/skill.md ，能够获取角色的wiki 资料。
你需要根据用户提供的角色，在wiki查信息，写一份sillytavern 角色扮演所需要的提示词。
```

[爱如往昔的提示词](./result/Still_in_Love.md)

更多写好的[提示词](https://github.com/quantumxiaol/umamusume-agent/tree/main/characters)

## 能力矩阵

| 能力 | Python API | 主 CLI `umamusume-crawler` | MCP `umamusume-mcp` | Skill `skills/umamusume-wiki-crawler` |
| :--- | :--- | :--- | :--- | :--- |
| Google 搜索 | 保留 | 无独立入口 | 不加载 | 无 |
| Biligame 标题搜索 | 有 | 无独立搜索子命令 | 有 | 有 |
| Moegirl 标题搜索 | 有 | 无独立搜索子命令 | 有 | 有 |
| umamusu.wiki 标题搜索 | 有 | 无独立搜索子命令 | 有 | 有 |
| Biligame 页面抓取 | 有 | 有 | 有 | 有 |
| Moegirl 页面抓取 | 有 | 有 | 有 | 有 |
| umamusu.wiki 页面抓取 | 有 | 有 | 有 | 有 |
| wikiru 角色搜索/正文 | 有 | 正文 | 有 | 有 |
| Umapyoi 搜索/档案/资源索引 | 有 | 有 | 有 | 有 |
| 角色/衣装索引更新 | 有 | 有 | 无 | 无 |
| Biligame 角色音频/图片下载 | 有 | 有 | 无 | 无 |
| umamusu.wiki 分类图片下载 | 有 | 无 | 有 | 有 |
| 视觉抓取 | 有 | 有 | 无 | 无 |

补充说明：

- 主 CLI 支持 `page`、`update-character-index`、`biligame-assets`，以及 `umapyoi-search`、`umapyoi-character`、`umapyoi-resources`。
- MCP 和 skill 共用正文与工具逻辑，提供四站搜索/抓取、Umapyoi 补充资料及分类图片下载。
- Bwiki/umamusu 正文使用 MediaWiki `action=parse`；萌娘使用公开 HTML，避免 `extracts` 丢失表格；wikiru 使用公开 PukiWiki HTML。
- 正文不递归抓关联页，保留链接。旧 `max_depth` / `max_pages` 在 MCP/skill 中仅兼容接收，不再影响渲染正文。

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
- `USER_AGENT`（默认可识别的 `UmamusumeWebCrawler/1.0`）
- `CRAWLER_TIMEOUT_S`
- `CRAWLER_USER_DATA_DIR`
- `CRAWLER_CACHE_DIR`（默认 `results/.http-cache`）

说明：

- `GOOGLE_API_KEY` / `GOOGLE_CSE_ID` 只在 Google 搜索相关能力中需要。
- Wiki 与 Umapyoi 均不依赖 Google。默认请求使用项目 UA；同进程同主机串行，间隔至少 2 秒。正文缓存 1 小时，Umapyoi/日文角色索引缓存 24 小时；删除缓存文件可强制刷新。
- `403/429/567` 明确报错并冷却，不自动切换到摘要或 Google。
- `main.py` 与 `mcpserver.py` 会自动尝试加载当前目录 `.env`。
- 作为 Python 库调用时，不会自动读取 `.env`，请自行 `load_dotenv()` 或直接传环境变量。

## 快速使用

```bash
umamusume-crawler --url "https://wiki.biligame.com/umamusume/东海帝皇" --output results/teio.md
umamusume-crawler --mode wikiru --url "トウカイテイオー" --output results/teio-ja.md
umamusume-crawler --task umapyoi-search --keyword "Tokai Teio" --output -
umamusume-crawler --task umapyoi-character --game-id 1003 --output results/teio-profile.json
umamusume-crawler --task umapyoi-resources --game-id 1003 --output results/teio-resources.json
umamusume-mcp --http -p 7777
```

Umapyoi 使用 `game_id`，不是其数据库 `id`。缺失字段保持为空，资料带来源，不自动覆盖 Wiki 档案。资源链接标为未验证，不自动下载；支援卡索引可能包含其他主角色 ID 的团体卡。

使用说明见[结构与使用](./docs/structure.md)。
