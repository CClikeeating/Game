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

负责文本/截图输入、额度、登录、日常接话/暧昧推荐、回复生成、小程序 API、用户网页和管理后台。

主要产物：

```text
outputs/baiou/product/uploads/{run_id}/
outputs/baiou/product/runs/{run_id}/summary.json
outputs/baiou/product/feedback.jsonl
```

启动 v0.3 产品 API（包含 `/app` 和 `/admin`）：

```powershell
python -m baiou.product.api.serve
```

或双击：

```text
run_baiou_miniprogram_api.cmd
```

旧本地网页调试台已归档到 `baiou/product/archive/legacy_web/`。它会展示 dry-run、截图理解和参考片段，只能作为内部历史调试入口，不属于 v0.3 用户端。

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
## Archive

历史交接和旧评测说明已经归档：

```text
docs/archive/v02/V02_HANDOFF.md
docs/archive/product-eval/EVAL_README.md
docs/archive/product-cloud-handoff-20260616.md
```

这些文件保留历史分支、旧评测表、旧云部署交接和 handoff 风险；v0.3 发布请优先看当前 README 与 `baiou/product/DEPLOY_PM_REPORT.md`。

## 产品端部署状态与待办

详细 PM 汇报见：

```text
baiou/product/DEPLOY_PM_REPORT.md
```

当前线上后端已经部署到：

```text
https://baioulove.xyz
https://baioulove.xyz/app
https://baioulove.xyz/api/v1/health
```

当前已完成：

- 小程序 API 后端部署，服务名 `baiou`，Nginx 反代到本机 `127.0.0.1:7871`。
- 用户端只暴露日常接话和暧昧推荐：`bailian_rag_fast` 扣 1，`bailian_rag_strategy_quality` 扣 2。
- 反馈写入、后台统计、反馈 CSV 与截图审核 ZIP 导出已接入。
- 截图和模型运行明细保留周期默认 30 天，服务器每天凌晨自动清理。
- 后端已支持微信 `wx.login` 登录链路；小程序正式版必须配置 AppSecret 并关闭内测登录回退。
- 后台配置文件已作为额度等运营配置的线上准来源。Gunicorn 多 worker 会在请求前自动检查共享配置文件变更，避免后台管理页改额度后出现不同 worker 返回旧值/新值来回跳。

2026-06-21 线上修复记录：

- 问题：后台管理页修改每日积分上限和初始免费额度后，`/api/v1/health` 以及小程序“我的”页可能在旧值和新值之间跳动。
- 根因：线上服务使用 Gunicorn `--workers 2 --threads 2`，后台保存配置只更新命中请求的 worker 内存，其它 worker 仍保留旧配置。
- 修复：提交 `686e379 Fix runtime admin config sync`，后端每个 worker 按共享 `BAIOU_ADMIN_CONFIG` 文件的更新时间自动刷新后台可管理配置，并用原子替换方式写入配置文件。
- 部署：新 release 为 `/opt/baiou/releases/release_20260621_runtime_config_sync`，`/opt/baiou/current` 已切到该 release，服务 `baiou` 已重启。
- 验证：连续请求 `https://baioulove.xyz/api/v1/health` 返回一致，确认 `initial_credits=5`、`time_pass_daily_credit_cap=40` 不再跳值。

小程序正式发布前仍需完成：

- 微信小程序后台 request/uploadFile 合法域名配置为 `https://baioulove.xyz`。
- 真机回归文字输入、截图回复、反馈、兑换码和后台导出。
- 小程序提交审核和公众开放。

服务器环境已按 v0.3 要求配置微信 AppID/AppSecret、`BAIOU_MINIPROGRAM_DEV_LOGIN=false`、共享 SQLite/上传目录和当前额度规则。

备案通过后的接入顺序：

```text
1. 微信公众平台配置 request/uploadFile 合法域名：`https://baioulove.xyz`
2. 小程序开发者工具打开 URL 校验，确认正式版 `apiBaseUrl` 指向 `https://baioulove.xyz`
3. 真机测试文字输入、上传截图、生成回复、反馈、兑换码、后台统计、审核 ZIP 导出
4. 提交小程序审核
```

正式开放前建议补齐：

- 改掉已经在对话中出现过的服务器 root 密码，改用 SSH key 登录。
- 管理后台改为密码登录；服务器只保存密码 hash，后台登录 cookie 默认 7 天有效。

旧云部署交接长文已移到 `docs/archive/product-cloud-handoff-20260616.md`。当前部署、提审和服务器配置以 `baiou/product/DEPLOY_PM_REPORT.md` 为准。

## v0.3 发布前代码审查清理记录

本轮清理目标是让产品端发布路径更清楚，同时补齐几个不改业务逻辑的发布前风险点。

已处理：

- 后台接口不再接受 `?token=`；管理页改为密码登录并使用 HttpOnly cookie，header token 仅作为脚本兼容通道。
- SQLite 启动时会给旧产品库补齐 v0.3 需要的缺失字段，降低共享库切 release 风险。
- 小程序登录逻辑集中到 `miniprogram/utils/api.js`；缓存 token 失效遇到 401 时，会清缓存并自动重新 `wx.login` 一次。
- 旧本地网页调试台归档到 `baiou/product/archive/legacy_web/`，不再放在产品端主运行目录。
- 产品评测脚本移到 `baiou/product/eval/`；旧评测说明、v0.2 handoff 和旧云部署交接移到 `docs/archive/`。
- 根 README 只保留当前 v0.3 发布入口、线上状态和提审前待办，历史长文改为归档链接。

本轮验证：

```powershell
$env:PYTEST_ADDOPTS='--basetemp=.pytest_tmp_review'
python -m pytest -q
# 85 passed
```
