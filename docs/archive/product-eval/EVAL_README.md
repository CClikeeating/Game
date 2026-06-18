# Baiou Product Eval Inputs

This document explains how to turn case-library holdout segments into product-ready reply test cases.

The source holdout files are case-learning segments. They are not always valid product inputs as-is, because a segment can end with the coach/reference answer, or include later context that the product should not see. Always build product eval inputs before running product modes.

## Current Eval Set

Current holdout set:

```text
outputs/baiou/cases/knowledge/eval_sets/product_regression_35_weak8_20260614/segments.jsonl
```

Build product-ready inputs:

```powershell
python -m baiou.product.eval.eval_inputs outputs\baiou\cases\knowledge\eval_sets\product_regression_35_weak8_20260614\segments.jsonl --overrides-path docs\archive\product-eval\eval_overrides\product_regression_35_weak8_20260614.json
```

Generated files:

```text
product_eval_inputs.jsonl
product_eval_inputs.csv
product_eval_inputs_summary.json
```

These files are generated outputs and are ignored by git. Regenerate them from the source eval set when needed.

## Construction Rules

1. Select only the relevant segment turns.
   Prefer lines marked with `*`; otherwise use `source_turn_ids`; only fall back to the full context when neither exists.

2. If the relevant segment ends with one or more male turns, treat the trailing male-turn block as `expected_reply`.
   Remove that male block from the product input context. This prevents leaking the answer into the prompt.

3. If the relevant segment ends with a female turn, keep it as `female_prompt`.
   The expected reply comes from `更优回复`; if it says `保留原回复：“...”`, extract the quoted reply; otherwise fall back to `男生原回复`.

4. Expected reply is optional.
   Some tests are open-ended and should be judged by human review or scoring rules. Do not force every eval case to have an expected answer.

5. Remove cases that are useful learning nodes but not valid product reply questions.
   Example: when `female_prompt` and `expected_reply` are the same because the segment captured the girl's reaction instead of a reply opportunity.

## Manual Overrides

Optional overrides live beside the source eval set:

```text
product_eval_overrides.json
```

For handoff, keep a tracked copy under:

```text
docs/archive/product-eval/eval_overrides/{eval_set_name}.json
```

Example:

```json
{
  "schema_version": "baiou_product_eval_overrides_v01",
  "exclude_eval_indices": [1, 33],
  "cases": {
    "6": {
      "expected_reply": "",
      "expected_reply_source": "manual_none",
      "expected_reply_optional": true,
      "eval_input_ready": true,
      "eval_input_issues": []
    },
    "18": {
      "expected_reply": "别着急想我",
      "expected_reply_source": "manual_override",
      "expected_reply_optional": false,
      "eval_input_ready": true,
      "eval_input_issues": []
    }
  }
}
```

For `product_regression_35_weak8_20260614`, the PM decisions were:

```text
eval 1: remove from product eval
eval 33: remove from product eval
eval 6: keep as an open-ended test without expected_reply
eval 18: expected_reply = 别着急想我
```

After applying these overrides, the product eval table has:

```text
33 product eval cases
33 ready cases
16 weak-ack cases
1 open-ended case without expected_reply
2 excluded cases
```

## Running Product Modes

Use the product-ready rows, not raw `segments.jsonl`.

For each row, pass:

```text
question = 我该怎么回？
context = row.context
images = optional screenshots, usually empty for text-only eval rows
mode = bailian_rag_fast or bailian_rag_quality
```

Important:

- `bailian_rag_fast` and `bailian_rag_quality` both use the configured Bailian knowledge base.
- If a new Bailian knowledge base is created, update `BAIOU_VECTOR_STORE_IDS` or `baiou/config/product/models.json` before testing.
- Do not upload holdout eval-set markdown to Bailian; it must remain outside the production RAG library.

## Review Guidance

For rows with `expected_reply`, compare product output against the intent, not exact wording.

For rows without `expected_reply`, judge:

```text
Does it answer the female prompt directly?
Does it avoid over-reading weak replies?
Does it keep pressure appropriate to the context?
Does it avoid leaking coach language or explaining too much?
Does fast mode stay safe/natural and quality mode add useful initiative without forcing escalation?
```

Known mode expectation:

```text
bailian_rag_fast: cheaper, safer, more conservative, may occasionally recall a less precise segment
bailian_rag_quality: label anchor + RAG, usually more accurate and slightly more proactive
```
