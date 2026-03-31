"""
thesis_parser.py — 将 Markdown 论文解析为 章→段→句 的三层结构，并支持回写
"""

import re
import json


def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def split_sentences(text, delimiters=None, min_length=4):
    """按中英文句号等切分句子"""
    if delimiters is None:
        delimiters = ["。", "！", "？", "；", ".", "!", "?", ";"]

    pattern = "([" + re.escape("".join(delimiters)) + "])"
    parts = re.split(pattern, text)

    sentences = []
    current = ""
    for part in parts:
        current += part
        if part in delimiters and len(current.strip()) >= min_length:
            sentences.append(current.strip())
            current = ""
    if current.strip():
        if sentences:
            sentences[-1] += current.strip()
        else:
            sentences.append(current.strip())

    return sentences


def parse_thesis(md_path, heading_level=1):
    """
    解析 Markdown 论文为结构化数据

    返回:
    {
        "chapters": [
            {
                "index": 0,
                "title": "第一章 绪论",
                "heading_line": "# 第一章 绪论",
                "paragraphs": [
                    {
                        "index": 0,
                        "sentences": ["句子1。", "句子2。"],
                        "raw": "句子1。句子2。"
                    },
                    ...
                ]
            },
            ...
        ],
        "preamble": "标题页等章节前内容"
    }
    """
    config = load_config()
    delimiters = config.get("sentence_delimiters", ["。", "！", "？"])
    min_len = config.get("min_sentence_length", 4)

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    heading_prefix = "#" * heading_level + " "
    lines = content.split("\n")
    tail_markers = config.get("tail_markers", ["参考文献", "致谢", "附录", "References", "Bibliography"])

    chapters = []
    current_chapter = None
    current_lines = []
    preamble_lines = []
    tail_lines = []
    in_tail = False

    for line in lines:
        # 检查是否进入尾部区域（参考文献、致谢等）
        if not in_tail and _is_tail_marker(line, tail_markers, heading_prefix):
            # 保存当前章
            if current_chapter is not None:
                current_chapter["_body_lines"] = current_lines
                chapters.append(current_chapter)
                current_chapter = None
                current_lines = []
            in_tail = True
            tail_lines.append(line)
            continue

        if in_tail:
            tail_lines.append(line)
            continue

        if line.startswith(heading_prefix) and not line.startswith(heading_prefix + "#"):
            # 遇到新章标题
            if current_chapter is not None:
                current_chapter["_body_lines"] = current_lines
                chapters.append(current_chapter)
            else:
                preamble_lines = current_lines[:]

            current_chapter = {
                "index": len(chapters),
                "title": line[len(heading_prefix):].strip(),
                "heading_line": line.strip(),
            }
            current_lines = []
        else:
            current_lines.append(line)

    # 最后一章
    if current_chapter is not None:
        current_chapter["_body_lines"] = current_lines
        chapters.append(current_chapter)
    else:
        preamble_lines = current_lines

    # 解析每章的段落和句子
    for ch in chapters:
        body = "\n".join(ch.pop("_body_lines"))
        paragraphs = _parse_paragraphs(body, delimiters, min_len)
        ch["paragraphs"] = paragraphs

    return {
        "chapters": chapters,
        "preamble": "\n".join(preamble_lines),
        "tail": "\n".join(tail_lines),
    }


def _is_tail_marker(line, markers, heading_prefix):
    """判断一行是否是尾部区域的起始标记"""
    stripped = line.strip()
    # 去除 markdown 格式标记（anchor、粗体、链接等）
    clean = re.sub(r'\[]\{[^}]*\}', '', stripped)       # []{#...}
    clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', clean)    # **text**
    clean = clean.strip()
    # 匹配有 # 前缀的标题
    if clean.startswith("#"):
        title = clean.lstrip("#").strip()
        for marker in markers:
            if marker in title:
                return True
    # 匹配无 # 前缀但独占一行的标记（如 pandoc 转换后可能没有 #）
    for marker in markers:
        if clean == marker or clean.startswith(marker + " ") or clean.startswith(marker + "\t"):
            return True
    return False


def _parse_paragraphs(body, delimiters, min_len):
    """将章节正文解析为段落列表"""
    raw_paragraphs = re.split(r"\n\s*\n", body)
    paragraphs = []

    for i, raw in enumerate(raw_paragraphs):
        raw = raw.strip()
        if not raw:
            continue

        # 跳过子标题行（##, ### 等），但保留在 raw 中
        text_for_sentences = re.sub(r"^#{2,}\s+.*$", "", raw, flags=re.MULTILINE).strip()

        if not text_for_sentences:
            # 纯子标题段，保留但不拆句
            paragraphs.append({
                "index": len(paragraphs),
                "sentences": [],
                "raw": raw,
                "is_heading_only": True,
            })
            continue

        sentences = split_sentences(text_for_sentences, delimiters, min_len)
        paragraphs.append({
            "index": len(paragraphs),
            "sentences": sentences,
            "raw": raw,
            "is_heading_only": False,
        })

    return paragraphs


def rebuild_thesis(structure, output_path):
    """从结构化数据重建 Markdown 文件"""
    parts = []

    if structure.get("preamble"):
        parts.append(structure["preamble"])
        parts.append("")

    for ch in structure["chapters"]:
        parts.append(ch["heading_line"])
        parts.append("")

        for para in ch["paragraphs"]:
            if para.get("is_heading_only"):
                parts.append(para["raw"])
            else:
                # 用修改后的句子重组段落
                parts.append("".join(para["sentences"]))
            parts.append("")

    # 保留尾部（参考文献、致谢等）
    if structure.get("tail"):
        parts.append(structure["tail"])

    content = "\n".join(parts)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return content


def get_chapter_text(structure, chapter_idx):
    """获取某一章的完整文本"""
    ch = structure["chapters"][chapter_idx]
    lines = [ch["heading_line"], ""]
    for para in ch["paragraphs"]:
        if para.get("is_heading_only"):
            lines.append(para["raw"])
        else:
            lines.append("".join(para["sentences"]))
        lines.append("")
    return "\n".join(lines)


def get_paragraph_text(para):
    """获取某段的完整文本"""
    if para.get("is_heading_only"):
        return para["raw"]
    return "".join(para["sentences"])


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python thesis_parser.py <path_to_md>")
        sys.exit(1)

    result = parse_thesis(sys.argv[1])
    print(f"Preamble: {len(result['preamble'])} chars")
    for ch in result["chapters"]:
        print(f"\nChapter {ch['index']}: {ch['title']}")
        print(f"  Paragraphs: {len(ch['paragraphs'])}")
        for p in ch["paragraphs"]:
            if not p.get("is_heading_only"):
                print(f"    Para {p['index']}: {len(p['sentences'])} sentences")
