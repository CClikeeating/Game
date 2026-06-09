# qingsheng_skill_runtime04

这是第 4 层：把 `qingsheng-skill` 真正接到大模型上运行。

前面三个管道是预处理和资产生产：

```text
原始聊天记录 -> 管道1 chat_turns -> 管道2 case_card/eval -> 管道3 learning/test/experience
```

这一层是未来产品/软件/小程序会用到的运行层：

```text
用户文字/截图/背景补充 -> 图片理解摘要 -> skill 手册 -> 百炼知识库检索 -> 大模型 -> 回答
```

## 支持的输入

- `--question`：用户问题，必填。
- `--context`：用户额外补充背景，比如女生年龄、认识方式、当前关系、你想让模型注意的点。
- `--image`：图片路径，可传多个。用于聊天截图、朋友圈截图、展示面截图等。

如果只传文字，runtime 会直接使用 `text_model`，当前通过 DashScope Responses API 的 `file_search` 调用百炼知识库。

如果传了图片，runtime 会先用 `vision_model` 把图片理解成聊天文本/摘要/检索关键词，再把这份图片理解结果合并进用户问题，交给 `text_model` 走百炼知识库检索并输出最终回答。这样图片问题也能参考案例知识库。

图片输入支持模式开关：

```powershell
--mode fast  # 视觉模型 + skill 直接回答，最快，但不检索知识库
--mode rag   # 视觉模型先摘要，再用摘要检索百炼知识库，默认
--mode auto  # 当前等同 rag，后续可接轻量判断器
```

`fast` 不是裸模型回答，它同样会加载 qingsheng skill prompt；它省掉的是第二次 `text_model + file_search` 调用。当前 `rag` 变慢的主要原因是第二步会携带较长的 skill/references prompt，后续需要做运行版短 prompt。

## 运行示例

只看 prompt，不调用模型：

```powershell
python -m workflow.qingsheng_skill_runtime04.run_skill `
  --question "她说最近好累，我该怎么回？" `
  --context "微信认识两周，还没见面，她 25 岁，最近工作忙" `
  --dry-run
```

图文一起输入：

```powershell
python -m workflow.qingsheng_skill_runtime04.run_skill `
  --question "帮我看这张聊天截图，她什么意思，我下一句怎么回？" `
  --context "我们是探探转微信，聊了三天，还没见面" `
  --image "D:/path/to/screenshot.jpg"
```

跑管道3生成的测试题样本：

```powershell
python -m workflow.qingsheng_skill_runtime04.run_eval_sample `
  --evals-file outputs/qingsheng_skill_eval03/batch_013_pipeline03_sample10_usable/test_questions/generated_qingsheng_evals.json `
  --batch-id runtime_eval_sample `
  --limit 2
```

## 配置

- `config/runtime.json`
  - skill 路径
  - 默认加载的 references
  - 本地经验包开关；当前默认关闭，避免和百炼知识库重复检索
  - 输出目录

- `config/models.json`
  - `text_model`：默认 Qwen `qwen3.7-plus` + 百炼知识库 `file_search`
  - `vision_model`：默认 Qwen `qwen3-vl-flash`，在 `rag` 模式只负责图片理解摘要；在 `fast` 模式直接给最终回复
  - `user_id=51`，专门给 runtime04 使用，不和管道2的清洗/判断 `user_id=0` 混用
  - API key 只从环境变量读取
  - 当前知识库 ID 配在 `text_model.file_search.vector_store_ids`

## 输出

输出在：

```text
outputs/qingsheng_skill_runtime04/{batch_id}/
```

每次运行会生成：

- `{timestamp}_prompt_preview.json`：本次组装后的输入预览。
- `{timestamp}_result.json`：模型返回结果或失败原因。

## 说明

这个 runtime 不复制 `qingsheng-skill`，而是读取原始 skill 文件。这样以后 skill 升级、经验包升级、模型切换都可以分开维护。
