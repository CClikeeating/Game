# qingsheng_skill_web05

本地网页测试台，用来测试 `qingsheng_skill_runtime04` 的文字/截图回复效果。

## 启动

```powershell
python -m workflow.qingsheng_skill_web05.serve
```

默认地址：

```text
http://127.0.0.1:7860
```

## 使用方式

- 输入用户问题和补充背景。
- 可上传一张或多张截图。
- 选择模式：
  - `fast`：加载 skill 后由视觉模型直接回答，不检索知识库。
  - `rag`：图片先转摘要，再用摘要检索百炼知识库，默认推荐。
  - `auto`：当前等同 `rag`，后续可接轻量判断器。
- 勾选 `dry-run` 可以只测试链路，不调用模型。

## 配置更新

网页不缓存也不复制 skill。修改下面文件后，重新提交页面即可使用新内容：

```text
qingsheng-skill/skill/SKILL.md
workflow/qingsheng_skill_runtime04/config/runtime.json
workflow/qingsheng_skill_runtime04/config/models.json
```

知识库 ID 在 `models.json` 的 `text_model.file_search.vector_store_ids` 中配置。

## 输出位置

```text
outputs/qingsheng_skill_web05/uploads/{run_id}/
outputs/qingsheng_skill_web05/runs/{run_id}/summary.json
```

runtime04 自己的 prompt/result 仍输出到：

```text
outputs/qingsheng_skill_runtime04/{batch_id}/
```
