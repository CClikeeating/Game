# baiou

`baiou` 是当前主线包，按四段组织：

- `source_pipeline/`：原始素材到结构化聊天轮次。
- `case_pipeline/production/`：聊天轮次到 `segments_v01`，生成人工复核和禁用片段汇总。
- `case_pipeline/knowledge/`：approved 片段到当前知识总库、本地检索索引和 RAG 上传文档。
- `product/`：文本/截图输入、检索、回复生成和网页测试台。
- `common/`：路径、IO、配置、模型客户端等共享能力。

默认输出根目录是 `outputs/baiou/`，可用 `BAIOU_OUTPUT_ROOT` 覆盖。
