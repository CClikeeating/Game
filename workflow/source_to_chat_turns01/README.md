# source_to_chat_turns01

管道1负责把 html / pdf / 长图 / 图片文件夹转换成结构化聊天话轮。

## 边界

管道1只做事实级结构化：

- 判断发送方：`male`、`female`、`narration`、`system`、`unknown`
- 判断内容类型：`text`、`sticker`、`selfie_photo`、`life_photo`、`image`、`narration`、`system`、`unknown`
- 保留视觉事实：`visual_note`
- 保留来源追溯：`block_id`、`source_image`、`crop_box`
- 标记是否需要人工复核：`need_review`

管道1不判断：

- 这是不是 IOI/IOD
- 关系阶段
- 男生回复好坏
- 后续应该怎么回
- 这张自拍或表情包是否构成信号

这些解释工作属于管道2。

## 图片类规则

- 女生发的表情包：`speaker=female`，`content_type=sticker`
- 男生发的表情包：`speaker=male`，`content_type=sticker`
- 女生自拍/个人照片：`speaker=female`，`content_type=selfie_photo`
- 男生生活照：`speaker=male`，`content_type=life_photo`
- 无法归到具体类型的图片：`content_type=image`
- 复盘、讲解、教程、案例分析文本：`speaker=narration`，`content_type=narration`

复盘/讲解内容会保留给后续管道参考，但不能当成男女双方真实聊天发言。

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

生成或刷新人工复核表：

```powershell
python -m workflow.source_to_chat_turns01.refresh_batch_state outputs/source_to_chat_turns01/batches/batch_001
```

应用人工复核：

```powershell
python -m workflow.source_to_chat_turns01.apply_human_review outputs/source_to_chat_turns01/batches/batch_001 outputs/source_to_chat_turns01/batches/batch_001/human_review.xlsx
```

## 输出

```text
outputs/source_to_chat_turns01/batches/{batch_id}/
  handoff.json
  batch_manifest.json
  batch_chat_turns.json
  human_review.xlsx
  human_review_index.json
  cases/{case_id}/
    chat_turns.json
    chat_readable.md
    quality_report.json
    raw_model_results.json
    prepared_images/
    source_manifest.json
    block_manifest.json
```

管道2读取整个批次包根目录，不复制单个 JSON 文件。
