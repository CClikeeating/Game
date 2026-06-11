# qingsheng_skill_web05

本地网页测试台，用来测试 `qingsheng_skill_runtime04` 的文字/截图回复效果。

网页只负责上传、输入、展示结果；真正的 skill、模型、知识库调用仍走 `workflow.qingsheng_skill_runtime04.run_skill`。所以修改 skill、知识库 ID 或模型配置后，不需要改网页。

## 启动

```powershell
python -m workflow.qingsheng_skill_web05.serve
```

默认地址：

```text
http://127.0.0.1:7860
```

## 页面功能

- 输入用户问题和补充背景。
- 上传一张或多张聊天截图。
- 选择运行模式：
  - `fast`：加载 skill 后由视觉模型直接回答，不检索知识库。
  - `rag`：图片先转摘要，再用摘要和问题检索百炼知识库，默认推荐。
  - `auto`：当前等同 `rag`，后续可接轻量判断器。
- 选择回复模式：
  - `simple`：只给一句可直接发送的话。
  - `coach`：默认教练模式，核心判断 + 话术 + 简短注意点。
  - `analysis`：详细复盘。
  - `autopilot`：第一行输出 `[发送]` 和可复制话术。
- 查看调试信息：
  - 各模型耗时。
  - token 使用量，如果模型接口返回了 usage。
  - RAG 知识库引用，如果模型接口返回了 file citation。
  - User Prompt 和 System Prompt 预览。
  - prompt/result/summary 文件路径。

## 配置更新

网页不缓存也不复制 skill。修改下面文件后，重新提交页面即可使用新内容：

```text
qingsheng-skill/skill/SKILL.md
workflow/qingsheng_skill_runtime04/config/runtime.json
workflow/qingsheng_skill_runtime04/config/models.json
```

知识库 ID 在 `models.json` 的 `text_model.file_search.vector_store_ids` 中配置。

回复模式在 `runtime.json` 的 `answer_style.modes` 中配置。

网页自身的端口、上传限制和输出目录在这里配置：

```text
workflow/qingsheng_skill_web05/config/web.json
```

也可以用环境变量临时覆盖：

```text
QINGSHENG_WEB_CONFIG
QINGSHENG_WEB_HOST
QINGSHENG_WEB_PORT
QINGSHENG_WEB_DEBUG
QINGSHENG_WEB_MAX_CONTENT_MB
QINGSHENG_WEB_OUTPUT_ROOT
```

## 输出位置

网页侧上传和摘要：

```text
outputs/qingsheng_skill_web05/uploads/{run_id}/
outputs/qingsheng_skill_web05/runs/{run_id}/summary.json
```

runtime04 自己的 prompt/result 仍输出到：

```text
outputs/qingsheng_skill_runtime04/{batch_id}/
```
