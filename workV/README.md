# workV MVP v0.1

`workV` 是新版 MVP 的干净工作区。它不替代旧项目，也不改管道1；它读取旧管道1产出的完整聊天整案，生产新版结构化片段库，并提供本地回复测试台。

## 定位

新版 MVP 面向男性用户的初识阶段聊天辅助工具，覆盖：刚认识、破冰、熟悉、暧昧升温、邀约到第一次线下见面/关系推进前。

暂不覆盖：分手挽回、复合、长期关系经营、婚恋咨询、复杂情感咨询、亲密升级、Kino、LMR、确立关系。

核心风格：高框架、低压力、可推进、有边界、不油腻、不跪舔、不查户口。

## 完整流程

```text
旧管道1整案
-> workV/case_production 生成 segments_v01
-> human_review_segments.xlsx 人工复核
-> approved segments
-> workV/knowledge 生成本地片段索引
-> workV/runtime 文本/截图输入
-> 标签判断
-> 本地相似片段检索
-> 回复生成
-> workV/web 展示和反馈
```

## 目录

```text
workV/
  config/                 新版标签、原则、模型、检索、Web 配置
  prompts/                案例拆解、片段复核、局势标签、回复生成 Prompt
  case_production/        整案 -> 片段；复核表应用
  knowledge/              本地片段知识库索引与检索
  runtime/                文本/截图 -> 标签 -> 检索 -> 回复
  web/                    本地回复测试台
  outputs/                workV 输出，不影响旧 outputs
```

## 标签体系

标签配置在 `workV/config/taxonomy_v01.json`。

- 聊天阶段：刚认识、破冰期、熟悉期、暧昧升温期、邀约期
- 女生状态：热情、正常、低投入、冷淡、防御、拒绝
- 男生目标：破冰、接话、延续话题、升温、邀约、降压
- 推荐策略：轻松开场、轻微调侃、共情回应、话题延展、情绪升温、模糊邀约、明确邀约、主动降压
- 风险类型：查户口、连续追问、太正经、过度讨好、油腻、强行暧昧、强行邀约、解释施压、长篇大论、无视边界
- 回复强度：安全、轻松、调侃、暧昧、推进

片段内部还支持可选 `次要标签`。主标签只放当前节点最主要判断；边界判断、辅助判断或趋势说明放入 `次要标签`，用于弱检索和人工理解，不替代主标签。

## Prompt 原则

原则配置在 `workV/config/prompt_principles.json`，包括：框架意识、需求感管理、低压力、主动引领、话题从事实转感受、IOI/IOD 趋势、轻微调侃、邀约三步法、尊重边界、冷读、拉扯、展示价值、废物测试、软抗拒、主动降压。

已从旧管道2 Prompt 借鉴的写法：

- 事实解释分层：旧管道1只给 speaker/content_type/visual_note 等事实层信息，新版模型才做阶段、状态、风险、策略解释。
- 证据引用：片段判断必须能追溯 `source_turn_ids`。
- 防结果倒推：不能因为整案最后成功，就把当前节点硬判为高投入、高阶段或好回复。
- 缺失背景保护：截图/长图可能不完整，要区分“已见证据”和“可能缺失背景”。
- 真实回复优先：优先学习原案例真实发生且有效的男方动作；如果男生原回复已经有效，建议回复优先保留原回复，不为了改写而改写。
- 有效原回复保护：主模型判断原回复有效时，不强行生成更油、更刻意或更模型腔的“更优回复”。
- 主次标签：六类基础标签只放当前节点最主要判断，边界判断或辅助判断放入 `次要标签`。
- 暧昧试探边界：女生正常/热情且上下文接受玩笑时，轻微暧昧可理解为试探或升温；女生冷淡、防御、拒绝、无投入时仍硬撩，才算强行暧昧。
- 旁白隔离：复盘、教程、讲解材料可以辅助理解，但不能当作真实聊天发言。
- 局部信号隔离：局部高热度信号只作为趋势说明，v0.1 不扩展到亲密升级、Kino、LMR、确立关系。

这些是 Prompt 原则，不是 v0.1 复杂标签。

## 案例生产

输入是旧管道1的 batch 目录。案例生产已经对齐旧管道2的运行方式：多个 case 之间并发，每个 case 内部仍然按 DeepSeek 主拆分 -> Qwen 复核串行执行，不混案。

并发配置在 `workV/config/run_options.json`，默认：

```json
{
  "max_workers": 2,
  "user_id_strategy": "worker_index",
  "user_id_start": 1,
  "fail_fast": false,
  "overwrite": false
}
```

Dry-run 只生成 Prompt 预览，不调用模型：

```powershell
python -m workV.case_production.build_segments `
  --input-bundle outputs/source_to_chat_turns01/batches/batch_003_remaining_html `
  --output-batch-id batch_003_segments_v01_preview `
  --case-limit 3 `
  --max-workers 2 `
  --dry-run
```

真正调用模型生成：

```powershell
python -m workV.case_production.build_segments `
  --input-bundle outputs/source_to_chat_turns01/batches/batch_003_remaining_html `
  --output-batch-id batch_003_segments_v01_first3 `
  --case-limit 3 `
  --max-workers 2
```

如果重复使用同一个 `--output-batch-id`，需要显式加 `--overwrite`，否则会阻止覆盖已有结果。

输出位置：

```text
workV/outputs/segments/{batch_id}/
  segments_manifest.json
  case_plan_run_log.json
  human_review_segments.xlsx
  model_call_log.json
  cases/{case_id}/
    case_outline.json
    segments.json
    model_review.json
```

## 人工复核

打开 `human_review_segments.xlsx` 的 `segments_review` sheet。复核表是给人工判断用的 xlsx，不会被 JSONL 流程替代。

关键列说明：

- `原文连接/定位`：源 `turn_id` 和对应截图路径，用来回到旧管道1原文位置。
- `背景介绍`：主模型对该片段背景的简短概括。
- `当前上下文`：源节点上下各 10 句聊天原文，带 `*` 的行是该片段引用的关键 turn。
- `主模型原回复评价` / `主模型标签` / `主模型建议回复` / `主模型迁移学习价值` / `主模型判断理由`：DeepSeek 主模型的结构化判断。`主模型标签` 会同时展示主标签和可选次要标签。
- `复核模型结论` / `复核模型修改建议`：Qwen 复核模型对主模型的意见，已经转成中文，不再塞原始 JSON。
- `需要你复核的问题`：说明这一行要怎么判断。
- `人工结论`：人工最终选择。
- `人工修正`：当选择“手工修正”时，建议写 JSON 字段补丁，例如 `{ "聊天阶段": "破冰期", "更优回复": "保留原回复：..." }`。如果只写一句判断说明，系统只会保存为人工说明并保持 `needs_review`，不会把它当成可发送回复。

如果 `主模型建议回复` 为“保留原回复...”且复核模型没有修改意见，该片段会自动标为 `approved`，不进入人工待审表。

`人工结论` 可选：

- 通过：认可主模型当前字段。
- 按复核模型修改：采用 Qwen 复核模型提出的修改建议。
- 手工修正：按 `人工修正` 列的 JSON 字段补丁覆盖字段；纯文字说明不会直接入库。
- 拒绝：该片段不用。
- 暂不启用：保留但不进入知识库。
- 跳过：本轮先不处理。

应用复核：

```powershell
python -m workV.case_production.apply_review --batch-id batch_003_segments_v01
```

只有 `quality_status=approved` 的片段默认进入本地知识库。选择“按复核模型修改”会应用 Qwen 提出的字段级修改；如果复核模型认为原回复更好，应把建议回复改成“保留原回复：原句”。

## 本地片段知识库

生成本地索引：

```powershell
python -m workV.knowledge.build_segment_index --batch-id batch_003_segments_v01
```

默认输出：

```text
workV/outputs/indexes/segments_index.jsonl
```

### 新版片段资产导出

旧管道3不是把整案拆成新版片段，它的主要价值是资产化方式：结构化 JSONL、干净经验包、RAG markdown、上传 manifest、评测资产。

新版 v0.1 已补 `workV.knowledge.build_segment_assets`，默认只导出 `quality_status=approved` 的片段；人工复核仍然使用 `human_review_segments.xlsx`，不会被 JSONL 流程替代。

导出 approved 片段资产：

```powershell
python -m workV.knowledge.build_segment_assets --batch-id batch_003_segments_v01_first3
```

测试或调试时可以包含未通过人工复核的片段：

```powershell
python -m workV.knowledge.build_segment_assets --batch-id sample --include-unapproved
```

默认输出：

```text
workV/outputs/segment_assets/{batch_id}/
  build_summary.json
  learning_cases/
    segment_cases_index.json
    segment_cases_index.jsonl
  experience_pack/
    segment_experience_pack.json
    segment_experience_pack.jsonl
  rag_knowledge_base/
    segments/*.md
    segments_index.jsonl
    upload_manifest.csv
    rag_build_summary.json
```

原则：新版知识库以 `segments_v01` 为主，不直接复用旧 `case_card` schema；旧管道3复用的是“导出形态和清洁资产思路”。

检索测试：

```powershell
python -m workV.knowledge.search_segments --query "她只回哈哈 我怎么回"
```

v0.1 默认使用本地片段索引，不默认使用旧百炼 `file_search`，避免旧知识库污染新版标签和风格。

## 回复 runtime

文本 dry-run：

```powershell
python -m workV.runtime.reply_engine `
  --question "她只回我哈哈，我下一句怎么回？" `
  --context "微信认识三天，还没见面" `
  --dry-run
```

真实模型调用：

```powershell
python -m workV.runtime.reply_engine `
  --question "她只回我哈哈，我下一句怎么回？" `
  --context "微信认识三天，还没见面"
```

截图输入：

截图理解现在使用 `workV/prompts/image_understanding_v01.md`，不再沿用旧 `qingsheng-skill` 图片理解 Prompt；dry-run 下不会调用视觉模型。

```powershell
python -m workV.runtime.reply_engine `
  --question "帮我看截图，她什么意思，我该怎么回？" `
  --context "微信认识三天，还没见面" `
  --image D:\path\to\chat.jpg
```

输出会包含：推荐回复、教练分析、标签、风险提醒、下一步建议、参考片段、模型耗时与 token。

## Web 测试台

启动：

```powershell
cd "D:\聊天\白鸥等1个文件\白鸥"
python -m workV.web.serve
```

或双击根目录：

```text
start_workV_web.cmd
```

访问：

```text
http://127.0.0.1:7870
```

页面支持：

- 当前聊天/用户问题输入
- 补充背景
- 聊天截图上传
- dry-run
- 标签展示
- 推荐回复
- 风险提醒
- 下一步建议
- 参考片段展示
- 模型耗时与 token 展示
- 有用/一般/不合适反馈记录

反馈会写入：

```text
workV/outputs/web/runs/{run_id}/summary.json
```

## 与旧项目的关系

复用：

- 旧管道1整案输出
- 旧模型 API key 环境变量
- 旧截图理解能力
- 旧复核表思路

不默认使用：

- 旧 7 阶段标签
- 旧 `case_card` schema
- 旧 eval/advisory/autopilot 资产
- 旧百炼 file_search 知识库
- 旧完整 `qingsheng-skill/SKILL.md` 长 Prompt

## 当前产品问题与下一步工作重点

当前产品链路已经跑通，但效果还没有稳定到可用。2026-06-12 用 `tt/1 (1).jpg` 做真实对照后确认：

- 原质量模式（三次调用）约 75 秒：截图理解约 7-9 秒，标签判断约 23 秒，回复生成约 45 秒。
- 百炼 RAG 快速模式在开思考时仍约 74 秒，慢点主要来自 `qwen3.7-plus` 的 reasoning tokens 和百炼知识库长上下文。
- 百炼 RAG 快速模式关思考后可降到约 19 秒；同时保持 `file_search.tool_choice=required`、`max_num_results=3`，仍会参考知识库。
- 关思考后的典型质量问题：模型能学到“轻松接住、低压力、不继续纠结”，但容易漏掉“转移话题/抛出可接话口”。例如回复“那正好，我也缺个聊天搭子”方向正确，但没有给女生一个容易接下去的话题入口。

当前应并行推进两条线：

1. 案例生产线：继续生产和复核高质量片段，优先补“女生想聊/睡不着/无聊/陪我聊会儿”“女生否认暧昧但保留窗口”“男生需要从暧昧试探转到轻松话题入口”等场景。重点沉淀可迁移动作：女生给聊天窗口时，不只表态接住，还要顺手给一个可接的话题入口。
2. 产品测试线：继续 A/B 测试质量模式、百炼 RAG 快速模式、候选更强模型（如百炼控制台可用的 3.7 Max/Max 类模型）和轻量二次修正。评估项拆成：是否识别女生窗口、是否避免继续追问、是否轻松接住、是否转移原压力、是否抛出可接话口、是否像真人微信、总耗时是否可接受。

后续产品端规则建议：

- 快速模式继续关思考以保证速度，但 Prompt 需要补“动作约束”。
- 当女生表达“想聊/睡不着/无聊/陪我聊会儿”时，推荐回复必须包含一个轻量话题入口，不能只输出态度句。
- 可增加快速模式自检：如果 `reply` 只表达态度、没有提供话题入口，则重写为“接住 + 轻松转移 + 可接话口”。
- 质量模式继续作为慢但稳的效果基准，用于对照和案例回收。

## 暂未改/暂缓项

这些内容目前没有假装已经完成，先明确记录在这里：

- 真实旧案例拆片段已完成一轮小批量验证：`batch_003_remaining_html` 前 5 个案例已生成 `batch_003_segments_v01_first5`，并通过人工 xlsx 应用过复核结果。当前状态为 13 条 approved、5 条 needs_review、1 条 disabled；大批量拆分仍暂缓，先用这批校准 Prompt 和复核表。
- 外部知识库暂未接入：新版默认使用本地 `segments_index.jsonl`，没有默认接旧百炼 `file_search`，也没有自动上传 `rag_knowledge_base`。
- 向量检索暂未做：当前相似片段检索是标签权重 + 文本命中，后续再加 embedding/向量库或外部知识库检索。
- 评测集暂未生成：新版已导出经验包和 RAG markdown，但还没有像旧管道3那样生成 `test_questions/*.json` 和自动评测 runner。
- 复核表仍是 MVP 版 xlsx：保留 `human_review_segments.xlsx`，已展示主模型判断、复核模型结论、原文定位、背景介绍和上下 10 句上下文；后续可继续增强成更细的影响说明和批量质检表。
- 图片理解客户端暂未完全迁出旧 runtime04：Prompt 已换成 `workV/prompts/image_understanding_v01.md`，但底层通用视觉调用客户端仍复用旧 runtime04 的 `RuntimeModelClient`。
- 产品网页仍是测试台：当前 `workV/web` 用于本地验证输入、截图、模型耗时、参考片段和反馈，不是最终产品端 UI。
- OCR、小程序、复杂话术库、用户账号、历史会话管理暂缓。

## 注意

`workV` 是 v0.1 最小闭环，不是最终产品。第一版目标是先验证：片段质量、标签判断、片段检索、回复风格和用户反馈。
