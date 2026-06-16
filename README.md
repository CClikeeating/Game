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

## 产品端云部署交接（2026-06-16）

当前 `main` 已包含产品网页 alpha、后台管理和额度控制，最近一次已验证提交：

```text
e0c0919 Refine web upload UX and trusted proxy IP handling
```

本地全量测试已通过：

```powershell
$env:PYTEST_ADDOPTS='--basetemp=.pytest_tmp_polish_admin_main'
python -m pytest -q
# 64 passed
```

当前服务器内测入口：

```text
用户网页：http://101.133.161.248/app
管理后台：http://101.133.161.248/admin
健康检查：http://101.133.161.248/api/v1/health
```

当前服务器 release：

```text
/opt/baiou/releases/release_20260616_090640_polish_admin
```

### 已完成的产品端能力

- `/app` 用户网页 alpha：
  - 内测访问码登录。
  - 手机端优先，同时适配桌面端。
  - 上传聊天截图、输入问题、补充背景、选择快速/质量模式、生成推荐回复。
  - 普通用户页面不展示“截图理解”和“参考片段”；这些只保留在后端/admin 调试数据里。
  - 上传区显示已选择图片数量、文件名、大小，并做格式/大小/数量校验。
  - 生成时显示等待阶段和等待秒数。
  - 快速模式扣 1 次额度，质量模式扣 2 次额度。
  - dry-run 不扣真实额度。

- `/admin` 管理后台：
  - 使用 `Authorization: Bearer <BAIOU_ADMIN_TOKEN>`，token 不放 URL。
  - 查看全站统计、今日全站额度、已用、剩余。
  - 查看用户列表、最近登录 IP 脱敏展示、IP hash、今日用量、总用量、最近活动时间。
  - 查看 IP 今日用量。
  - 支持单用户每日额度覆盖。
  - 支持单用户禁用（额度 0）和清空覆盖额度。
  - 支持动态配置全局每日额度、IP 每日额度、全站每日额度、模式扣费、RAG 知识库 ID 和召回数量。
  - 支持反馈查看和 CSV 导出。

- 服务端安全和成本控制：
  - Gunicorn 绑定 `127.0.0.1:7871`，公网只通过 Nginx 80 端口访问。
  - `BAIOU_MINIPROGRAM_DEBUG=false`。
  - `BAIOU_MINIPROGRAM_DEV_LOGIN=false`。
  - IP 限额、用户限额、全站额度三层同时生效。
  - 后台 IP 记录只信任 `BAIOU_TRUSTED_PROXY_IPS` 中的代理地址，避免直接信任客户端伪造的 `X-Forwarded-For`。

### 当前线上关键配置

这些值在服务器环境变量中配置，不应写入代码、README、截图或聊天记录：

```text
DASHSCOPE_API_KEY
DEEPSEEK_API_KEY
BAIOU_ADMIN_TOKEN
BAIOU_WEB_ACCESS_CODES 或 BAIOU_WEB_ACCESS_CODE_HASHES
BAIOU_WECHAT_SECRET
```

当前建议公开配置项：

```text
BAIOU_OUTPUT_ROOT=/opt/baiou/shared/outputs
BAIOU_ADMIN_CONFIG=/opt/baiou/shared/admin_config.json
BAIOU_MINIPROGRAM_DB=/opt/baiou/shared/app.db
BAIOU_MINIPROGRAM_UPLOAD_ROOT=/opt/baiou/shared/uploads
BAIOU_MINIPROGRAM_HOST=127.0.0.1
BAIOU_MINIPROGRAM_PORT=7871
BAIOU_MINIPROGRAM_DEV_LOGIN=false
BAIOU_MINIPROGRAM_DEBUG=false
BAIOU_SESSION_DAYS=30
BAIOU_REPLY_MODE=bailian_rag_fast
BAIOU_VECTOR_STORE_IDS=n7s0ou2dpt
BAIOU_RAG_MAX_NUM_RESULTS=3
BAIOU_UPLOAD_RETENTION_DAYS=30
BAIOU_RUN_RETENTION_DAYS=30
BAIOU_WEB_IP_DAILY_QUOTA=20
BAIOU_WEB_SITE_DAILY_QUOTA=500
BAIOU_MODE_UNIT_COSTS=bailian_rag_fast=1,bailian_rag_quality=2
BAIOU_TRUSTED_PROXY_IPS=127.0.0.1,::1
```

### 云部署必须保留的持久化数据

如果迁移到云平台，不能只部署代码。下面这些路径必须放到持久化磁盘、数据库或对象存储中：

```text
/opt/baiou/shared/app.db
/opt/baiou/shared/admin_config.json
/opt/baiou/shared/uploads/
/opt/baiou/shared/outputs/
/opt/baiou/shared/logs/
```

其中 `app.db` 保存用户、会话、回复记录、反馈、每日额度、IP 用量、单用户额度覆盖和登录事件。丢失后不会影响代码启动，但会丢失运营数据和后台管理状态。

### 云部署运行方式

当前服务是 Flask + Gunicorn，不需要单独前端构建步骤。

依赖安装：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

启动命令：

```bash
.venv/bin/gunicorn --workers 2 --threads 2 --timeout 240 --bind 127.0.0.1:7871 'baiou.product.api.app:create_app()'
```

云平台如果要求直接监听平台端口，可以把 bind 改成平台提供的 `$PORT`，但要确认：

- 外层反代会覆盖或正确设置 `X-Real-IP` / `X-Forwarded-For`。
- `BAIOU_TRUSTED_PROXY_IPS` 只配置可信代理地址。
- 管理后台仍然必须带 `Authorization` header。

### 部署后验证清单

基础检查：

```bash
curl -fsS http://127.0.0.1:7871/api/v1/health
```

公网检查：

```text
打开 /app，确认能看到访问码页。
输入内测码，确认能进入用户页。
上传 1 张图，确认页面显示“已选择 1 张”。
快速模式跑一次，确认返回 model_success。
质量模式跑一次，确认等待状态可见，且额度扣 2。
打开 /admin，输入 admin token。
确认 stats、users、ip-usage、feedback 都能加载。
确认全站每日额度为 500。
```

### 当前已知注意事项

- 当前内测仍是 HTTP，不适合长期公开传播真实用户截图；正式开放前建议配置域名和 HTTPS。
- 用户截图属于隐私数据，必须保留清理任务。当前代码提供 `baiou.product.api.cleanup`，服务器应定时执行。
- 当前网页 alpha 已经可用，但还不是完整商业化产品：没有支付、没有正式账号系统、没有微信小程序正式发布链路。
- 质量模式会比快速模式慢，前端已有等待提示和 90 秒超时；如果后续模型调用经常超过 90 秒，需要调大前端超时时间或改成异步任务轮询。
- 管理后台可以动态调额度，但环境变量仍会在服务重启后作为基础配置载入；需要区分“服务器 env 默认值”和“admin_config 动态覆盖值”。
- 不要把 `tt/` 里的真实测试素材上传到外部云平台样例仓库，也不要打包进部署镜像。
- 不要把 `outputs/baiou/cases/knowledge/eval_sets/` 里的 holdout 测评集上传到 RAG 知识库，避免评测泄漏。
- 服务器 root 密码曾在对话中出现过，正式迁移或公开前应轮换密码，保留 SSH key 登录。
