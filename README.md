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
## v0.2 handoff

Before continuing v0.2 work, read:

```text
baiou/V02_HANDOFF.md
```

It records the current integration branch, parallel product/case branches, cleaned 455-doc RAG library, product eval table rules, and handoff risks.

## 产品端部署状态与待办

详细 PM 汇报见：

```text
baiou/product/DEPLOY_PM_REPORT.md
```

当前服务器内测后端已经部署到：

```text
http://101.133.161.248
```

当前已完成：

- 小程序 API 后端部署，服务名 `baiou`，Nginx 反代到本机 `127.0.0.1:7871`。
- 百炼 RAG 快速模式和质量模式可用，服务器只保留百炼知识库 ID，不再保存本地 455 条知识库正文。
- 反馈写入、后台统计、反馈 CSV 导出已接入。
- 截图和模型运行明细保留周期默认 30 天，服务器每天凌晨自动清理。
- 后端已支持微信 `wx.login` 登录链路，但服务器还没有配置小程序 `AppSecret`，当前仍保留内测登录回退。

备案通过前暂不做或不能正式启用：

- 域名解析到服务器公网 IP。
- HTTPS 证书配置。
- 微信小程序后台 request/uploadFile 合法域名配置。
- 小程序正式版 `apiBaseUrl` 切换到 `https://正式域名`。
- 小程序提交审核和公众开放。

备案通过后的接入顺序：

```text
1. 域名解析到 101.133.161.248
2. 配置 HTTPS 证书
3. Nginx 增加正式 server_name
4. 小程序 apiBaseUrl 改为 https://正式域名
5. 微信后台配置合法域名
6. 真机测试上传、回复、反馈、后台统计
7. 提交小程序审核
```

正式开放前建议补齐：

- 在微信公众平台获取小程序 `AppSecret`，服务器配置 `BAIOU_WECHAT_SECRET`。
- 关闭内测登录：`BAIOU_MINIPROGRAM_DEV_LOGIN=false`。
- 改掉已经在对话中出现过的服务器 root 密码，改用 SSH key 登录。
- 管理后台 token 仅在服务器环境变量中保存，不写入前端或公开文档。
