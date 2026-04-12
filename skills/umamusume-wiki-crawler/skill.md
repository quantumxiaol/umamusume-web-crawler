---
name: umamusume-wiki-crawler
description: 赛马娘 (Umamusume) Wiki 查询技能。通过 CLI 调用四个核心工具：Biligame 标题搜索、Moegirl 标题搜索、Biligame 页面抓取、Moegirl 页面抓取。
version: 1.1.0
---

# 用途

当用户要查询《赛马娘 Pretty Derby》Wiki 信息时，使用本 Skill。

- 游戏数值、技能、支援卡、育成事件优先走 Biligame。
- 人设背景、历史原型、梗、角色经历优先走 Moegirl。

# 四个核心工具（CLI 子命令）

- `biligame_wiki_search`：在 Bilibili Wiki 搜索标题。
- `moegirl_wiki_search`：在萌娘百科搜索标题。
- `crawl_biligame_wiki`：抓取并解析 Bilibili Wiki 页面。
- `crawl_moegirl_wiki`：抓取并解析萌娘百科页面。

输出为 JSON：
- 搜索命令返回 `{"results": [...]}`。
- 抓取命令返回 `{"status": "success", "result": "...markdown..."}`。

# 执行步骤

1. 先搜索，再抓取，不要猜 URL。
2. 根据问题类型选择站点：
- 数值/机制类 -> `biligame_wiki_search` + `crawl_biligame_wiki`
- 背景/历史类 -> `moegirl_wiki_search` + `crawl_moegirl_wiki`
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

代理参数（按需）：

- `--proxy` 强制使用代理
- `--no-proxy` 强制不使用代理

# 约束

- 只调用这四个子命令，不混用其他抓取脚本。
- 搜索结果为空时，先换关键词再抓取。
- 抓取失败时保留错误 JSON，向用户明确说明失败原因。
