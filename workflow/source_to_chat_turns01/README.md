# source_to_chat_turns01

管道1：把 html / pdf / 长图 / 图片文件夹转成结构化聊天话轮。

## 输入

原始素材放在：

```text
data/raw/html
data/raw/pdf
data/raw/images
data/raw/folders
```

## 运行

准备图片块：

```powershell
python -m workflow.source_to_chat_turns01.source_preparation html "data/raw/html/example.html" --run-id case_001
```

调用视觉模型识别话轮：

```powershell
python -m workflow.source_to_chat_turns01.run_pipeline --case-id case_001 --source-output case_001 --mode group
```

收集成批次包：

```powershell
python -m workflow.source_to_chat_turns01.collect_batch batch_001 case_001
```

## 输出

```text
outputs/source_to_chat_turns01/{batch_id}/
  handoff.json
  batch_manifest.json
  batch_chat_turns.json
  human_review.xlsx
  cases/{case_id}/
    chat_turns.json
    chat_readable.md
    quality_report.json
    raw_model_results.json
    prepared_images/
    source_manifest.json
    block_manifest.json
```

管道2读取整个批次包根目录，而不是单独复制 `batch_chat_turns.json`。
