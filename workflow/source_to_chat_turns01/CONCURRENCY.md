# 管道1多案例并发说明

## 目的

管道1负责把已经切好的素材块交给视觉模型，输出结构化聊天话轮。

并发运行的含义是：同时处理多个独立案例。每个案例内部仍然按图片 group 顺序调用模型，不把多个案例混进同一个请求。

## 运行方式

准备 CSV 计划表：

```csv
case_id,source_output,mode,limit,user_id
data1html_001_three_day_emoji_girl,data1html_001_three_day_emoji_girl,group,,
data1html_020_truth_sleep_ten_thousand_times,data1html_020_truth_sleep_ten_thousand_times,group,,
```

运行：

```powershell
python -m workflow.source_to_chat_turns01.run_case_plan `
  --plan workflow/source_to_chat_turns01/case_plan_template.csv `
  --batch-id batch_parallel_001 `
  --max-workers 2
```

运行后会先写入：

```text
outputs/source_to_chat_turns01/_case_runs/{case_id}/group/
```

然后自动 collect 成标准管道1批次包：

```text
outputs/source_to_chat_turns01/batches/{batch_id}/
  handoff.json
  batch_manifest.json
  batch_manifest.csv
  batch_chat_turns.json
  human_review.xlsx
  cases/{case_id}/
```

## 并发上限

配置文件：

```text
workflow/source_to_chat_turns01/config/run_options.yaml
```

默认 `max_workers=2`。

代码层硬上限为 50。即使命令行传入更大的数，也会被压到 50。

## user_id

默认按 worker 分配：

```text
1
2
3
...
```

如果计划表某一行写了 `user_id`，则优先使用该行的值。

`user_id` 用于模型服务侧隔离和日志追踪，不代表可以绕过账号总限流。

## 设计原则

- 不混案：一个视觉模型请求只包含同一个案例的一组图片。
- 不覆盖：用新的 `batch_id` 输出新批次。
- 可追溯：单案输出和标准批次包都会保留。
- 可恢复：单个 case 失败时默认不中断整个计划表。
