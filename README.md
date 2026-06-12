# Baiou 主线

当前项目主线只维护 `baiou/`。历史模块已经从当前项目移除，不参与新流程运行、测试和开发。

## 主线流程

```text
data/raw/*
  -> baiou.source_pipeline
  -> outputs/baiou/source
  -> baiou.case_pipeline.production
  -> outputs/baiou/cases/segments
  -> baiou.case_pipeline.knowledge
  -> outputs/baiou/cases/knowledge/current
  -> baiou.product
  -> outputs/baiou/product
```

## 1. 管道1：素材到聊天话轮

负责把 html、pdf、长图、图片或图片文件夹转成结构化聊天话轮，并生成复核表。

主要产物：

```text
outputs/baiou/source/prepared/{source_id}/
outputs/baiou/source/case_runs/{case_id}/
outputs/baiou/source/batches/{batch_id}/
```

关键文件：

```text
source_manifest.json
block_manifest.json
chat_turns.json
chat_readable.md
batch_chat_turns.json
handoff.json
human_review.xlsx
```

## 2. 管道2：案例片段生产

负责从管道1的 source batch 生成 `segments_v01`，并产出人工复核表。复核后只有 `approved` 片段进入管道3；`disabled` 片段统一留在本批次汇总表里。

主要产物：

```text
outputs/baiou/cases/segments/{batch_id}/
```

关键文件：

```text
segments_manifest.json
human_review_segments.xlsx
disabled_segments.xlsx
disabled_segments.jsonl
case_outline.json
segments.json
model_review.json
```

## 3. 管道3：知识库构建

负责把管道2里所有 `approved` 片段合并进持续累积的当前知识总库，并生成本地检索索引和 RAG 上传文档。产品层默认只读取当前总库。

主要产物：

```text
outputs/baiou/cases/knowledge/current/
outputs/baiou/cases/knowledge/imports/{batch_id}/
```

关键文件：

```text
current/segments.jsonl
current/local_index/segments_index.jsonl
current/rag_knowledge_base/segments/{batch_id}_{timestamp}/{segment_id}.md
current/rag_knowledge_base/upload_manifest.csv
imports/{batch_id}/import_summary.json
imports/{batch_id}/imported_segments.jsonl
imports/{batch_id}/skipped_segments.jsonl
```

## 4. 产品层

负责文本/截图输入、标签判断、本地案例片段检索、百炼 RAG 快速模式、回复生成和网页测试台。

主要产物：

```text
outputs/baiou/product/uploads/{run_id}/
outputs/baiou/product/runs/{run_id}/summary.json
outputs/baiou/product/feedback.jsonl
```

启动网页：

```powershell
python -m baiou.product.web.serve
```

或双击：

```text
run_baiou_web.cmd
```

## 配置

配置集中在：

```text
baiou/config/source_pipeline/
baiou/config/case_pipeline/
baiou/config/product/
```

常用环境变量：

```text
BAIOU_OUTPUT_ROOT
BAIOU_WEB_CONFIG
BAIOU_WEB_HOST
BAIOU_WEB_PORT
BAIOU_WEB_OUTPUT_ROOT
BAIOU_REPLY_MODE
BAIOU_VECTOR_STORE_IDS
DASHSCOPE_API_KEY
DEEPSEEK_API_KEY
```

## 保留目录

- `baiou/`：当前唯一主线代码。
- `tests/`：当前主线测试。
- `data/`：原始素材输入。
- `tt/`：临时真实产品流测试素材，需要保留。
- `outputs/baiou/`：主线运行产物。
