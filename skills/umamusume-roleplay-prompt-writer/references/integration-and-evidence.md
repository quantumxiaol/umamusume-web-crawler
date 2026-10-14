# 兼容性与调研依据

核对日期：2026-10-14。此文记录本 Skill 的设计依据，不是每张角色卡都要复制的内容。外部平台文档说明其自身行为；对本项目的改进建议是结合代码作出的判断，未经跨模型实验验证。

## 当前本地链路

以下链接假定三个项目并列放在同一父目录；相邻仓库不存在时，仍可按 Skill 默认格式产出。修改接入方式前应重新看实际代码，不能长期假定这一快照永远不变。

| 已核实实现 | 对制卡的影响 |
| --- | --- |
| build 的 [`_load_prompt`、`_build_character_config`、`build_characters`](../../../../umamusume-character-build/src/umamusume_character_build/character_builder.py) 读取顶层 `.md/.txt`，整段文本写入 `system_prompt` | 平铺角色文件正好匹配扫描方式；附录应放子目录，不能命名为顶层 `Almond_Eye.sources.md` 等文件，否则会被当成另一个角色。HTML 注释也会进入系统文本。 |
| 同一文件的 `_extract_names_from_prompt` 识别前 24 行中的“角色扮演提示词：中文名（English Name）”；文件 stem 的下划线转为空格参与名称匹配 | 保留标题形式和准确英文文件名，不随意给顶层角色文件加 `_v2`、`_notes` 等后缀。 |
| [`persona_extractor.py`](../../../../umamusume-character-build/src/umamusume_character_build/persona_extractor.py) 是未使用的占位模块；[`model.py`](../../../../umamusume-character-build/src/umamusume_character_build/model.py) 定义项目自有配置 | 不能假定 Markdown 各小节会被拆成酒馆字段，或 `personality` 已从正文抽取。项目配置不等于 Tavern V2。 |
| agent 的 [`LegacyDialogueContextBuilder.build`](../../../../umamusume-agent/src/umamusume_agent/dialogue/context.py) 拼接人设和回复指令；[`protocol.py`](../../../../umamusume-agent/src/umamusume_agent/dialogue/protocol.py) 定义 JSON、旧两行格式及 TTS 分离要求 | 卡内再硬写“必须 2—4 段 Markdown”会与宿主冲突。角色声音可以稳定，输出封装由运行端负责。 |
| 多人模式 [`CharacterSceneContextBuilder`](../../../../umamusume-agent/src/umamusume_agent/director/context.py) 追加场景、角色协议，导演决定回应者 | 人设不包办场景状态、其他角色的发言或轮次调度。开场不要永久覆盖实时场景。 |
| 上述读取与组装链路未实现酒馆宏、`first_mes`、`mes_example` 字段解析或世界书触发 | 默认使用普通文字；开场是可供宿主使用的素材，正文示例在当前实现中会随整份人设常驻。 |

因此采用“顶层纯人设 Markdown＋`_notes/` 中的作者资料和开场”。这是兼容当前构建器的文件组织，不是新发明的角色卡交换标准，也不要求本次修改 build 或 agent。

## 平台文档支持什么

### 开场与示例有价值，但没有统一配额

SillyTavern 明确把第一消息视为文风与长度示范，并说明示例对话如何插入上下文；示例也可被配置为保留。它没有规定全体模型必须采用固定篇幅、固定数量的例子或统一 token 上限。[Character Design](https://docs.sillytavern.app/usage/core-concepts/characterdesign/)

本项目据此保留少量可辨认的声音样本，另外准备真正的开场素材。没有直接证据支持强制追问、分歧或第二轮比单方样例更好；默认使用情境说明与角色单方台词，双向样例可选。示例中的用户形象可能影响模型对关系的推断，因此不替用户预设性格或承诺；这是设计风险判断，不是已测量的必然结果。示例数量和初稿字数不是“前 20 轮不漂移”的保证。开场作为系统文本的小节，与它成为聊天中的首条角色消息，是不同的接入方式。

### V2 是数据规范，运行行为还取决于前端

[Character Card V2 规范](https://github.com/malfoyslastname/character-card-spec-v2/blob/main/spec_v2.md) 定义字段及交换结构，明确作者注释元数据不应进入提示词。它不能证明所有角色聊天平台完整支持相同的导入格式。实际 ST 的角色提示覆盖还受用户开关影响。

此外，消息角色、位置和深度可由前端配置；不能将“某字段写在最前面”笼统等同于所有 API 上的最高指令权限。[Prompt Manager](https://docs.sillytavern.app/usage/prompts/prompt-manager/)

本项目默认不使用宏，是因为读取链路没有宏替换；固定角色的真名并非不可移植的错误。用户姓名则无需硬编码。以后导出酒馆时再按目标语法转换。

### 世界书和作者注释是运行功能

世界书依赖前端按关键词等条件注入，短小、自足的条目有利于管理预算；普通 Markdown 标题不能实现按需加载。[World Info](https://docs.sillytavern.app/usage/core-concepts/worldinfo/)

作者注释可配置位置和插入频率，适合承载场景性的提醒；“默认深度一定为 4”不应写成本项目事实。[Author's Note](https://docs.sillytavern.app/usage/core-concepts/authors-note/)

静态设定与临时状态分开有维护价值。是否能节省 API 费用、获得前缀缓存命中，仍取决于提供商、模型和实际消息组装，不能靠角色卡作统一保证。

## 2025 年论文结论的适用范围

《Talk Less, Call Right》研究 CPDC 2025 中带工具的角色对话。RRP 的总体分数为 0.571，基线为 0.519；上下文对话子项中，人工改进提示为 0.617，RRP 为 0.611。文章将主要进步归于更可靠的工具调用，并明确其适用范围有限。[论文原文，表 1 与 Limitations](https://arxiv.org/html/2509.00482v1)

作者团队公布的是 API 赛道第 8 名，不是冠军。[Typhoon 团队报告](https://opentyphoon.ai/blog/en/emnlp-2025)

可借鉴的是把人物声音、场景状态与执行规则讲清楚；不能据此宣称“规则列表全面胜过叙事”“3—5 例能保证长聊不漂移”，也不能把特定比赛的一次工具调用上限抄进赛马娘卡。

## 旧卡的具体改进点

检查对象为旧版 [Almond_Eye.md](../../../results/roleplay_prompt/Almond_Eye/Almond_Eye.md)。以下是文本和接入评审，没有将旧卡内容再次认定为官方事实：

| 旧卡表现 | 应怎样改 |
| --- | --- |
| 开头让模型扮演杏目，“互动目标”却写“作为训练员，回应杏目” | 统一模型身份；角色目标写杏目怎样回应用户。 |
| 人物反差、语气和边界有辨识度，但若干条写成“绝不畏惧”“唯一依靠”等绝对判断 | 核对原剧情，补场合、阶段和亲疏条件，让人设能处理失败、拒绝与关系变化。 |
| 关系表夹入现实母系关系；玩家外号和游戏设定同层出现 | 按来源分类核实，不能用现实原型替游戏建立家庭关系。 |
| 语录没有出处，原创演绎与游戏原句容易混淆 | 少量原句可追溯；翻译标译文，原创对话另列。 |
| 示例以单方台词为主 | 保留这一形式，补充适用情境与语气差异；确有需要再选双向样例，多轮表现由实测检查。 |
| “整体输入即可启动”的作者说明也会被构建成系统提示词 | 移至作者资料；正文每句都服务于扮演。 |
| 没有实际第一消息 | 附属文件提供具体开场供宿主使用，避免让固定开场变成每轮当前场景。 |

无需推倒原有八部分；主要收益来自证据质量、主体一致、条件化行为、声音示范，以及对实际运行方式的尊重。单纯增加标题、负面禁令或字数不能证明效果更好。

## 仅在要求 Tavern V2 导出时使用的映射

下表是本项目内容到字段的建议拆分，不是对现有 build 的描述。真正导出时读取目标规范并校验完整 schema；无需为了填空而制造额外设定。

| 字段 | 内容来源与注意事项 |
| --- | --- |
| `name` | 中文显示名；英文／日文身份另行保留。 |
| `description` | 世界、身份、关键经历、关系和必要语言特征。 |
| `personality` | 关键行为模式的简短摘要；减少与 description 重复。 |
| `scenario` | 选定开场的关系与起点；不能同时塞进多个互斥场景。 |
| `first_mes` | 附属文件中的主开场第一消息。 |
| `alternate_greetings` | 其他可选第一消息；必要的场景差异应在消息自身交代。 |
| `mes_example` | 对话样例；按目标前端使用 `<START>`、`{{user}}:`、`{{char}}:`。不整份复制人设。 |
| `creator_notes` | 作者说明、来源、原创与二设边界；不进入运行提示。 |
| `system_prompt`、`post_history_instructions` | 默认留空以使用宿主配置；有明确需求再编写，不夹入破限内容。 |
| `character_book` | 可选的低频补充信息；需实际支持触发机制。 |

V2 的 `spec`、`spec_version`、`data` 及其他必需键按规范填写；不要把本表当成完整 JSON schema。未知扩展在改已有卡时保留。Author's Note 的配置也不要误当成 V2 核心必需字段。
