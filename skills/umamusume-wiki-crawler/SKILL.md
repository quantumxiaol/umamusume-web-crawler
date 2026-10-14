---
name: umamusume-wiki-crawler
description: 查询赛马娘 Wiki 档案、台词和资源，或下载角色小人图片时使用。支持 Biligame、萌娘百科、umamusu.wiki、wikiru 正文，Umapyoi 结构化档案与资源索引，以及 Biligame 小人 PNG、umamusu.wiki 分类图片下载。
---

# 查询流程

在项目根目录执行；首次使用先运行 `uv sync --frozen` 安装项目依赖。查询入口：

```bash
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py <tool> [args]
```

`crawl.py` 负责参数解析、进度和 JSON 输出，查询与下载逻辑复用 `src/umamusume_web_crawler`。这个 skill 随项目使用，单独复制 skill 目录不能运行。

1. 有准确 URL 或标题可直接抓取，否则先搜索。
2. 按问题选择来源：Biligame 查机制/技能/育成；萌娘查背景/原型；umamusu.wiki 查英文整理与图库；wikiru 查日文档案、台词及触发条件。
3. Umapyoi 补充结构化档案和资源索引，不自动覆盖其他来源。对冲突保留来源并核对。
4. 根据正文 Markdown 回答，引用来源链接。正文保留表格、折叠台词；关联子页只保留链接，需要时单独读取。

# 搜索与正文工具

| 站点 | 搜索命令 | 正文命令 |
| --- | --- | --- |
| Biligame | `biligame_wiki_search` | `crawl_biligame_wiki` |
| 萌娘 | `moegirl_wiki_search` | `crawl_moegirl_wiki` |
| umamusu.wiki | `umamusu_wiki_search` | `crawl_umamusu_wiki` |
| wikiru | `wikiru_wiki_search` | `crawl_wikiru_wiki` |

搜索参数为 `keyword --limit 5`；正文参数为 URL 或准确标题。wikiru 搜索仅查角色索引，使用日文名；URL 格式为 `https://umamusume.wikiru.jp/?日文标题`。

```bash
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py biligame_wiki_search "东海帝皇"
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py crawl_biligame_wiki "东海帝皇"
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py wikiru_wiki_search "トウカイテイオー"
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py crawl_wikiru_wiki "トウカイテイオー"
```

Bwiki/umamusu 使用 MediaWiki parse；萌娘和 wikiru 读取公开 HTML。旧 `--max-depth/--max-pages` 仅兼容接收。搜索返回 `results`；正文返回 `status`、Markdown `result`、`infobox`、`source_url` 与 `transport`。`infobox` 只提取常见字段，完整信息以正文表格为准。

# Umapyoi 补充资料

```bash
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py umapyoi_character_search "Tokai Teio"
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py get_umapyoi_character 1003
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py get_umapyoi_resources 1003
```

搜索支持日文、英文或游戏 ID。使用返回的 `game_id`，不要使用数据库 `id`；无 `game_id` 的记录不能按 ID 查询。档案保留 `null` 和 `missing_fields`，不要自行补全。资源索引包含衣装、支援卡、图片分组及档案资源链接；团体支援卡可能具有其他主角色 ID。链接标为 `unverified`，不代表能下载；部分接口失败会返回 `partial` 与 `errors`。

# 分类图片

```bash
uv run python skills/umamusume-wiki-crawler/scripts/crawl.py download_umamusu_category_images "Category:Game_Backgrounds" --output-dir results/umamusu/backgrounds --max-files 10 --delay 2
```

支持分类翻页，跳过已有文件。JSON 输出到 stdout，进度到 stderr。

# Biligame 小人 PNG

使用项目主 CLI。按用户指定的角色下载；只有需要全量时才省略 `--character`：

```bash
uv run umamusume-crawler --task biligame-chibi --character "丸善斯基" --chibi-output results/biligame_chibi --request-delay 10 --page-delay 20 --no-proxy
```

`--character` 可重复，支持中文名、英文名或角色 ID。默认包含该角色的原皮和换装，`--base-only` 只取原皮。输出按角色 ID/名称和游戏衣装 ID/名称分目录；图片名使用页面实际资源 ID，不能根据游戏衣装 ID 自行拼接。默认目录是 `results/biligame_chibi`。

相同命令可续跑，保留 `.chibi_manifest.json`；已完成的图片会校验后跳过。默认同主机请求间隔 5 秒、衣装页间隔 10 秒，上例使用更长间隔。遇到 `403/429/567` 会停止，查看错误后稍后续跑。

# 请求与错误处理

- Google 默认禁用，skill 不提供 Google 工具。
- `--proxy` 使用配置代理，`--no-proxy` 禁用代理。
- 公共请求使用项目 UA、缓存与按主机限速。不要同时启动多个进程绕过限速。
- `403/429/567` 时保留错误并稍后重试；不绕过限制、不用摘要冒充完整正文。
- 搜索为空可以换关键词；失败 JSON 要向用户明确说明，不能当成资料不存在。
