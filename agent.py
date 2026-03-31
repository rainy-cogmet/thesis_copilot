"""
agent.py — 封装 Claude Code CLI 调用，为学生/导师 Agent 提供统一接口
"""

import subprocess
import json
import os
import sys


def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_rules():
    """
    加载 rules/ 目录下的所有规则文件，支持 .md .docx .pdf .tex 格式
    自动转换为文本后合并
    """
    config = load_config()
    rules_dir = config.get("rules_dir", "rules")
    rules_parts = []

    # basename → 标签映射（不带扩展名）
    rule_names = {
        "school_format": "学校格式规范",
        "advisor_comments": "导师修改意见",
        "custom_rules": "额外规则",
        "sample_paper": "范文参考",
    }

    # 支持的扩展名，按优先级排序
    supported_ext = [".md", ".txt", ".docx", ".pdf", ".tex", ".latex"]

    for basename, label in rule_names.items():
        content = _find_and_read_rule(rules_dir, basename, supported_ext)
        if content:
            rules_parts.append(f"## {label}\n\n{content}")

    return "\n\n---\n\n".join(rules_parts) if rules_parts else "（未提供规则文件）"


def _find_and_read_rule(rules_dir, basename, extensions):
    """
    在 rules_dir 中查找 basename.* 文件或 basename/ 目录
    支持单文件和整个目录
    """
    # 1. 先找单文件
    for ext in extensions:
        filepath = os.path.join(rules_dir, basename + ext)
        if os.path.exists(filepath):
            return _read_file_as_text(filepath, ext)

    # 2. 找目录（如 rules/school_format/）
    dir_path = os.path.join(rules_dir, basename)
    if os.path.isdir(dir_path):
        return _read_directory_as_text(dir_path)

    # 3. 模糊匹配文件名或目录名
    if os.path.isdir(rules_dir):
        key = basename.replace("_", "").lower()
        for fname in sorted(os.listdir(rules_dir)):
            name_lower = fname.lower().replace("_", "").replace("-", "")
            if key in name_lower:
                full = os.path.join(rules_dir, fname)
                # 匹配到目录
                if os.path.isdir(full):
                    return _read_directory_as_text(full)
                # 匹配到文件
                ext = os.path.splitext(fname)[1].lower()
                if ext in extensions:
                    return _read_file_as_text(full, ext)
    return None


# LaTeX 相关扩展名（目录扫描时识别这些）
_LATEX_EXTS = {".tex", ".cls", ".sty", ".bst", ".bib", ".cfg", ".def"}
_TEXT_EXTS = {".md", ".txt", ".csv", ".log"}
_CONVERT_EXTS = {".docx", ".pdf"}
_ALL_SCANNABLE = _LATEX_EXTS | _TEXT_EXTS | _CONVERT_EXTS


def _read_directory_as_text(dir_path):
    """
    递归扫描目录，提取所有有用文件的内容
    自动识别 LaTeX 模板文件(.tex .cls .sty .bst)、文档和 PDF
    """
    parts = []
    file_count = 0

    for root, dirs, files in os.walk(dir_path):
        # 跳过隐藏目录和常见无用目录
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", ".git")]

        for fname in sorted(files):
            if fname.startswith("."):
                continue

            ext = os.path.splitext(fname)[1].lower()
            if ext not in _ALL_SCANNABLE:
                continue

            filepath = os.path.join(root, fname)
            relpath = os.path.relpath(filepath, dir_path)

            content = None

            if ext in _LATEX_EXTS | _TEXT_EXTS:
                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read().strip()
                except Exception:
                    continue
            elif ext in _CONVERT_EXTS:
                content = _read_file_as_text(filepath, ext)

            if content:
                # 对过长的单个文件做截断（防止 token 爆炸）
                if len(content) > 8000:
                    content = content[:8000] + f"\n\n... [截断，原文件 {len(content)} 字符]"

                parts.append(f"### 文件: {relpath}\n\n```\n{content}\n```")
                file_count += 1

    if parts:
        header = f"（从目录 {os.path.basename(dir_path)}/ 中扫描到 {file_count} 个文件）\n"
        print(f"[INFO] 目录扫描: {dir_path} → {file_count} 个文件", file=sys.stderr)
        return header + "\n\n".join(parts)

    return None


def _read_file_as_text(filepath, ext):
    """根据文件格式读取内容为纯文本"""
    ext = ext.lower()

    # 纯文本格式直接读
    if ext in (".md", ".txt"):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return content if content and "（待填写）" not in content else None

    # docx → pandoc 转 markdown
    if ext == ".docx":
        return _convert_with_pandoc(filepath, "markdown")

    # tex/latex → pandoc 转 markdown
    if ext in (".tex", ".latex"):
        return _convert_with_pandoc(filepath, "markdown")

    # pdf → 先尝试 pdftotext，再 fallback 到 pandoc
    if ext == ".pdf":
        text = _extract_pdf_text(filepath)
        if text:
            return text
        return _convert_with_pandoc(filepath, "markdown")

    return None


def _convert_with_pandoc(filepath, to_format="markdown"):
    """用 pandoc 将文件转为指定格式的文本"""
    cache_path = filepath + ".cache.md"

    # 有缓存且比源文件新，直接用缓存
    if os.path.exists(cache_path):
        if os.path.getmtime(cache_path) > os.path.getmtime(filepath):
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read().strip() or None

    try:
        result = subprocess.run(
            ["pandoc", filepath, "-t", to_format, "--wrap=none"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            content = result.stdout.strip()
            # 写缓存
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[INFO] 已转换: {filepath} → 文本 ({len(content)} 字)", file=sys.stderr)
            return content
        else:
            print(f"[WARN] pandoc 转换失败: {filepath}: {result.stderr[:200]}", file=sys.stderr)
    except FileNotFoundError:
        print("[WARN] pandoc 未安装，无法转换非文本格式的规则文件", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print(f"[WARN] pandoc 转换超时: {filepath}", file=sys.stderr)

    return None


def _extract_pdf_text(filepath):
    """用 pdftotext 提取 PDF 文本"""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", filepath, "-"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            content = result.stdout.strip()
            print(f"[INFO] PDF 文本提取: {filepath} ({len(content)} 字)", file=sys.stderr)
            return content
    except FileNotFoundError:
        pass  # pdftotext 未安装，fallback 到 pandoc
    except subprocess.TimeoutExpired:
        pass
    return None


def load_materials(chapter_idx, chapter_title=""):
    """
    加载指定章节的参考文献资料
    
    查找逻辑（按优先级）:
    1. materials/chapter_{idx}/ 目录下所有文件
    2. materials/ch{idx}_*.md 等匹配文件
    3. 文件名包含章节标题关键词的文件
    """
    materials_dir = "materials"
    if not os.path.isdir(materials_dir):
        return ""

    parts = []

    # 1. 查找 chapter_N/ 子目录
    ch_dir = os.path.join(materials_dir, f"chapter_{chapter_idx}")
    if os.path.isdir(ch_dir):
        for fname in sorted(os.listdir(ch_dir)):
            if fname.startswith("."):
                continue
            filepath = os.path.join(ch_dir, fname)
            content = _read_material_file(filepath)
            if content:
                parts.append(f"### {fname}\n\n{content}")

    # 2. 查找 ch{idx}_* 文件
    prefix = f"ch{chapter_idx}_"
    for fname in sorted(os.listdir(materials_dir)):
        if fname.lower().startswith(prefix) and os.path.isfile(os.path.join(materials_dir, fname)):
            filepath = os.path.join(materials_dir, fname)
            content = _read_material_file(filepath)
            if content:
                parts.append(f"### {fname}\n\n{content}")

    if parts:
        header = f"（共加载 {len(parts)} 份参考资料）\n\n"
        print(f"[INFO] 章 {chapter_idx} 加载了 {len(parts)} 份参考资料", file=sys.stderr)
        return header + "\n\n---\n\n".join(parts)

    return ""


def _read_material_file(filepath):
    """读取单个参考资料文件"""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".md", ".txt"):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return None
    if ext in (".docx", ".tex", ".pdf"):
        return _read_file_as_text(filepath, ext)
    return None


def load_prompt_template(template_name):
    """加载提示词模板"""
    config = load_config()
    prompts_dir = config.get("prompts_dir", "prompts")
    filepath = os.path.join(prompts_dir, f"{template_name}.md")

    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def call_claude(prompt, system_prompt=None, expect_json=True):
    """
    调用 Claude Code CLI

    参数:
        prompt: 用户提示词
        system_prompt: 系统提示词（可选）
        expect_json: 是否期望 JSON 响应

    返回:
        如果 expect_json=True，返回解析后的 dict
        否则返回原始字符串
    """
    config = load_config()
    claude_cmd = config.get("claude_cmd", "claude")

    cmd = [claude_cmd, "-p"]

    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    # 如果需要 JSON，在 prompt 中强调
    if expect_json:
        prompt += "\n\n请严格以 JSON 格式回复，不要包含 markdown 代码块标记。"

    cmd.append(prompt)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5分钟超时
        )

        if result.returncode != 0:
            print(f"[ERROR] Claude CLI 返回非零码: {result.returncode}", file=sys.stderr)
            print(f"[STDERR] {result.stderr[:500]}", file=sys.stderr)
            return None

        output = result.stdout.strip()

        if expect_json:
            return _parse_json_response(output)
        return output

    except subprocess.TimeoutExpired:
        print("[ERROR] Claude CLI 调用超时", file=sys.stderr)
        return None
    except FileNotFoundError:
        print(f"[ERROR] 找不到命令 '{claude_cmd}'，请确认 Claude Code 已安装", file=sys.stderr)
        sys.exit(1)


def _parse_json_response(text):
    """从 Claude 响应中提取 JSON"""
    # 去除可能的 markdown 代码块
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试找到第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        print(f"[WARN] 无法解析 JSON 响应，原始内容:\n{text[:500]}", file=sys.stderr)
        return None


# ============================================================
# 学生 Agent 接口
# ============================================================

def student_revise_sentence(sentence, context, chapter_title, para_index, chapter_idx=0):
    """学生修改单个句子"""
    rules = load_rules()
    materials = load_materials(chapter_idx, chapter_title)
    template = load_prompt_template("student_sentence")

    prompt = template.format(
        sentence=sentence,
        context=context,
        chapter_title=chapter_title,
        para_index=para_index,
        rules=rules,
        materials=materials if materials else "（无）",
    )

    system = load_prompt_template("system_student")
    result = call_claude(prompt, system_prompt=system, expect_json=True)

    if result and "revised_sentence" in result:
        return result["revised_sentence"]
    return sentence  # 解析失败则保持原样


def student_fix_sentences(sentences_with_feedback, context, chapter_title, para_index, reference_content=""):
    """学生修复导师指出的问题句"""
    rules = load_rules()
    template = load_prompt_template("student_fix_sentences")

    issues_text = ""
    for item in sentences_with_feedback:
        issues_text += f"- 原句: {item['sentence']}\n  问题: {item['feedback']}\n\n"

    prompt = template.format(
        issues=issues_text,
        context=context,
        chapter_title=chapter_title,
        para_index=para_index,
        rules=rules,
        reference_content=reference_content if reference_content else "（无）",
    )

    system = load_prompt_template("system_student")
    result = call_claude(prompt, system_prompt=system, expect_json=True)

    if result and "fixed_sentences" in result:
        return result["fixed_sentences"]  # list of {"original": ..., "revised": ...}
    return []


def student_fix_chapter(chapter_text, feedback, chapter_title):
    """学生根据章级导师意见做局部修补"""
    rules = load_rules()
    template = load_prompt_template("student_fix_chapter")

    prompt = template.format(
        chapter_text=chapter_text,
        feedback=feedback,
        chapter_title=chapter_title,
        rules=rules,
    )

    system = load_prompt_template("system_student")
    result = call_claude(prompt, system_prompt=system, expect_json=False)
    return result if result else chapter_text


def student_restructure_chapter(chapter_text, structure_feedback, chapter_title):
    """学生根据导师意见调整章节段落结构"""
    rules = load_rules()
    template = load_prompt_template("student_restructure")

    prompt = template.format(
        chapter_text=chapter_text,
        structure_feedback=structure_feedback,
        chapter_title=chapter_title,
        rules=rules,
    )

    system = load_prompt_template("system_student")
    result = call_claude(prompt, system_prompt=system, expect_json=False)
    return result if result else chapter_text


# ============================================================
# 导师 Agent 接口
# ============================================================

def advisor_review_structure(chapter_text, chapter_title, paragraphs):
    """导师审阅章节的段落结构（在逐句修改之前）"""
    rules = load_rules()
    template = load_prompt_template("advisor_structure")

    # 生成段落结构概览
    overview_parts = []
    content_parts = []
    for i, para in enumerate(paragraphs):
        if para.get("is_heading_only"):
            overview_parts.append(f"  段 {i}: [子标题] {para['raw'][:50]}")
            content_parts.append(f"### 段 {i} [子标题]\n{para['raw']}")
        else:
            text = "".join(para["sentences"])
            preview = text[:80] + "..." if len(text) > 80 else text
            overview_parts.append(f"  段 {i}: ({len(para['sentences'])}句) {preview}")
            content_parts.append(f"### 段 {i} ({len(para['sentences'])}句)\n{text}")

    # 读取导师意见中与本章相关的部分
    advisor_comments = ""
    try:
        import os
        comments_path = os.path.join(load_config().get("rules_dir", "rules"), "advisor_comments.md")
        if os.path.exists(comments_path):
            with open(comments_path, "r", encoding="utf-8") as f:
                advisor_comments = f.read().strip()
    except Exception:
        pass

    prompt = template.format(
        chapter_title=chapter_title,
        structure_overview="\n".join(overview_parts),
        paragraphs_content="\n\n".join(content_parts),
        rules=rules,
        advisor_comments=advisor_comments,
    )

    system = load_prompt_template("system_advisor")
    result = call_claude(prompt, system_prompt=system, expect_json=True)

    default = {"needs_restructure": False, "feedback": "", "actions": []}
    if result and "needs_restructure" in result:
        return result
    return default

def advisor_review_sentence(sentence, context, chapter_title, para_index):
    """导师审阅单个句子"""
    rules = load_rules()
    template = load_prompt_template("advisor_sentence")

    prompt = template.format(
        sentence=sentence,
        context=context,
        chapter_title=chapter_title,
        para_index=para_index,
        rules=rules,
    )

    system = load_prompt_template("system_advisor")
    result = call_claude(prompt, system_prompt=system, expect_json=True)

    # 默认返回结构
    default = {"pass": True, "feedback": ""}
    if result and "pass" in result:
        return result
    return default


def advisor_review_paragraph(paragraph_text, context, chapter_title, para_index):
    """导师审阅整个段落"""
    from sample_index import get_summary_for_advisor

    rules = load_rules()
    template = load_prompt_template("advisor_paragraph")

    prompt = template.format(
        paragraph=paragraph_text,
        context=context,
        chapter_title=chapter_title,
        para_index=para_index,
        rules=rules,
        sample_summary=get_summary_for_advisor(),
    )

    system = load_prompt_template("system_advisor")
    result = call_claude(prompt, system_prompt=system, expect_json=True)

    # 期望结构: {"pass": bool, "feedback": str, "flagged_sentences": [...], "references": [...]}
    default = {"pass": True, "feedback": "", "flagged_sentences": [], "references": []}
    if result and "pass" in result:
        return result
    return default


def advisor_review_chapter(chapter_text, chapter_title):
    """导师审阅整个章节"""
    from sample_index import get_summary_for_advisor

    rules = load_rules()
    template = load_prompt_template("advisor_chapter")

    prompt = template.format(
        chapter_text=chapter_text,
        chapter_title=chapter_title,
        rules=rules,
        sample_summary=get_summary_for_advisor(),
    )

    system = load_prompt_template("system_advisor")
    result = call_claude(prompt, system_prompt=system, expect_json=True)

    # 期望结构: {"pass": bool, "feedback": str, "issues": [...], "references": [...]}
    default = {"pass": True, "feedback": "", "issues": [], "references": []}
    if result and "pass" in result:
        return result
    return default


def advisor_final_review(full_text):
    """导师全文终审"""
    rules = load_rules()
    template = load_prompt_template("advisor_final")

    prompt = template.format(
        full_text=full_text,
        rules=rules,
    )

    system = load_prompt_template("system_advisor")
    result = call_claude(prompt, system_prompt=system, expect_json=True)

    # 期望结构: {"pass": bool, "feedback": str, "chapter_issues": {...}}
    default = {"pass": True, "feedback": "通过", "chapter_issues": {}}
    if result and "pass" in result:
        return result
    return default
