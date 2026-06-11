# Baiou Case Workflow

## 新版 MVP 工作入口

当前新版 MVP 改造请先进入 `workV/` 新工作区，不要直接在旧 `workflow/` 上继续改产品逻辑。

协作和后续开发默认顺序：

1. 先阅读 `workV/README.md`。
2. 新功能优先放在 `workV/` 下。
3. 旧 `workflow/` 只作为可复用来源：管道1整案输出、管道2双模型复核机制、管道3资产导出思路、旧截图能力。
4. 不要把旧 7 阶段体系、旧 `case_card` schema、旧 `qingsheng-skill` 长 Prompt、旧百炼 `file_search` 默认混进新版 v0.1。
5. 新版默认流程是：旧管道1整案 -> `workV` 拆 `segments_v01` -> xlsx 人工复核 -> approved segments -> 本地片段索引/片段资产 -> 文本或截图回复测试台。

常用入口：

```powershell
# 查看新版说明
Get-Content workV/README.md

# 启动新版本地测试台
python -m workV.web.serve
```

下面是旧项目原说明，保留用于理解历史管道和复用边界。

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

## 当前运行层

`workflow/qingsheng_skill_runtime04` 用于把 `qingsheng-skill` 接到模型和知识库上：

- 文字输入：Qwen `qwen3.7-plus` + 百炼知识库 `file_search`。
- 图片输入：默认先用 Qwen3-VL 轻量视觉模型提取聊天摘要，再用摘要检索百炼知识库。
- 图片模式可切换：`fast` 加载 skill 后由视觉模型直接回答，`rag` 先摘要再检索，`auto` 当前等同 `rag`。

后续需要单独优化 runtime prompt：把完整 skill 和 references 压缩成产品运行版短提示词，以降低 token 成本和响应时间。

`archive/` 里的内容只作历史保留，后续主流程不要读取它。
