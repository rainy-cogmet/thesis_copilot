#!/usr/bin/env python3
"""
run.py — 硕士论文修改 Harness 主编排脚本

四层嵌套循环：全文 → 章 → 段 → 句
"""

import json
import os
import sys
import time
import subprocess
import argparse
from datetime import datetime

from thesis_parser import parse_thesis, rebuild_thesis, get_chapter_text, get_paragraph_text
from agent import (
    student_revise_sentence,
    student_fix_sentences,
    student_fix_chapter,
    student_restructure_chapter,
    advisor_review_sentence,
    advisor_review_paragraph,
    advisor_review_chapter,
    advisor_review_structure,
    advisor_final_review,
)


# ============================================================
# 全局运行时状态
# ============================================================

_run_timestamp: str = ""  # 本次运行的时间戳，在 main() 中初始化


# ============================================================
# 工具函数
# ============================================================

def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def log(msg, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    prefix = {"INFO": "📝", "OK": "✅", "FAIL": "❌", "WARN": "⚠️", "STEP": "🔄"}
    icon = prefix.get(level, "📝")
    print(f"[{timestamp}] {icon} {msg}")


def _get_run_log_dir() -> str:
    """获取本次运行的日志目录：logs/<timestamp>/"""
    config = load_config()
    return os.path.join(config["logs_dir"], _run_timestamp)


def save_log(data, *path_parts):
    """保存审阅日志到带时间戳的目录"""
    log_path = os.path.join(_get_run_log_dir(), *path_parts)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_state():
    """加载断点续传状态"""
    config = load_config()
    state_file = config["state_file"]
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_state(state):
    """保存当前进度"""
    config = load_config()
    os.makedirs(os.path.dirname(config["state_file"]), exist_ok=True)
    with open(config["state_file"], "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def convert_docx_to_md(docx_path, md_path):
    """使用 pandoc 将 docx 转换为 markdown"""
    log(f"正在将 {docx_path} 转换为 Markdown...")
    try:
        subprocess.run(
            ["pandoc", docx_path, "-t", "markdown", "-o", md_path, "--wrap=none"],
            check=True,
            capture_output=True,
        )
        log(f"转换完成: {md_path}", "OK")
    except FileNotFoundError:
        log("未找到 pandoc，请先安装: brew install pandoc 或 apt install pandoc", "FAIL")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        log(f"pandoc 转换失败: {e.stderr.decode()}", "FAIL")
        sys.exit(1)


def convert_md_to_docx(md_path, docx_path):
    """使用 pandoc 将 markdown 转回 docx"""
    log(f"正在将 Markdown 转换回 {docx_path}...")
    try:
        subprocess.run(
            ["pandoc", md_path, "-o", docx_path],
            check=True,
            capture_output=True,
        )
        log(f"转换完成: {docx_path}", "OK")
    except subprocess.CalledProcessError as e:
        log(f"pandoc 转换失败: {e.stderr.decode()}", "FAIL")


def get_sentence_context(para, sent_idx, window=1):
    """获取句子的上下文（前后各 window 个句子）"""
    sentences = para["sentences"]
    start = max(0, sent_idx - window)
    end = min(len(sentences), sent_idx + window + 1)

    parts = []
    for i in range(start, end):
        marker = " >>> " if i == sent_idx else "     "
        parts.append(f"{marker}{sentences[i]}")
    return "\n".join(parts)


def get_paragraph_context(chapter, para_idx, window=1):
    """获取段落的上下文（前后各 window 个段落的摘要）"""
    paragraphs = chapter["paragraphs"]
    parts = []

    for i in range(max(0, para_idx - window), min(len(paragraphs), para_idx + window + 1)):
        text = get_paragraph_text(paragraphs[i])
        if i == para_idx:
            parts.append(f"[当前段] {text}")
        else:
            # 只取前80字作为摘要
            summary = text[:80] + "..." if len(text) > 80 else text
            parts.append(f"[第{i}段] {summary}")

    return "\n\n".join(parts)


# ============================================================
# 范围过滤
# ============================================================

def get_scope():
    """读取 config 中的 scope 配置"""
    config = load_config()
    scope = config.get("scope", {})
    mode = scope.get("mode", "all")
    return mode, scope


def should_process_chapter(ch_idx):
    """判断这一章是否在处理范围内"""
    mode, scope = get_scope()
    if mode == "all":
        return True
    chapters = scope.get("chapters", [])
    return ch_idx in chapters


def should_process_paragraph(ch_idx, para_idx):
    """判断这一段是否在处理范围内"""
    mode, scope = get_scope()
    if mode == "all":
        return True
    if not should_process_chapter(ch_idx):
        return False
    para_spec = scope.get("paragraphs", {})
    ch_key = str(ch_idx)
    if ch_key not in para_spec:
        return True  # 章在范围内但未指定段 → 处理全章
    val = para_spec[ch_key]
    if val == "all":
        return True
    if isinstance(val, list):
        return para_idx in val
    return True


def should_skip_final_review():
    """是否跳过全文终审"""
    mode, scope = get_scope()
    return scope.get("skip_final_review", False) if mode == "selected" else False


# ============================================================
# 核心循环
# ============================================================

def process_sentence_loop(chapter, ch_idx, para, para_idx):
    """L4: 句级循环 — 逐句修改 + 审阅"""
    if para.get("is_heading_only") or not para["sentences"]:
        return

    chapter_title = chapter["title"]
    log(f"  段 {para_idx}: {len(para['sentences'])} 个句子")

    for s_idx in range(len(para["sentences"])):
        sentence = para["sentences"][s_idx]
        context = get_sentence_context(para, s_idx)

        # 学生修改
        revised = student_revise_sentence(sentence, context, chapter_title, para_idx, chapter_idx=ch_idx)
        if revised != sentence:
            log(f"    句 {s_idx}: 已修改", "STEP")
            para["sentences"][s_idx] = revised
        else:
            log(f"    句 {s_idx}: 无需修改")

        # 导师审阅
        review = advisor_review_sentence(
            para["sentences"][s_idx], context, chapter_title, para_idx
        )

        save_log(
            {"sentence": para["sentences"][s_idx], "original": sentence, "review": review},
            f"chapter_{ch_idx}", f"para_{para_idx}", f"sentence_{s_idx}.json",
        )


def process_paragraph_loop(structure, ch_idx, chapter):
    """L3: 段级循环 — 逐段处理，含段级审阅和回退"""
    config = load_config()
    max_retries = config.get("max_paragraph_retries", 2)
    chapter_title = chapter["title"]

    for para_idx, para in enumerate(chapter["paragraphs"]):
        if para.get("is_heading_only"):
            continue
        if not should_process_paragraph(ch_idx, para_idx):
            log(f"  段 {para_idx}: 跳过（不在处理范围内）")
            continue

        # --- L4: 句级循环 ---
        process_sentence_loop(chapter, ch_idx, para, para_idx)

        # --- 段级审阅 ---
        for retry in range(max_retries + 1):
            para_text = get_paragraph_text(para)
            para_context = get_paragraph_context(chapter, para_idx)

            review = advisor_review_paragraph(
                para_text, para_context, chapter_title, para_idx
            )

            save_log(
                {"paragraph": para_text, "review": review, "retry": retry},
                f"chapter_{ch_idx}", f"para_{para_idx}", "paragraph_review.json",
            )

            if review.get("pass", True):
                log(f"  段 {para_idx}: 审阅通过 ✓", "OK")
                break

            if retry < max_retries:
                log(f"  段 {para_idx}: 审阅未通过 (第{retry+1}次)，修复问题句...", "FAIL")
                flagged = review.get("flagged_sentences", [])

                # 提取导师引用的范文片段
                reference_content = ""
                refs = review.get("references", [])
                if refs:
                    from sample_index import extract_from_advisor_references
                    reference_content = extract_from_advisor_references(refs)
                    log(f"    导师引用了 {len(refs)} 处范文", "STEP")

                if flagged:
                    # 只修复导师指出的问题句
                    fixes = student_fix_sentences(
                        flagged, para_text, chapter_title, para_idx,
                        reference_content=reference_content,
                    )

                    # 应用修复
                    for fix in fixes:
                        original = fix.get("original", "")
                        revised = fix.get("revised", "")
                        if original and revised:
                            for i, s in enumerate(para["sentences"]):
                                if original in s:
                                    para["sentences"][i] = s.replace(original, revised)
                                    break
            else:
                log(f"  段 {para_idx}: 达到最大重试次数，继续推进", "WARN")

        # 每段处理完后保存论文和进度
        rebuild_thesis(structure, config["thesis_md"])
        save_state({
            "phase": "paragraph",
            "chapter_idx": ch_idx,
            "para_idx": para_idx,
            "timestamp": datetime.now().isoformat(),
        })


def process_chapter_loop(structure):
    """L2: 章级循环 — 逐章处理，含章级审阅和回退"""
    config = load_config()
    max_retries = config.get("max_chapter_retries", 2)

    for ch_idx, chapter in enumerate(structure["chapters"]):
        if not should_process_chapter(ch_idx):
            log(f"\n  章 {ch_idx}: {chapter['title']} — 跳过（不在处理范围内）")
            continue

        log(f"\n{'='*50}")
        log(f"章 {ch_idx}: {chapter['title']} ({len(chapter['paragraphs'])} 段)")
        log(f"{'='*50}")

        # --- 结构审阅（在逐句修改之前） ---
        chapter_text = get_chapter_text(structure, ch_idx)
        struct_review = advisor_review_structure(
            chapter_text, chapter["title"], chapter["paragraphs"]
        )

        save_log(
            {"chapter": chapter["title"], "review": struct_review},
            f"chapter_{ch_idx}", "structure_review.json",
        )

        if struct_review.get("needs_restructure", False):
            actions = struct_review.get("actions", [])
            log(f"  导师要求调整段落结构: {len(actions)} 项操作", "STEP")
            for act in actions:
                log(f"    {act.get('type', '?')}: {act.get('instruction', '')[:60]}", "STEP")

            # 学生执行结构调整
            feedback = struct_review.get("feedback", "") + "\n具体操作:\n"
            for act in actions:
                feedback += f"- {act.get('type')}: {act.get('instruction')}\n"

            new_text = student_restructure_chapter(
                chapter_text, feedback, chapter["title"]
            )

            # 重新解析章节结构
            _update_chapter_from_text(structure, ch_idx, new_text, config)
            rebuild_thesis(structure, config["thesis_md"])

            log(f"  结构调整完成: {len(chapter['paragraphs'])} 段", "OK")
        else:
            log(f"  段落结构合理，无需调整")

        # --- L3: 段级循环 ---
        process_paragraph_loop(structure, ch_idx, chapter)

        # --- 章级审阅 ---
        for retry in range(max_retries + 1):
            chapter_text = get_chapter_text(structure, ch_idx)
            review = advisor_review_chapter(chapter_text, chapter["title"])

            save_log(
                {"chapter": chapter["title"], "review": review, "retry": retry},
                f"chapter_{ch_idx}", "chapter_review.json",
            )

            if review.get("pass", True):
                log(f"章 {ch_idx} ({chapter['title']}): 审阅通过 ✓", "OK")
                break

            if retry < max_retries:
                log(f"章 {ch_idx}: 审阅未通过 (第{retry+1}次)，局部修补...", "FAIL")
                feedback = review.get("feedback", "") + "\n具体问题:\n"
                for issue in review.get("issues", []):
                    feedback += f"- [{issue.get('location','')}] {issue.get('issue','')}\n"
                    feedback += f"  建议: {issue.get('suggestion','')}\n"

                # 学生做局部修补
                fixed_text = student_fix_chapter(
                    chapter_text, feedback, chapter["title"]
                )

                # 重新解析修补后的章节并更新结构
                _update_chapter_from_text(structure, ch_idx, fixed_text, config)
            else:
                log(f"章 {ch_idx}: 达到最大重试次数，继续推进", "WARN")

        # 章处理完后保存
        rebuild_thesis(structure, config["thesis_md"])
        save_state({
            "phase": "chapter",
            "chapter_idx": ch_idx,
            "timestamp": datetime.now().isoformat(),
        })

        # 输出本章修改结果到 outputs/
        _save_chapter_output(structure, ch_idx)


def _save_chapter_output(structure, ch_idx):
    """将处理完的章节以 md 格式保存到 outputs/<timestamp>/ 下"""
    output_dir = os.path.join("outputs", _run_timestamp)
    os.makedirs(output_dir, exist_ok=True)

    chapter = structure["chapters"][ch_idx]
    chapter_text = get_chapter_text(structure, ch_idx)

    filename = f"chapter_{ch_idx}_{chapter['title']}.md"
    # 清理文件名中的非法字符
    filename = "".join(c if c.isalnum() or c in "._-— " else "_" for c in filename)
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(chapter_text)

    log(f"  章 {ch_idx} 结果已保存到: {filepath}", "OK")


def _update_chapter_from_text(structure, ch_idx, new_text, config):
    """用修补后的文本更新章节结构"""
    from thesis_parser import _parse_paragraphs

    chapter = structure["chapters"][ch_idx]
    delimiters = config.get("sentence_delimiters", ["。", "！", "？"])
    min_len = config.get("min_sentence_length", 4)

    # 去掉章标题行
    lines = new_text.strip().split("\n")
    body_lines = []
    for line in lines:
        if line.startswith("# ") and chapter["title"] in line:
            continue
        body_lines.append(line)

    body = "\n".join(body_lines)
    chapter["paragraphs"] = _parse_paragraphs(body, delimiters, min_len)


def process_document_loop(structure):
    """L1: 全文循环 — 含全文终审和回退"""
    config = load_config()
    max_rounds = config.get("max_doc_rounds", 3)

    for doc_round in range(1, max_rounds + 1):
        log(f"\n{'#'*60}")
        log(f"全文修改 第 {doc_round}/{max_rounds} 轮")
        log(f"{'#'*60}")

        # --- L2: 章级循环 ---
        process_chapter_loop(structure)

        # --- 全文终审 ---
        rebuild_thesis(structure, config["thesis_md"])

        if should_skip_final_review():
            log("已跳过全文终审（selected 模式）", "OK")
            return True

        with open(config["thesis_md"], "r", encoding="utf-8") as f:
            full_text = f.read()

        log(f"\n{'='*50}")
        log("全文终审中...")
        log(f"{'='*50}")

        review = advisor_final_review(full_text)

        save_log(
            {"round": doc_round, "review": review},
            f"round_{doc_round}", "final_review.json",
        )

        score = review.get("score", 0)
        passed = review.get("pass", False)

        log(f"终审评分: {score}/10")
        log(f"终审意见: {review.get('feedback', '')}")

        if passed:
            log(f"🎉 全文终审通过！（第 {doc_round} 轮）", "OK")
            return True

        if doc_round < max_rounds:
            log(f"全文终审未通过，准备第 {doc_round + 1} 轮...", "FAIL")

            # 打印各章问题
            chapter_issues = review.get("chapter_issues", {})
            if chapter_issues:
                for ch_name, issue in chapter_issues.items():
                    log(f"  {ch_name}: {issue}", "WARN")

            # 重新解析论文（因为可能在修改过程中结构有变化）
            structure.update(
                parse_thesis(config["thesis_md"], config.get("chapter_heading_level", 1))
            )
        else:
            log(f"达到最大轮数 ({max_rounds})，停止循环", "WARN")

    return False


# ============================================================
# 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="硕士论文修改 Harness")
    parser.add_argument("--resume", action="store_true", help="从上次中断处继续")
    parser.add_argument("--skip-convert", action="store_true", help="跳过 docx→md 转换")
    parser.add_argument("--dry-run", action="store_true", help="试运行，只解析不调用 Agent")
    args = parser.parse_args()

    config = load_config()

    # 初始化本次运行时间戳
    global _run_timestamp
    _run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 确保目录存在
    for d in [config["logs_dir"], "state", "thesis", "outputs"]:
        os.makedirs(d, exist_ok=True)

    # Step 1: 转换 docx → markdown
    if not args.skip_convert and os.path.exists(config["thesis_docx"]):
        convert_docx_to_md(config["thesis_docx"], config["thesis_md"])
    elif not os.path.exists(config["thesis_md"]):
        log("请先将论文文件放到 thesis/ 目录下", "FAIL")
        log(f"  .docx 文件放到: {config['thesis_docx']}")
        log(f"  或 .md 文件放到: {config['thesis_md']}")
        sys.exit(1)

    # Step 2: 解析论文结构
    log("正在解析论文结构...")
    structure = parse_thesis(config["thesis_md"], config.get("chapter_heading_level", 1))

    # Step 2.5: 建立范文索引
    from sample_index import build_index, get_summary_for_advisor
    log("正在索引范文...")
    build_index(config.get("rules_dir", "rules"))
    summary = get_summary_for_advisor()
    if "未提供" not in summary:
        log(f"范文已就绪（按需提取，不预加载全文）", "OK")
    else:
        log("未检测到范文文件，跳过范文索引")

    total_chapters = len(structure["chapters"])
    total_paragraphs = sum(len(ch["paragraphs"]) for ch in structure["chapters"])
    total_sentences = sum(
        len(p["sentences"])
        for ch in structure["chapters"]
        for p in ch["paragraphs"]
        if not p.get("is_heading_only")
    )

    log(f"论文结构: {total_chapters} 章, {total_paragraphs} 段, {total_sentences} 句")

    mode, scope = get_scope()
    if mode == "selected":
        log(f"🎯 精确模式: 只处理指定的章节和段落")
    else:
        log(f"📖 全文模式: 处理所有章节")

    for ch in structure["chapters"]:
        ch_idx = ch["index"]
        will_process = should_process_chapter(ch_idx)
        marker = "→" if will_process else "  (跳过)"
        log(f"  {marker} 章 {ch_idx}: {ch['title']} ({len(ch['paragraphs'])} 段)")

        if will_process and mode == "selected":
            for p in ch["paragraphs"]:
                if not p.get("is_heading_only"):
                    p_ok = should_process_paragraph(ch_idx, p["index"])
                    pm = "    →" if p_ok else "      (跳过)"
                    preview = "".join(p["sentences"])[:40] + "..."
                    log(f"  {pm} 段 {p['index']}: {len(p['sentences'])}句 {preview}")

    if args.dry_run:
        log("试运行完成（未调用 Agent）", "OK")
        return

    # Step 3: 运行四层循环
    start_time = time.time()
    passed = process_document_loop(structure)
    elapsed = time.time() - start_time

    # Step 4: 输出结果
    log(f"\n{'#'*60}")
    log(f"运行完成! 耗时: {elapsed/60:.1f} 分钟")
    if passed:
        log("论文修改已通过导师终审 🎓", "OK")
    else:
        log("已达到最大轮数，请查看日志中的导师意见手动处理", "WARN")

    # 转回 docx
    if os.path.exists(config["thesis_md"]):
        convert_md_to_docx(config["thesis_md"], config["output_docx"])
        log(f"最终论文已输出到: {config['output_docx']}", "OK")

    log(f"审阅日志保存在: {_get_run_log_dir()}/")
    log(f"章节输出保存在: outputs/{_run_timestamp}/")


if __name__ == "__main__":
    main()
