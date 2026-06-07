# Baiou Case Workflow

这个项目把聊天素材加工成 `qingsheng-skill` 可用的案例、测试题和经验包。

## 目录结构

```text
workflow/          管道代码、配置、模板、说明
data/              原始输入数据，不进 Git
outputs/           每层管道的批次输出包，不进 Git
qingsheng-skill/   skill 本体，独立保留
other/             临时辅助工具
archive/           旧实验和旧素材归档，主流程不依赖
```

## 主流程

```text
data/raw/*
  -> workflow/source_to_chat_turns01
  -> outputs/source_to_chat_turns01/{batch_id}
  -> workflow/qingsheng_cases02
  -> outputs/qingsheng_cases02/{batch_id}
  -> workflow/qingsheng_skill_eval03
  -> outputs/qingsheng_skill_eval03/{batch_id}
```

每一层都读取上一层的完整批次包根目录，而不是复制出来的单个 JSON。

## 三类最终资产

管道三会从管道二案例包生成：

- `learning_cases/`：学习案例和案例索引。
- `test_questions/`：用来测试 skill 的 eval 题。
- `experience_pack/`：未来部署 skill 时可带走的干净经验包。

`archive/` 里的内容只作历史保留，后续主流程不要读取它。
