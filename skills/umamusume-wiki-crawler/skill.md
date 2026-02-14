---
name: umamusume-wiki-crawler
description: 赛马娘 (Umamusume) 领域的专家助手。专门用于查询游戏数据（技能/属性/支援卡）和角色背景（历史原型/性格/轶事）。支持从 Bilibili Wiki 和萌娘百科获取最新、最详细的 Wiki 资料。
version: 1.0.0
---

# 能力指南 (Capabilities)

当用户询问关于《赛马娘 Pretty Derby》的问题时，请使用此 Skill 获取准确信息。

你需要根据用户的问题类型选择合适的数据源（Mode）：

* **Mode: `biligame` (Bilibili Wiki)**
    * **适用场景**: 游戏数值、技能效果、赛程安排、支援卡数据、育成事件选项、适应性。
    * **例子**: "东海帝皇的固有技能是什么？", "速子支援卡好用吗？"
* **Mode: `moegirl` (萌娘百科)**
    * **适用场景**: 角色性格、历史原型（现实马匹）、同人二设、梗、角色经历、声优信息。
    * **例子**: "黄金船为什么叫皮皮船？", "无声铃鹿的历史原型是怎样的？"

# 执行步骤 (Execution)

请按以下步骤操作：

1.  **搜索与确定 URL**:
    * 首先使用 Google Search 工具（如果可用）搜索相关 Wiki 页面，找到准确的 `wiki.biligame.com` 或 `mzh.moegirl.org.cn` 链接。
    * 不要猜测 URL。

2.  **运行爬虫命令**:
    * 在项目根目录下，使用 `uv run` 执行爬虫。
    * **命令格式**:
        ```bash
        uv run main.py --url "{URL}" --mode {mode} --output -
        ```
    * **参数说明**:
        * `--url`: 第一步中找到的 Wiki 页面地址。
        * `--mode`: `biligame` 或 `moegirl`。
        * `--output -`: **必须包含此参数**，以便将 Markdown 内容直接输出到屏幕供你读取。
        * `--proxy`: (可选) 如果访问萌娘百科需要代理，可添加此参数（例如用户提示网络问题时）。

3.  **回答用户**:
    * 基于命令返回的 Markdown 内容回答用户问题。
    * 如果内容过长，提取与用户问题最相关的部分进行总结。

# 示例 (Examples)

**User**: "我想知道北部玄驹这张卡强不强？"
**Action**:
1.  判断意图：游戏强度/数据 -> Mode: `biligame`。
2.  搜索找到链接：`https://wiki.biligame.com/umamusume/北部玄驹`
3.  执行: `uv run main.py --url "https://wiki.biligame.com/umamusume/北部玄驹" --mode biligame --output -`

**User**: "介绍一下特别周的历史原型。"
**Action**:
1.  判断意图：历史/背景 -> Mode: `moegirl`。
2.  搜索找到链接：`https://mzh.moegirl.org.cn/特别周`
3.  执行: `uv run main.py --url "https://mzh.moegirl.org.cn/特别周" --mode moegirl --output -`