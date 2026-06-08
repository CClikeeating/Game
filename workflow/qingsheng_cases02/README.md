# qingsheng_cases02

管道2读取管道1的聊天话轮批次包，生成 qingsheng skill 可用的案例卡和 eval 草稿。

## 边界

管道2负责解释管道1给出的事实：

- 判断关系阶段和阶段范围
- 判断女方信号、男方信号或消极信号
- 判断男生表现画像，例如框架感、引导感、需求感、边界感和情绪稳定性
- 判断男生关键好回复和坏回复
- 生成 `case_card.json`
- 生成 advisory / autopilot eval
- 生成需要人工复核的冲突项

管道2不重新 OCR，不重新切图，也不修改原始素材。

## 如何使用管道1字段

管道1提供的 `speaker`、`content_type`、`visual_note` 是事实标签，不是关系判断。

- `content_type=sticker`：表情包或贴纸，只能作为情绪回应参考。
- `content_type=selfie_photo`：女生自拍/个人照片，可以作为信号候选，但必须结合上下文判断。
- `content_type=life_photo`：男生生活照，通常作为男方展示材料，不是女方信号。
- `content_type=image`：普通图片，需要结合上下文判断用途。
- `speaker=narration` 或 `content_type=narration`：复盘、讲解、教程或案例分析内容。它可以帮助理解案例，但不能当成男女双方真实聊天发言。

IOI/IOD、关系阶段、好坏回复、后续策略，都只能在管道2结合完整上下文后判断。

## 阶段与男生画像

阶段不是硬分类。管道2会同时保留：

- `primary_stage`：整体大阶段。
- `stage_range`：阶段跨度。
- `strategy_stage`：后续 skill/eval 应采用的策略阶段。
- `cross_stage_signals`：局部穿插信号，例如整体阶段4但出现阶段6亲密话题。

`case_facts.male_profile` 是男生表现画像，只作为倾向性参考，不是定死的人格判断。它用于帮助案例库总结男生在当前案例中的框架感、引导方式、需求感、沟通特质和证据 turn_id。

## 输入

```text
outputs/source_to_chat_turns01/batches/{batch_id}/
```

主入口是批次包里的 `handoff.json` 和 `batch_chat_turns.json`。来源追溯从同一批次包的 `cases/{case_id}` 读取。

## 运行

```powershell
python -m workflow.qingsheng_cases02.pipeline --batch-id batch_001 --input-bundle outputs/source_to_chat_turns01/batches/batch_001
```

应用人工复核：

```powershell
python -m workflow.qingsheng_cases02.apply_human_review --batch-id batch_001
```

## 输出

```text
outputs/qingsheng_cases02/{batch_id}/
  handoff.json
  batch_case_manifest.json
  batch_case_manifest.csv
  human_review.xlsx
  human_review_index.json
  model_call_log.json
  cases/{case_id}/
    case_card.json
    readable_case.md
    eval_advisory.json
    eval_autopilot.json
    case_quality_report.json
```

`case_card.json` 是下一阶段的主资产。`eval_advisory.json` 和 `eval_autopilot.json` 是测试题草稿。`human_review.xlsx` 只放模型冲突或关键不确定项。

## gold_reference 规则

`gold_reference` 优先学习原案例中真实发生、且被判断为有效的男方好回复。

模型新写的回复只能作为备用，不能覆盖原案例里已经存在的好回复。
