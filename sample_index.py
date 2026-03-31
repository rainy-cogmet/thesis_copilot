"""
sample_index.py — 范文索引与按需提取

预先将范文拆分为章节/段落并建立索引，不加载全文。
导师 Agent 引用时，按位置提取对应片段。
"""

import os
import re
import json
import subprocess
import sys


_INDEX_CACHE = None
_INDEX_FILE = "state/sample_index.json"


def build_index(rules_dir="rules"):
    """
    扫描 rules/ 下的范文，建立索引（只记录结构，不存全文）
    
    索引结构:
    {
        "papers": {
            "王某某2023硕士论文": {
                "source": "rules/sample_paper/王某某2023硕士论文.pdf",
                "chapters": [
                    {"title": "绪论", "para_count": 5, "char_offset": 0, "char_length": 1200},
                    {"title": "相关工作", "para_count": 8, "char_offset": 1200, "char_length": 2400},
                    ...
                ],
                "total_chars": 15000,
                "total_paragraphs": 42
            }
        },
        "summary": "可用范文: 王某某2023硕士论文(6章42段), 李某某2022硕士论文(5章38段)"
    }
    """
    papers = {}

    # 查找范文文件/目录
    sample_dir = os.path.join(rules_dir, "sample_paper")
    sample_files = []

    if os.path.isdir(sample_dir):
        for root, _, files in os.walk(sample_dir):
            for f in files:
                if not f.startswith(".") and _is_supported(f):
                    sample_files.append(os.path.join(root, f))
    else:
        # 单文件模式
        for f in os.listdir(rules_dir):
            if "sample" in f.lower().replace("_", "") and _is_supported(f):
                sample_files.append(os.path.join(rules_dir, f))

    for filepath in sample_files:
        name = os.path.splitext(os.path.basename(filepath))[0]
        text = _read_to_text(filepath)
        if not text:
            continue

        chapters = _parse_chapters(text)
        papers[name] = {
            "source": filepath,
            "chapters": chapters,
            "total_chars": len(text),
            "total_paragraphs": sum(ch["para_count"] for ch in chapters),
        }
        print(f"[INFO] 范文索引: {name} → {len(chapters)} 章, {len(text)} 字", file=sys.stderr)

    # 生成摘要（给导师 Agent 看的）
    summary_parts = []
    for name, info in papers.items():
        ch_count = len(info["chapters"])
        p_count = info["total_paragraphs"]
        ch_titles = ", ".join(ch["title"] for ch in info["chapters"][:6])
        summary_parts.append(f"- {name} ({ch_count}章{p_count}段): {ch_titles}")

    index = {
        "papers": papers,
        "summary": "\n".join(summary_parts) if summary_parts else "（未提供范文）",
    }

    # 保存索引
    os.makedirs(os.path.dirname(_INDEX_FILE), exist_ok=True)
    with open(_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    global _INDEX_CACHE
    _INDEX_CACHE = index
    return index


def get_index():
    """获取索引（有缓存用缓存）"""
    global _INDEX_CACHE
    if _INDEX_CACHE:
        return _INDEX_CACHE
    if os.path.exists(_INDEX_FILE):
        with open(_INDEX_FILE, "r", encoding="utf-8") as f:
            _INDEX_CACHE = json.load(f)
        return _INDEX_CACHE
    return build_index()


def get_summary_for_advisor():
    """返回范文目录摘要，供导师 Agent 使用（不含全文）"""
    index = get_index()
    return index.get("summary", "（未提供范文）")


def extract_reference(paper_name, chapter=None, paragraph=None, keyword=None):
    """
    按需提取范文片段
    
    参数:
        paper_name: 范文名称（模糊匹配）
        chapter: 章节标题或编号（可选）
        paragraph: 段落编号（可选）
        keyword: 关键词搜索（可选）
    
    返回:
        提取的文本片段
    """
    index = get_index()
    papers = index.get("papers", {})

    # 模糊匹配范文名
    matched_name = _fuzzy_match_paper(paper_name, papers)
    if not matched_name:
        return f"[未找到范文: {paper_name}]"

    paper = papers[matched_name]
    filepath = paper["source"]

    # 读取全文
    text = _read_to_text(filepath)
    if not text:
        return f"[无法读取范文: {filepath}]"

    # 按章节提取
    if chapter is not None:
        return _extract_chapter(text, chapter)

    # 按关键词搜索
    if keyword:
        return _extract_by_keyword(text, keyword)

    # 都没指定，返回前 2000 字摘要
    return text[:2000] + "..." if len(text) > 2000 else text


def extract_from_advisor_references(references):
    """
    批量处理导师 Agent 返回的引用列表
    
    references 格式:
    [
        {"paper": "王某某2023", "chapter": "实验设计", "reason": "参考其实验描述方式"},
        {"paper": "李某某2022", "keyword": "系统架构", "reason": "学习其架构描述逻辑"}
    ]
    
    返回: 拼接好的参考文本
    """
    if not references:
        return ""

    parts = []
    for ref in references:
        paper = ref.get("paper", "")
        chapter = ref.get("chapter")
        keyword = ref.get("keyword")
        reason = ref.get("reason", "")

        content = extract_reference(paper, chapter=chapter, keyword=keyword)

        parts.append(
            f"### 参考: {paper}"
            + (f" — {chapter}" if chapter else "")
            + (f" (搜索: {keyword})" if keyword else "")
            + f"\n导师要求: {reason}\n\n{content}"
        )

    return "\n\n---\n\n".join(parts)


# ============================================================
# 内部工具函数
# ============================================================

def _is_supported(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in (".pdf", ".docx", ".tex", ".latex", ".md", ".txt")


def _read_to_text(filepath):
    """将文件转为纯文本"""
    ext = os.path.splitext(filepath)[1].lower()

    if ext in (".md", ".txt"):
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip()

    if ext in (".docx", ".tex", ".latex"):
        try:
            r = subprocess.run(
                ["pandoc", filepath, "-t", "markdown", "--wrap=none"],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0:
                return r.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    if ext == ".pdf":
        try:
            r = subprocess.run(
                ["pdftotext", "-layout", filepath, "-"],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        # fallback pandoc
        try:
            r = subprocess.run(
                ["pandoc", filepath, "-t", "markdown", "--wrap=none"],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode == 0:
                return r.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return None


def _parse_chapters(text):
    """从文本中解析章节结构（只记录元数据）"""
    chapters = []
    # 匹配 markdown 标题或中文章节标题
    pattern = r"^(#{1,2}\s+.+|第[一二三四五六七八九十\d]+章\s*.+)$"
    lines = text.split("\n")

    current_title = "(前言)"
    current_start = 0
    current_paras = 0

    for i, line in enumerate(lines):
        if re.match(pattern, line.strip()):
            # 保存上一章
            if current_start > 0 or current_paras > 0:
                chunk = "\n".join(lines[current_start:i])
                chapters.append({
                    "title": current_title,
                    "para_count": max(1, chunk.count("\n\n")),
                    "line_start": current_start,
                    "line_end": i,
                })

            current_title = line.strip().lstrip("#").strip()
            current_start = i
            current_paras = 0

    # 最后一章
    chunk = "\n".join(lines[current_start:])
    if chunk.strip():
        chapters.append({
            "title": current_title,
            "para_count": max(1, chunk.count("\n\n")),
            "line_start": current_start,
            "line_end": len(lines),
        })

    return chapters


def _fuzzy_match_paper(query, papers):
    """模糊匹配范文名"""
    query_lower = query.lower().replace(" ", "").replace("_", "")

    # 精确匹配
    if query in papers:
        return query

    # 包含匹配
    for name in papers:
        name_lower = name.lower().replace(" ", "").replace("_", "")
        if query_lower in name_lower or name_lower in query_lower:
            return name

    # 部分匹配（取 query 中最长的连续子串）
    for name in papers:
        name_lower = name.lower()
        if any(w in name_lower for w in query_lower.split() if len(w) >= 2):
            return name

    return None


def _extract_chapter(text, chapter_query):
    """从全文中提取指定章节"""
    lines = text.split("\n")
    chapters = _parse_chapters(text)

    # 模糊匹配章节标题
    query_lower = str(chapter_query).lower().replace(" ", "")

    for ch in chapters:
        title_lower = ch["title"].lower().replace(" ", "")
        if query_lower in title_lower or title_lower in query_lower:
            content = "\n".join(lines[ch["line_start"]:ch["line_end"]])
            if len(content) > 4000:
                content = content[:4000] + "\n\n... [截断]"
            return content

    # 如果 chapter_query 是数字，按序号取
    try:
        idx = int(chapter_query)
        if 0 <= idx < len(chapters):
            ch = chapters[idx]
            content = "\n".join(lines[ch["line_start"]:ch["line_end"]])
            if len(content) > 4000:
                content = content[:4000] + "\n\n... [截断]"
            return content
    except (ValueError, TypeError):
        pass

    return f"[未找到章节: {chapter_query}]"


def _extract_by_keyword(text, keyword, context_chars=1500):
    """按关键词搜索，返回关键词周围的上下文"""
    pos = text.find(keyword)
    if pos == -1:
        # 尝试不区分大小写
        pos = text.lower().find(keyword.lower())

    if pos == -1:
        return f"[未在范文中找到关键词: {keyword}]"

    start = max(0, pos - context_chars // 2)
    end = min(len(text), pos + len(keyword) + context_chars // 2)

    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    return snippet
