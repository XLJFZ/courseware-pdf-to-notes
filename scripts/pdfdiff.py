#!/usr/bin/env python3
"""逐页比较文本和 2× 渲染图；相似度仅用于安排复核，不证明内容等价。"""
import argparse
import difflib
import hashlib
import re
import sys

try:
    import pymupdf
except ImportError:
    sys.exit("缺少依赖，请先安装：python -m pip install pymupdf")


def load_pages(path):
    with pymupdf.open(path) as doc:
        return [page.get_text("text").strip() for page in doc]


def visual_hash(page):
    # 每次只保留单页像素，避免整本 PDF 图像常驻内存。
    pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
    return (pix.width, pix.height, hashlib.sha256(pix.samples).digest())


def critical_tokens(text):
    return re.findall(r"\d+(?:\.\d+)?|[+−–\-±×÷=<>≤≥∑√^]|\b(?:mm|cm|km|m|s|kg|g|N|kN|Pa|kPa|MPa|J|W|V|A|Hz)\b", text)


def compare_pages(old, new, min_ratio=0.99):
    rows = []
    for i in range(min(len(old), len(new))):
        a, b = old[i], new[i]
        ta, tb = a.get_text("text").strip(), b.get_text("text").strip()
        na, nb = re.sub(r"\s+", "", ta), re.sub(r"\s+", "", tb)
        visual_changed = visual_hash(a) != visual_hash(b)
        if not ta or not tb:
            kind = "无文字/空文字页，需视觉核对"
        elif critical_tokens(ta) != critical_tokens(tb):
            kind = "数字/单位/运算符变化，必须复核"
        elif na != nb:
            ratio = difflib.SequenceMatcher(None, na, nb, autojunk=False).ratio()
            kind = "高相似度文字变化，仍需复核" if ratio >= min_ratio else "文字内容变化，需复核"
        elif visual_changed:
            kind = "文字相同但渲染变化，需视觉核对"
        else:
            continue
        rows.append((i + 1, kind))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--min-ratio", type=float, default=0.99)
    ap.add_argument("--max-list", type=int, default=20)
    ap.add_argument("--dump-text", metavar="OUT")
    args = ap.parse_args()
    if not 0 <= args.min_ratio <= 1 or args.max_list < 1:
        ap.error("--min-ratio 必须在 0–1，--max-list 必须大于 0")
    with pymupdf.open(args.old) as old, pymupdf.open(args.new) as new:
        print("old pages: %d | new pages: %d" % (len(old), len(new)))
        if not len(old) or not len(new):
            ap.error("PDF 没有页面")
        rows = compare_pages(old, new, args.min_ratio)
        if args.dump_text:
            with open(args.dump_text, "w", encoding="utf-8") as f:
                f.write("### pages=%d\n" % len(new))
                for i, page in enumerate(new):
                    f.write("\n===== PAGE %d =====\n%s" % (i + 1, page.get_text("text").rstrip()))
        if rows:
            print("需复核 %d 页：" % len(rows))
            for number, kind in rows[:args.max_list]:
                print("  p%d: %s" % (number, kind))
            if len(rows) > args.max_list:
                print("  其余 %d 页未列出，可增大 --max-list" % (len(rows) - args.max_list))
        else:
            print("前 %d 页文本及 2× 渲染一致" % min(len(old), len(new)))
        if len(new) > len(old):
            print("尾部候选新增页: p%d–p%d（仅在前缀确认一致后才可仅处理此范围）" % (len(old) + 1, len(new)))
        elif len(old) > len(new):
            print("新 PDF 少 %d 页，需核对删页/重排" % (len(old) - len(new)))
        print("按相同页号比较；插页、删页、重排需人工确认，不自动判定超集。")


if __name__ == "__main__":
    main()
