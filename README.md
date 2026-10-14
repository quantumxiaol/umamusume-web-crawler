# Umamusume Web Crawler

查询赛马娘角色资料、导出 Wiki 正文，并下载角色图片与音频。支持命令行、MCP 和 Skill，可用于资料整理、同人小说创作和角色扮演提示词制作。

## 支持的资料来源

| 来源 | 适合查询的内容 |
| --- | --- |
| [Biligame 赛马娘 Wiki](https://wiki.biligame.com/umamusume/) | 游戏档案、技能、育成事件、台词与角色资源 |
| [萌娘百科](https://mzh.moegirl.org.cn/) | 角色背景、作品设定与原型资料 |
| [umamusu.wiki](https://umamusu.wiki/) | 英文角色资料、整理页与分类图库 |
| [wikiru](https://umamusume.wikiru.jp/) | 日文档案、台词及触发条件；角色搜索使用日文名 |
| [Umapyoi](https://umapyoi.net/) | 结构化角色档案、衣装、支援卡和图片资源索引 |

Wiki 正文导出为 Markdown，保留表格、折叠台词和链接；Umapyoi 提供 JSON 数据。正文中的关联页面保留为链接，需要时可单独获取。

代码中也提供 Google 搜索工具，但默认不启用。日常角色查询与创作所需的资料通常可以从上述来源获取，无需配置 Google。

## 安装

需要 Python 3.12 或更高版本，以及 `uv`。下载或克隆本仓库后，在项目根目录执行：

```bash
uv sync --frozen
uv run umamusume-crawler --help
```

完成安装即可查询 Wiki、读取 Umapyoi 数据或下载小人图片。下文的命令均在项目根目录运行，输出默认保存在 `results/` 下。

## 配合 AI 助手使用

用能够读取本地文件、执行命令的 AI 助手打开本项目，然后发送下面的任务描述。Skill 随完整项目使用，查询脚本依赖仓库中的 Python 代码。

### 查询角色资料

[Wiki 查询 Skill](./skills/umamusume-wiki-crawler/SKILL.md) 负责搜索与获取资料。例如：

```text
使用 skills/umamusume-wiki-crawler/SKILL.md，查询东海帝王的角色档案、
说话习惯和对训练员的称呼，整理结果并附来源链接。
```

### 写小说

可以让助手用 Wiki 查询 Skill 收集资料，再按自己的构思写作：

```text
使用 skills/umamusume-wiki-crawler/SKILL.md 查询星云天空的资料，
结合她的性格与说话习惯，写一篇训练员陪她钓鱼的同人短篇。
剧情重点是两人从互相试探到坦白心意，约 3000 字。
```

此前用这种方式生成的作品：

- [爱丽速子：不可测量的化学反应](./result/Tachyon.md) — Antigravity + Gemini 3.1 Pro。
- [星云天空：钓上来的那颗心](./result/钓上来的那颗心.md) — Codex + GPT 5.6 sol。

现在也提供专用的 [同人小说 Skill](./skills/umamusume-fanfic-writer/SKILL.md)，把资料核对、创作和成稿检查放在同一流程中。直接给出角色与剧情即可：

```text
使用 skills/umamusume-fanfic-writer/SKILL.md，写一篇星云天空的同人短篇。
剧情是训练员陪她钓鱼，两人从互相试探到坦白心意，约 3000 字。
```

小说默认保存到 `results/novel/`，文末附资料来源和原创情节说明；也可以在请求中指定输出路径。

### 写角色扮演提示词

同样可以先用 Wiki 查询 Skill 收集资料，再让助手整理成提示词：

```text
使用 skills/umamusume-wiki-crawler/SKILL.md 查询爱如往昔的资料，
为她制作中文角色扮演提示词，包含性格、说话习惯、重要关系和台词示例。
用户扮演训练员。
```

此前生成的示例：[爱如往昔的角色扮演提示词](./result/Still_in_Love.md)。更多示例见 [umamusume-agent 的角色目录](https://github.com/quantumxiaol/umamusume-agent/tree/main/characters)。

也可以直接使用专用的 [角色提示词 Skill](./skills/umamusume-roleplay-prompt-writer/SKILL.md)，由它调用 Wiki 查询并组织角色设定：

```text
使用 skills/umamusume-roleplay-prompt-writer/SKILL.md，为杏目制作中文
角色扮演提示词。用户扮演已经与她相识的训练员，侧重日常相处和训练中的互动。
```

提示词保存在 `results/roleplay_prompt/`，按角色英文名命名，例如杏目对应 `Almond_Eye.md`。正文用于提供给模型的角色设定；资料来源、称呼核对和开场素材另存于该目录下的 `_notes/`，方便查阅和调整。

两个专用写作 Skill 都会查询 Wiki。如果已有本地剧情资料，可放在 `results/character_story/` 中供它们参考；没有本地剧情时，则使用能获取的 Wiki 资料。

## 命令行使用

### 导出 Wiki 正文

```bash
# Biligame 中文正文
uv run umamusume-crawler \
  --url "https://wiki.biligame.com/umamusume/东海帝皇" \
  --output results/teio.md

# wikiru 日文正文
uv run umamusume-crawler --mode wikiru \
  --url "トウカイテイオー" --output results/teio-ja.md
```

也支持萌娘百科和 umamusu.wiki 的页面 URL。省略 `--output` 时写入 `results/crawl.md`，使用 `--output -` 可直接输出到终端。

### 查询 Umapyoi 档案与资源

先搜索角色，再用结果中的 `game_id` 获取资料。以下示例中的 `1003` 是东海帝王的游戏 ID：

```bash
uv run umamusume-crawler --task umapyoi-search --keyword "Tokai Teio" --output -
uv run umamusume-crawler --task umapyoi-character --game-id 1003 --output results/teio-profile.json
uv run umamusume-crawler --task umapyoi-resources --game-id 1003 --output results/teio-resources.json
```

资源查询返回衣装、支援卡与图片链接，不会下载文件。链接可能失效，缺失字段会按原样保留。

### 对比五个来源

想直接查看各站的获取效果，可以一次导出东海帝王的五份样例：

```bash
uv run python scripts/export_source_samples.py --no-proxy
```

结果写入 `results/test_raw_crawler/`：`biligame.md`、`moegirl.md`、`umamusu.md`、`wikiru.md`、`umapyoi.md`。前四份是 Wiki 正文，最后一份包含 Umapyoi 的 JSON 档案与资源索引。只查看一站时，添加 `--site biligame` 等参数。

## Biligame 小人图片

下载角色页面左下角互动小人的透明 PNG，默认包含原皮和换装：

```bash
# 单个角色，默认保存到 results/biligame_chibi
uv run umamusume-crawler --task biligame-chibi --character 丸善斯基 --no-proxy

# 只下载原皮，并指定保存目录
uv run umamusume-crawler --task biligame-chibi \
  --character 丸善斯基 --base-only --chibi-output ./my_chibi --no-proxy

# 下载本地索引中的全部已实装角色，并放慢请求间隔
uv run umamusume-crawler --task biligame-chibi \
  --request-delay 10 --page-delay 20 --no-proxy
```

`--character` 支持中文名、英文名或角色 ID，可以重复指定多个角色。图片按角色与衣装分目录保存，原皮目录标为 `原皮`，换装目录保留衣装名。每套衣装通常有两张互动状态图。

再次运行同一命令会校验并跳过已完成内容，补齐缺失或损坏的图片。请保留输出目录中的 `.chibi_manifest.json`，其中保存下载进度和角色、衣装、图片的对应关系。

需要新增角色或衣装时，先更新本地索引：

```bash
uv run umamusume-crawler --task update-character-index --no-proxy
```

更多参数、目录示例和错误处理见 [小人下载说明](./docs/structure.md#biligame-互动小人-png)。角色立绘和音频下载见 [角色资源下载](./docs/structure.md#3-biligame-角色资源下载)。

## 接入 MCP

启动本地服务：

```bash
uv run umamusume-mcp --http -p 7777
```

在支持 Streamable HTTP 的 MCP 客户端中添加 `http://127.0.0.1:7777/mcp/`。服务提供四站 Wiki 搜索与正文、Umapyoi 档案与资源索引，以及 umamusu.wiki 分类图片下载。

使用 stdio 客户端时，将工作目录设为项目根目录，启动命令为 `uv run umamusume-mcp`。工具参数见 [MCP 说明](./docs/structure.md#mcp)。

## 请求与常见问题

- **代理**：命令行加 `--no-proxy` 可直接连接；需要代理时配置 `HTTP_PROXY` / `HTTPS_PROXY` 并使用 `--use-proxy`。
- **重复查询**：默认复用有效缓存，存放在 `results/.http-cache/`，可通过 `CRAWLER_CACHE_DIR` 更改目录。
- **访问受限**：遇到 `403/429/567` 时先查看错误信息，稍后再试。站点可能针对脚本请求或不同网络环境设置访问限制，浏览器能打开页面不代表脚本一定可用。
- **批量下载**：按设置的间隔逐步请求。不要同时启动多个下载任务；中断后重跑原命令即可续传小人图片。

## 更多文档

- [项目说明](./docs/structure.md)：完整参数、Python API、MCP 工具、环境配置与测试方式。
- [开发日志](./docs/devlog.md)：抓取方案的演变、正文完整性改进与访问问题排查。
