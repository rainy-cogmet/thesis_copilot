# 📝 Thesis Copilot

基于 Claude Code 的双 Agent 论文修改系统——一个写，一个审，循环到过关为止。

## 工作原理

```
┌──────────────────────────────────────────────────────┐
│  L1  全文循环（最多 N 轮）                              │
│  ┌────────────────────────────────────────────────┐  │
│  │  L2  逐章推进                                    │  │
│  │  ┌──────────────────────────────────────────┐  │  │
│  │  │  L3  逐段推进                              │  │  │
│  │  │  ┌────────────────────────────────────┐  │  │  │
│  │  │  │  L4  逐句处理                        │  │  │  │
│  │  │  │  学生修改 → 导师审阅                   │  │  │  │
│  │  │  └────────────────────────────────────┘  │  │  │
│  │  │  导师审阅整段 ✓/✗                         │  │  │
│  │  │  ✗ → 只改导师标记的问题句                   │  │  │
│  │  └──────────────────────────────────────────┘  │  │
│  │  导师审阅整章 ✓/✗                               │  │
│  │  ✗ → 只做局部修补                                │  │
│  └────────────────────────────────────────────────┘  │
│  导师全文终审 ✓/✗                                      │
│  ✗ → 进入下一轮                                        │
└──────────────────────────────────────────────────────┘
```

系统由两个 Claude Code Agent 组成，在四层嵌套循环中协作：

- **学生 Agent** 根据规则和参考文献逐句修改论文
- **导师 Agent** 在每一层（句→段→章→全文）进行审阅，不达标不放行
- 不通过时精准定位问题，不做无意义的重写

## 特性

- **精确打击** — 通过 `scope` 配置只处理指定的章节和段落，不用每次跑全文
- **规则文件格式随意** — 直接丢 `.docx`、`.pdf`、`.tex`、`.md` 文件，或整个 LaTeX 模板目录
- **范文按需提取** — 导师引用范文某段时才去读取，不预加载全文，省 token
- **按章加载参考文献** — 把文献综述放到 `materials/ch{N}_*`，只在处理对应章节时加载
- **断点续传** — 每段处理完自动保存进度，中断后可以继续
- **完整审阅日志** — 每一次审阅决策都以 JSON 保存，方便回溯

## 快速开始

### 环境准备

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)：确认 `claude -p "测试"` 能正常返回
- [Pandoc](https://pandoc.org/installing.html)：用于格式转换
- 可选：`poppler-utils` 用于读取 PDF（`brew install poppler` / `apt install poppler-utils`）

### 放置文件

```bash
git clone https://github.com/YOUR_USERNAME/thesis-copilot.git
cd thesis-copilot

# 1. 放论文
cp 你的论文.docx thesis/original.docx

# 2. 放规则文件（格式随意）
cp 学校格式规范.pdf rules/school_format.pdf
cp 导师批注.docx rules/advisor_comments.docx

# 3. 编辑额外规则
vim rules/custom_rules.md

# 4. 放范文（可选）
mkdir -p rules/sample_paper
cp 优秀论文.pdf rules/sample_paper/

# 5. 放参考文献资料（可选，按章节命名）
cp 文献综述.md materials/ch2_literature_review.md
```

### 运行

```bash
# 预览结构和范围（不调用 Agent）
python run.py --dry-run

# 正式运行
python run.py

# 已有 markdown 时跳过格式转换
python run.py --skip-convert
```

## 范围控制

编辑 `config.json` 中的 `scope` 字段：

```jsonc
// 只处理第 3 章和第 7 章
"scope": {
  "mode": "selected",
  "chapters": [2, 6],
  "paragraphs": {
    "2": [0, 1, 3],    // 第 3 章只改第 0、1、3 段
    "6": "all"          // 第 7 章全部段落
  },
  "skip_final_review": true
}
```

```jsonc
// 全文处理
"scope": {
  "mode": "all"
}
```

章节编号从 0 开始，不确定编号就先跑 `python run.py --dry-run` 查看。

## 项目结构

```
thesis-copilot/
├── run.py                 # 主编排脚本（四层嵌套循环）
├── agent.py               # Claude Code CLI 封装
├── thesis_parser.py       # Markdown ↔ 章/段/句 解析
├── sample_index.py        # 范文索引与按需提取
├── config.json            # 配置与范围控制
├── CLAUDE.md              # Claude Code 项目说明
│
├── prompts/               # Agent 提示词模板
│   ├── system_student.md      # 学生角色设定
│   ├── system_advisor.md      # 导师角色设定
│   ├── student_sentence.md    # 学生：逐句修改
│   ├── student_fix_sentences.md  # 学生：修复问题句
│   ├── student_fix_chapter.md    # 学生：章级修补
│   ├── advisor_sentence.md    # 导师：句级审阅
│   ├── advisor_paragraph.md   # 导师：段级审阅
│   ├── advisor_chapter.md     # 导师：章级审阅
│   └── advisor_final.md       # 导师：全文终审
│
├── rules/                 # 审阅规则（支持任意格式）
│   ├── school_format.*        # 学校格式规范
│   ├── advisor_comments.*     # 导师修改意见
│   ├── custom_rules.md        # 额外规则
│   └── sample_paper/          # 范文目录
│
├── materials/             # 按章参考文献
│   └── ch{N}_*.md
│
├── thesis/                # 论文文件
│   ├── original.docx          # 原始论文
│   ├── thesis.md              # （自动生成）工作用 Markdown
│   └── output.docx            # （自动生成）最终输出
│
├── logs/                  # 审阅日志
└── state/                 # 断点续传状态
```

## 两个 Agent 的分工

### 导师 Agent

在每一层用不同的尺度审阅：

| 层级 | 关注点 |
|---|---|
| 句 | 语法、术语、表达清晰度 |
| 段 | 段内逻辑、过渡衔接、主题明确 |
| 章 | 结构完整性、论证链条、术语一致性 |
| 全文 | 整体框架、创新点阐述、结论支撑度 |

审阅不通过时，精确返回问题位置和修改建议。可以引用范文中的具体段落作为参考。

### 学生 Agent

收到导师反馈和范文片段后做针对性修改，不动已通过的部分。

### 范文按需引用

启动时只建索引（目录级别），不读全文。导师审阅时看到范文清单：

```
可参考的范文:
- 王某某2023硕士论文 (6章42段): 绪论, 相关工作, 系统设计, 实验, 结论
```

觉得需要参考时在回复中指明：

```json
{
  "references": [
    {"paper": "王某某2023", "chapter": "实验", "reason": "参考其实验方法描述的写法"}
  ]
}
```

系统自动提取对应片段喂给学生 Agent。不引用 = 不加载 = 零浪费。

## 配置项

| 参数 | 默认值 | 说明 |
|---|---|---|
| `max_doc_rounds` | 3 | 全文最多循环几轮 |
| `max_paragraph_retries` | 2 | 段落不通过最多重试几次 |
| `max_chapter_retries` | 2 | 章节不通过最多重试几次 |
| `chapter_heading_level` | 1 | 章标题的 Markdown 层级（`#` = 1） |
| `sentence_delimiters` | `。！？；.!?;` | 断句标点 |

## 自定义提示词

所有提示词都在 `prompts/` 下，纯 Markdown 格式，用 `{placeholder}` 做变量替换。想调整 Agent 的审阅尺度、写作风格、学科侧重——直接改文件，不需要动代码。

## 审阅日志

每一次审阅决策都保存为 JSON：

```
logs/
└── round_1/
    ├── chapter_2/
    │   ├── para_0/
    │   │   ├── sentence_0.json    # 每句的修改前后 + 审阅意见
    │   │   ├── sentence_1.json
    │   │   └── paragraph_review.json  # 段级审阅结果
    │   └── chapter_review.json    # 章级审阅结果
    └── final_review.json          # 全文终审结果
```

## 局限性

- 最适合中文和英文学术写作
- 非常长的章节可能遇到 token 上限，建议拆分
- 论文中的表格和图片会被保留但不会被深度分析
- 学生 Agent 修改的是文本内容，不处理 LaTeX/Word 排版格式

## 许可

MIT
