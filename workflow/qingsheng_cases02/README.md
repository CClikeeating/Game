# qingsheng_cases02

管道2：读取管道1的聊天话轮批次包，生成 qingsheng 案例卡和 eval 草稿。

## 输入

```text
outputs/source_to_chat_turns01/{batch_id}/
```

主入口是批次包内的 `batch_chat_turns.json`，来源追溯从同包的 `cases/{case_id}` 读取。

## 运行

```powershell
python -m workflow.qingsheng_cases02.pipeline --batch-id batch_001 --input-bundle outputs/source_to_chat_turns01/batch_001
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

`gold_reference` 优先学习原案例中真实发生的男方好回复；模型另写回复只作为备用。

阶段判断使用 `stage_judgment`：主阶段、阶段范围、策略阶段、模糊原因同时保留。
