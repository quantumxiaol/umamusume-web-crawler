# Umamusume Web Crawler

围绕 3 个赛马娘 Wiki 的搜索、抓取与部分资源下载工具集：

- `wiki.biligame.com/umamusume`
- `mzh.moegirl.org.cn`
- `umamusu.wiki`

同时保留 Google 搜索能力，以及一套不再作为主流程推荐的视觉抓取方案。

我之前试过crawl4ai ，把网站pdf 化，用markitdown、qwen2.5VL转markdown，做完发现效果还是不好，又看到他们开放了 MediaWiki API接口，发现前面的东西白做了。

## 当前定位

当前代码的主线能力是：

- 三站 wiki 的标题搜索
- 三站 wiki 的页面抓取与 Markdown 化
- 部分资源下载
  - Biligame：角色音频/图片批量下载
  - umamusu.wiki：分类图片批量下载
- Google 搜索

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
| Google 搜索 | 有 | 无独立入口 | 有 | 无 |
| Biligame 标题搜索 | 有 | 无独立搜索子命令 | 有 | 有 |
| Moegirl 标题搜索 | 有 | 无独立搜索子命令 | 有 | 有 |
| umamusu.wiki 标题搜索 | 有 | 无独立搜索子命令 | 有 | 有 |
| Biligame 页面抓取 | 有 | 有 | 有 | 有 |
| Moegirl 页面抓取 | 有 | 有 | 有 | 有 |
| umamusu.wiki 页面抓取 | 有 | 有 | 有 | 有 |
| 角色/衣装索引更新 | 有 | 有 | 无 | 无 |
| Biligame 角色音频/图片下载 | 有 | 有 | 无 | 无 |
| umamusu.wiki 分类图片下载 | 有 | 无 | 有 | 有 |
| 视觉抓取 | 有 | 有 | 无 | 无 |

补充说明：

- 主 CLI 现在是三个任务：
  - `--task page`：页面抓取
  - `--task update-character-index`：合并官网角色表与 Biligame 衣装索引
  - `--task biligame-assets`：Biligame 角色音频/图片下载
- skill 目前只封装三站 wiki 搜索/抓取和 `umamusu.wiki` 分类图片下载，不包含 Google 搜索，也不包含 Biligame 角色资源下载。
- MCP 目前包含 Google 搜索、三站 wiki 搜索/抓取、`umamusu.wiki` 分类图片下载，不包含 Biligame 角色资源下载。


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

## 快速使用

```bash
umamusume-crawler \
  --url "https://wiki.biligame.com/umamusume/东海帝皇"
[API-CRAWL] Fetching https://wiki.biligame.com/umamusume/东海帝皇 via MediaWiki API...
Wrote 9994 chars to results/crawl.md
```

结果包含页面内容，模型可以使用。

```
赛马娘
- **角色ID**: 1003
- **ID**: 100301
- **日文名**: トウカイテイオー
- **中文名**: 东海帝皇
- **昵称**: トップ・オブ・ジョイフル
- **初始星级**: 3
```

使用说明的详情见[结构与使用](./docs/structure.md)