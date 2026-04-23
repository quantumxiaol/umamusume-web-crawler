---
name: umamusume-wiki-crawler
description: 赛马娘 (Umamusume) Wiki 查询技能。通过 CLI 调用 Biligame、Moegirl 与 umamusu.wiki 的搜索/抓取工具，并支持按分类批量下载图片。
version: 1.2.0
---

# 用途

当用户要查询《赛马娘 Pretty Derby》Wiki 信息时，使用本 Skill。

- 游戏数值、技能、支援卡、育成事件优先走 Biligame。
- 人设背景、历史原型、梗、角色经历优先走 Moegirl。

# 四个核心工具（CLI 子命令）

- `biligame_wiki_search`：在 Bilibili Wiki 搜索标题。
- `moegirl_wiki_search`：在萌娘百科搜索标题。
- `umamusu_wiki_search`：在 `umamusu.wiki` 搜索标题。
- `crawl_biligame_wiki`：抓取并解析 Bilibili Wiki 页面。
- `crawl_moegirl_wiki`：抓取并解析萌娘百科页面。
- `crawl_umamusu_wiki`：抓取并解析 `umamusu.wiki` 页面。
- `download_umamusu_category_images`：下载 `umamusu.wiki` 某分类下的全部文件图片。

输出为 JSON：
- 搜索命令返回 `{"results": [...]}`。
- 抓取命令返回 `{"status": "success", "result": "...markdown..."}`。

# 执行步骤

1. 先搜索，再抓取，不要猜 URL。
2. 根据问题类型选择站点：
- 数值/机制类 -> `biligame_wiki_search` + `crawl_biligame_wiki`
- 背景/历史类 -> `moegirl_wiki_search` + `crawl_moegirl_wiki`
- 英文社区整理页、角色总表、分类图片 -> `umamusu_wiki_search` / `crawl_umamusu_wiki` / `download_umamusu_category_images`
3. 基于抓取结果中的 Markdown 回答用户问题。

# 命令格式

统一入口：

```bash
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py <tool> [args]
```

查看帮助：

```bash
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py --help
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py biligame_wiki_search --help
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py crawl_moegirl_wiki --help
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py crawl_umamusu_wiki --help
```

# 示例

Biligame 搜索标题：

```bash
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py \
  biligame_wiki_search "东海帝皇" --limit 5
```

Moegirl 搜索标题：

```bash
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py \
  moegirl_wiki_search "东海帝王" --limit 5
```

抓取 Biligame 页面：

```bash
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py \
  crawl_biligame_wiki "https://wiki.biligame.com/umamusume/东海帝皇" \
  --max-depth 1 --max-pages 5
```

抓取 Moegirl 页面：

```bash
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py \
  crawl_moegirl_wiki "https://mzh.moegirl.org.cn/东海帝王" \
  --max-depth 1 --max-pages 5
```

搜索 umamusu.wiki：

```bash
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py \
  umamusu_wiki_search "Agnes Tachyon" --limit 5
```

抓取 umamusu.wiki 页面：

```bash
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py \
  crawl_umamusu_wiki "https://umamusu.wiki/List_of_Characters" \
  --max-depth 1 --max-pages 5
```

下载分类图片：

```bash
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py \
  download_umamusu_category_images "Category:Game_Backgrounds" \
  --output-dir results/umamusu/backgrounds --delay 0.5
```

代理参数（按需）：

- `--proxy` 强制使用代理
- `--no-proxy` 强制不使用代理

# 约束

- 优先调用本脚本内的对应子命令，不混用其他零散抓取脚本。
- 搜索结果为空时，先换关键词再抓取。
- 抓取失败时保留错误 JSON，向用户明确说明失败原因。
- 批量下载图片时保留 `delay`，并处理分类翻页。
