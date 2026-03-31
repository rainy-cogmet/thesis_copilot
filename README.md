# 📝 Thesis Copilot

[中文文档](README_zh.md)

A multi-agent harness for Claude Code that automates thesis revision through a student-advisor feedback loop.

One agent writes. Another critiques. They loop until your thesis is done.

## How it works

```
┌─────────────────────────────────────────────────────┐
│  L1  Full document loop (max N rounds)              │
│  ┌───────────────────────────────────────────────┐  │
│  │  L2  Chapter loop                             │  │
│  │  ┌─────────────────────────────────────────┐  │  │
│  │  │  L3  Paragraph loop                     │  │  │
│  │  │  ┌───────────────────────────────────┐  │  │  │
│  │  │  │  L4  Sentence loop                │  │  │  │
│  │  │  │  Student revises → Advisor reviews│  │  │  │
│  │  │  └───────────────────────────────────┘  │  │  │
│  │  │  Advisor reviews paragraph ✓/✗          │  │  │
│  │  │  ✗ → fix only flagged sentences         │  │  │
│  │  └─────────────────────────────────────────┘  │  │
│  │  Advisor reviews chapter ✓/✗                  │  │
│  │  ✗ → local patches only                       │  │
│  └───────────────────────────────────────────────┘  │
│  Advisor final review ✓/✗                           │
│  ✗ → next round                                     │
└─────────────────────────────────────────────────────┘
```

Two Claude Code agents work in a 4-level nested loop:

- **Student agent** revises sentence by sentence based on rules and reference materials
- **Advisor agent** reviews at every level (sentence → paragraph → chapter → full document), only passes when quality meets the bar
- On failure, the system precisely targets what needs fixing — no unnecessary rewrites

## Features

- **Surgical scope control** — process specific chapters and paragraphs instead of the whole thesis
- **Multi-format rules** — drop in `.docx`, `.pdf`, `.tex`, or `.md` files as guidelines, or entire LaTeX template directories
- **On-demand sample extraction** — advisor references specific passages from exemplar papers only when needed, saving tokens
- **Per-chapter materials** — load literature reviews and references for specific chapters automatically
- **Breakpoint resume** — state is saved after every paragraph, pick up where you left off
- **Full audit trail** — every review decision is logged as JSON

## Quick start

### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- [Pandoc](https://pandoc.org/installing.html) for format conversion
- Optional: `poppler-utils` for PDF reading (`brew install poppler` / `apt install poppler-utils`)

### Setup

```bash
git clone https://github.com/YOUR_USERNAME/thesis-copilot.git
cd thesis-copilot

# 1. Place your thesis
cp /path/to/your/thesis.docx thesis/original.docx

# 2. Add your rules (any format: .md, .docx, .pdf, .tex)
cp school_guidelines.pdf rules/school_format.pdf
cp advisor_feedback.docx rules/advisor_comments.docx

# 3. Edit your custom rules
vim rules/custom_rules.md

# 4. (Optional) Add sample papers
mkdir -p rules/sample_paper
cp exemplar_thesis.pdf rules/sample_paper/

# 5. (Optional) Add chapter-specific reference materials
cp literature_review.md materials/ch2_literature_review.md
```

### Run

```bash
# Preview structure and scope (no API calls)
python run.py --dry-run

# Run the revision loop
python run.py

# Skip docx→md conversion if you already have markdown
python run.py --skip-convert
```

### Scope control

Edit `config.json` to target specific chapters and paragraphs:

```jsonc
"scope": {
  "mode": "selected",     // "all" for full document
  "chapters": [2, 6],     // chapter indices (0-based)
  "paragraphs": {
    "2": [0, 1, 3],       // specific paragraphs in chapter 2
    "6": "all"            // all paragraphs in chapter 6
  },
  "skip_final_review": true
}
```

Run `python run.py --dry-run` to see which chapters/paragraphs will be processed before committing.

## Project structure

```
thesis-copilot/
├── run.py                 # Main orchestrator (4-level nested loop)
├── agent.py               # Claude Code CLI wrapper for both agents
├── thesis_parser.py       # Markdown ↔ chapter/paragraph/sentence
├── sample_index.py        # On-demand sample paper extraction
├── config.json            # Settings and scope control
├── CLAUDE.md              # Project context for Claude Code
├── prompts/               # Agent prompt templates
│   ├── system_student.md
│   ├── system_advisor.md
│   ├── student_sentence.md
│   ├── student_fix_sentences.md
│   ├── student_fix_chapter.md
│   ├── advisor_sentence.md
│   ├── advisor_paragraph.md
│   ├── advisor_chapter.md
│   └── advisor_final.md
├── rules/                 # Your guidelines (any format)
│   ├── school_format.*
│   ├── advisor_comments.*
│   ├── custom_rules.md
│   └── sample_paper/
├── materials/             # Per-chapter reference literature
│   └── ch{N}_*.md
├── thesis/                # Your thesis files
│   ├── original.docx
│   ├── thesis.md          # (generated) working copy
│   └── output.docx        # (generated) final output
├── logs/                  # Review logs (JSON)
└── state/                 # Resume checkpoint
```

## How the agents work

### Advisor agent

The advisor applies your rules strictly at each granularity level:

| Level | Focus |
|---|---|
| Sentence | Grammar, terminology, clarity |
| Paragraph | Internal logic, transitions, coherence |
| Chapter | Structure, argumentation, consistency |
| Full document | Framework, innovation narrative, conclusions |

When the advisor fails a paragraph or chapter, it returns precisely what's wrong — flagged sentences, specific issues, and optionally references to sample papers for the student to learn from.

### Student agent

The student receives the advisor's feedback plus any referenced sample paper excerpts, and makes targeted fixes. It doesn't rewrite content the advisor already approved.

### Sample paper referencing

Sample papers are indexed at startup (table of contents only, not loaded into memory). When the advisor thinks the student should reference a specific passage, it says:

```json
{
  "references": [
    {"paper": "Wang2023", "chapter": "Experiments", "reason": "Learn from their method description"}
  ]
}
```

The system then extracts just that section and passes it to the student — no token waste.

## Configuration

| Key | Default | Description |
|---|---|---|
| `max_doc_rounds` | 3 | Maximum full-document revision cycles |
| `max_paragraph_retries` | 2 | Max retries per paragraph before moving on |
| `max_chapter_retries` | 2 | Max retries per chapter before moving on |
| `chapter_heading_level` | 1 | Markdown heading level for chapters (`#` = 1) |
| `sentence_delimiters` | `。！？；.!?;` | Characters that end a sentence |

## Customizing prompts

All agent prompts are in `prompts/` as plain Markdown files with `{placeholder}` variables. Customize them to fit your field, language, or advisor's style. No code changes needed.

## Logs

Every review decision is saved as structured JSON in `logs/`:

```
logs/
└── round_1/
    ├── chapter_2/
    │   ├── para_0/
    │   │   ├── sentence_0.json
    │   │   ├── sentence_1.json
    │   │   └── paragraph_review.json
    │   └── chapter_review.json
    └── final_review.json
```

## Limitations

- Works best with Chinese and English academic writing
- Very long chapters may hit token limits — consider splitting
- Tables and figures in the thesis are preserved but not deeply analyzed
- The student agent revises text, not LaTeX/Word formatting

## License

MIT
