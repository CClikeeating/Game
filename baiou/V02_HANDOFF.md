# Baiou v0.2 Handoff

This is the current handoff note for the Baiou v0.2 work. It records what is already in the integration branch, what exists on parallel branches, what local generated assets are important, and where the next owner should be careful.

## Current Integration Branch

Current PM/integration branch:

```text
codex/integrate-product-case-v02
```

Latest known commit on this branch:

```text
3cbcdc8 Add product eval input builder
```

This branch includes:

```text
case taxonomy v0.2 integration
product prompt sync with case taxonomy v0.2
bailian_rag_fast as product default mode
bailian_rag_quality quality-label mode
product image understanding speaker attribution fix
quality-mode weak-reply overreading guard
product eval input builder and eval handoff docs
```

This branch does not yet include the two later parallel feature branches:

```text
origin/codex/product-v2-miniprogram
origin/codex/case-v2-weak-signal-coverage
```

## Parallel Branches

### Product Mini Program

Branch:

```text
origin/codex/product-v2-miniprogram
```

Latest known commit:

```text
fa3ae52 Add miniprogram product MVP
```

Main content:

```text
miniprogram/
baiou/product/api/
baiou/product/storage/
run_baiou_miniprogram_api.cmd
tests/test_baiou_product_miniprogram_api.py
```

It adds a local Flask API, SQLite storage, WeChat mini-program MVP screens, upload/reply/feedback flows, and placeholder login/payment/admin pieces.

Known check from PM thread:

```text
37 passed
manual TT run in WeChat DevTools was reported usable
```

Do not assume this branch is already merged into `codex/integrate-product-case-v02`.

### Case Weak-Signal Coverage

Branch:

```text
origin/codex/case-v2-weak-signal-coverage
```

Latest known commit:

```text
1876b83 Add weak signal coverage workflow
```

Main content:

```text
baiou/case_pipeline/knowledge/build_eval_set.py
baiou/case_pipeline/production/audit_weak_signal_coverage.py
baiou/case_pipeline/production/materialize_missing_nodes.py
prompt/model-limit changes for weak signal handling
tests/test_baiou_case_pipeline_weak_signal.py
```

It improves weak-ack / low-pressure / natural-close coverage so product RAG is less likely to over-escalate when the girl only replies with low-information text such as `嗯嗯`, `好`, `ok`, or similar.

Known check from PM thread:

```text
37 passed
```

Do not assume this branch is already merged into `codex/integrate-product-case-v02`.

## Knowledge Base State

Current local formal knowledge base was cleaned from 492 to 455 active segments.

Current active counts:

```text
current/segments.jsonl: 455
current/local_index/segments_index.jsonl: 455
current/rag_knowledge_base/segments_index.jsonl: 455
active RAG markdown under segments/: 455
```

Health check target:

```text
python -m baiou.health_check
```

Expected important lines:

```text
segments: 455
local_index: 455
rag_markdown: 455
counts_match: True
```

Active formal RAG batches:

```text
40  calib_5segments_after_pipe2_prompt_v01_20260612_222046_775555
71  heat_probe_v02_5case_weak_gate_enforced_20260614_20260614_215934_144061
344 html_v02_remaining30_weak_gate_20260614_20260614_230724_538521
```

Removed from active upload path:

```text
37 old heat_probe_v02_5case_review_final2 docs
64 intermediate weak_gate docs
```

Clean all-in-one upload directory for a new Bailian knowledge base:

```text
outputs/baiou/cases/knowledge/current/rag_knowledge_base/clean_uploads/clean_v2_455_20260614_233309
```

Important: `outputs/` is ignored by git. These local assets exist in this workspace, but a fresh clone will not have them unless artifacts are copied separately.

## Bailian RAG

Current configured knowledge base ID:

```text
n7s0ou2dpt
```

If a new Bailian knowledge base is created with the 455 clean docs, update one of:

```text
BAIOU_VECTOR_STORE_IDS
baiou/config/product/models.json -> reply_rag_model.file_search.vector_store_ids
```

Do not upload holdout eval markdown to Bailian. The holdout set must remain outside the production RAG library.

## Product Modes

Current mode expectation:

```text
bailian_rag_fast: cheaper, safer, more conservative, can recall a less precise segment
bailian_rag_quality: quality-label anchor + Bailian RAG, usually more accurate and slightly more proactive
```

Product prompt notes already added:

```text
do not over-read weak replies as fear, attachment, or hidden affection
avoid lines like 奖励你 / 给你机会 / 乖 in the wrong context
when the girl wants to chat, a cleaner example is 那聊点付费的
speaker attribution for product screenshots defaults to left/white = girl, right/green = male/user
```

## Product Eval Set

Raw holdout eval set:

```text
outputs/baiou/cases/knowledge/eval_sets/product_regression_35_weak8_20260614/segments.jsonl
```

Product-ready eval inputs are generated from the raw holdout set. Do not directly test with raw `segments.jsonl`.

Tracked generation rule and override:

```text
baiou/product/eval_inputs.py
baiou/product/EVAL_README.md
baiou/product/eval_overrides/product_regression_35_weak8_20260614.json
```

Regenerate product-ready inputs:

```powershell
python -m baiou.product.eval_inputs outputs\baiou\cases\knowledge\eval_sets\product_regression_35_weak8_20260614\segments.jsonl --overrides-path baiou\product\eval_overrides\product_regression_35_weak8_20260614.json
```

Expected product eval summary:

```text
33 product eval cases
33 ready cases
16 weak-ack cases
1 open-ended case without expected_reply
2 excluded cases
```

PM eval decisions:

```text
eval 1: excluded from product eval
eval 33: excluded from product eval
eval 6: kept as open-ended with no expected_reply
eval 18: expected_reply = 别着急想我
```

## Logic Checks And Open Risks

Current logic looks consistent:

```text
production RAG library: 455 active docs
holdout eval set: excluded from production RAG
product-ready eval table: generated separately from holdout
fast/quality modes: both use Bailian RAG; quality adds a soft label anchor
```

Main risks to watch:

```text
1. Branch confusion
   The mini-program branch and weak-signal case branch are not merged into the current integration branch yet.

2. Artifact confusion
   outputs/ is ignored. Local current knowledge assets and eval tables are not guaranteed to exist in a fresh clone.

3. Bailian ID drift
   If a new knowledge base is created, the product config or BAIOU_VECTOR_STORE_IDS must be updated before product tests.

4. Eval leakage
   Never upload eval-set markdown to Bailian.

5. Exact-match scoring
   Product eval should judge intent and pressure level, not exact wording, except for very short canonical replies such as 你.
```

## Suggested Next Steps

1. Decide whether to merge `origin/codex/case-v2-weak-signal-coverage` into a new integration branch.
2. Decide whether to merge `origin/codex/product-v2-miniprogram` into the same or a separate integration branch.
3. If using a new Bailian knowledge base, upload the 455 clean docs and update the product vector store ID.
4. Run the 33 product-ready eval cases on both `bailian_rag_fast` and `bailian_rag_quality`.
5. Record failures by category: recall drift, over-escalation, too conservative, wrong speaker/context, awkward wording, or JSON/format failure.
