# 硕士论文修改 Harness 系统

## 项目概述

这是一个双Agent论文修改系统，由 `run.py` 编排，通过 Claude Code CLI 驱动两个角色：

- **学生Agent**：负责逐句修改论文
- **导师Agent**：负责逐级审阅（句→段→章→全文）

## 四层循环架构

```
L1 全文循环（最大 MAX_DOC_ROUNDS 轮）
  └─ L2 章循环（逐章推进）
       └─ L3 段循环（逐段推进）
            └─ L4 句循环（逐句修改+审阅）
            ← 段审阅（不通过→只改问题句）
       ← 章审阅（不通过→局部修补）
  ← 全文终审（不通过→重进 L2）
```

## 回退策略

- 段落不通过：只重改导师指出的问题句
- 章节不通过：只针对导师意见做局部修补
- 全文不通过：继续循环直到通过或达到轮数上限

## 关键文件

- `run.py` — 主编排脚本
- `config.json` — 轮数上限、路径等配置
- `prompts/` — 各级 Agent 提示词模板
- `rules/` — 审阅规则文件（用户提供）
- `thesis/thesis.md` — 工作中的论文 Markdown
- `state/progress.json` — 断点续传状态
- `logs/` — 每轮审阅日志

## 使用方法

```bash
# 1. 把论文 .docx 放到 thesis/ 目录
# 2. 把规则文档放到 rules/ 目录
# 3. 运行
python run.py

# 断点续传（从上次中断处继续）
python run.py --resume
```

## 规则文件说明

在 `rules/` 目录下放置：
- `school_format.md` — 学校论文格式规范
- `advisor_comments.md` — 导师批注/修改意见
- `custom_rules.md` — 你口头描述的额外规则
- `sample_paper.md` — 导师认可的范文（作为参考）
