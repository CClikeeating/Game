# qingsheng_skill_eval03

管道3：读取管道2案例批次包，生成 skill 资产和知识库文档。

## 输入

```text
outputs/qingsheng_cases02/{batch_id}/
```

## 运行

只生成资产：

```powershell
python -m workflow.qingsheng_skill_eval03.build_assets --batch-id batch_001 --input-bundle outputs/qingsheng_cases02/batch_001
```

生成资产并做 baseline 前置检查：

```powershell
python -m workflow.qingsheng_skill_eval03.run_baseline --batch-id batch_001 --input-bundle outputs/qingsheng_cases02/batch_001
```

## 输出

```text
outputs/qingsheng_skill_eval03/{batch_id}/
  learning_cases/
    cases_index.json
    cases_index.jsonl
    learning_manifest.csv
  test_questions/
    generated_qingsheng_evals.json
    eval_manifest.csv
  experience_pack/
    qingsheng_experience_pack.json
    qingsheng_experience_pack.jsonl
    experience_manifest.json
  rag_knowledge_base/
    cases/
      {case_id}.md
    qingsheng_cases_index.jsonl
    upload_manifest.csv
    rag_build_summary.json
  build_summary.json
  baseline_preflight.json
```

- `learning_cases`：给人或模型学习、检索案例。
- `test_questions`：用来测试 qingsheng skill。
- `experience_pack`：未来部署 skill 时可带走的干净经验库，不包含复核表、模型日志和原始图片。
- `rag_knowledge_base`：从案例资产派生出的 Markdown 知识库文档，适合上传到百炼知识库或后续自建 RAG；它不替代 `experience_pack`，只是多一种检索友好的导出格式。
  - `cases/{case_id}.md` 是上传知识库的主文件。
  - 每份 Markdown 会包含主阶段、阶段路径、关键阶段节点、女方信号、好/坏回复和可迁移规则。
  - Markdown 面向人读和知识库检索；结构化 JSON/JSONL 仍保留在 `experience_pack` 和 `learning_cases`。
