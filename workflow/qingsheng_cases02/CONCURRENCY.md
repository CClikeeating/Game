# 管道2多案例并发说明

## 目的

管道2默认是一案一判。每个案例会分别调用：

- DeepSeek 主判断模型
- Qwen 复核模型

并发运行的含义不是把多个案例塞进同一个大模型 prompt，而是同时处理多个独立案例。这样可以减少等待时间，同时保持每个案例的数据边界清楚。

## 什么时候用

适合这些场景：

- 从多个管道1批次中抽样对比。
- 一次处理多个已经完成管道1的案例。
- 想让不同并发任务使用不同 `user_id`，方便服务侧隔离和日志追踪。

## 运行方式

准备一个 CSV 计划表，字段为：

```csv
batch_id,input_bundle,case_id
batch_001_data1html_5_cases,outputs/source_to_chat_turns01/batch_001_data1html_5_cases,data1html_005_next_valentine_day
batch_002_data1html_10_cases,outputs/source_to_chat_turns01/batch_002_data1html_10_cases,data1html_018_see_through_tricks
```

运行：

```powershell
python -m workflow.qingsheng_cases02.run_case_plan `
  --plan workflow/qingsheng_cases02/case_plan_template.csv `
  --output-batch-id batch_compare_001 `
  --max-workers 2
```

输出仍然是标准管道2批次包：

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

## user_id 分配

默认配置在：

```text
workflow/qingsheng_cases02/config/run_options.yaml
```

默认：

```json
{
  "case_plan": {
    "max_workers": 2,
    "user_id_strategy": "worker_index",
    "user_id_start": 1,
    "user_id_prefix": "",
    "fail_fast": false
  }
}
```

代码层硬上限为 50。即使命令行传入更大的数，也会被压到 50。

当 `max_workers=2`、`user_id_start=1` 时，并发任务会轮流使用：

```text
1
2
```

如果计划表某一行显式写了 `user_id`，则优先使用该行的值。

## 限流边界

`user_id` 主要用于服务侧隔离和追踪，不等于无限并发。

- DeepSeek 文档说明：普通 API 用户的所有 `user_id` 会合并计算并发限速；提升并发配额后，才会额外对每个 `user_id` 设置并发限制。
- 阿里云百炼文档说明：限流按主账号维度计算，账号下 RAM 子账号、业务空间和 API Key 的调用量合并计算。

因此建议测试阶段 `max_workers=2`。如果稳定，再逐步提高。

## 设计原则

- 不混案：每个模型请求只包含一个完整案例。
- 不覆盖：输出到新的 `output_batch_id`。
- 可追溯：manifest 和 model log 会记录 `worker_user_id`。
- 可恢复：单个 case 失败时默认不中断整个计划表。
