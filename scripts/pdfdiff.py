#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐页比对两份 PDF，定位新增页范围，并用文本相似度区分「改字」与「内容重做」。

为什么需要它：课件 PDF 常出现「超集版本」——新文件是旧文件的前缀 + 若干新增页。
逐页比文字即可定位分界点，避免整份重做。但超集版里也常混着拼写/日期微改，
这类差异相似度极高（≥ 0.99），**不应触发重导图或改笔记**，所以要用相似度把两类分开。

用法:
    python pdfdiff.py OLD.pdf NEW.pdf
    python pdfdiff.py OLD.pdf NEW.pdf --dump-text out.txt
    python pdfdiff.py OLD.pdf NEW.pdf --min-ratio 0.98

依赖: pymupdf
"""
import argparse
import difflib
import re
import sys

try:
    import pymupdf
except ImportError:
    sys.exit("缺少依赖，请先安装： python -m pip install pymupdf")


def load_pages(path):
    """返回每页的文字层（已 strip）。注意：公式与图片里的数字抽不出来，属正常。"""
    with pymupdf.open(path) as doc:
        return [page.get_text("text").strip() for page in doc]


def main():
    ap = argparse.ArgumentParser(
        description="逐页比对两份 PDF，定位新增页范围（用相似度区分改字 / 重做）"
    )
    ap.add_argument("old", help="旧 PDF")
    ap.add_argument("new", help="新 PDF（通常是旧文件的超集）")
    ap.add_argument("--min-ratio", type=float, default=0.99,
                    help="相似度门槛：>= 该值视为「改字」，否则视为「内容重做」（默认 0.99）")
    ap.add_argument("--dump-text", metavar="OUT",
                    help="把新 PDF 的文字层写到 OUT，便于通读结构")
    ap.add_argument("--max-list", type=int, default=20, help="每类最多列出多少页（默认 20）")
    args = ap.parse_args()

    old, new = load_pages(args.old), load_pages(args.new)
    print("old pages: %d | new pages: %d" % (len(old), len(new)))

    if args.dump_text:
        with open(args.dump_text, "w", encoding="utf-8") as f:
            f.write("### pages=%d\n" % len(new))
            for i, t in enumerate(new):
                f.write("\n===== PAGE %d =====\n%s" % (i + 1, t.rstrip()))
        print("文字层已写入:", args.dump_text)

    n = min(len(old), len(new))
    norm = lambda s: re.sub(r"\s+", "", s)   # 忽略空白差异，避免排版微调被当成内容改动

    first, typos, rewrites = None, [], []
    for i in range(n):
        if old[i] != new[i]:
            ratio = difflib.SequenceMatcher(None, norm(old[i]), norm(new[i])).ratio()
            (typos if ratio >= args.min_ratio else rewrites).append((i + 1, ratio))
            if first is None:
                first = i + 1

    if first is None:
        print("前 %d 页逐页文字完全一致" % n)
    else:
        print("首个差异页: %d" % first)
        fmt = lambda seq: ", ".join("p%d(%.3f)" % (p, r) for p, r in seq[:args.max_list])
        print("  改字 %d 页: %s" % (len(typos), fmt(typos) or "-"))
        print("  重做 %d 页: %s" % (len(rewrites), fmt(rewrites) or "-"))
        print("  → 只有「重做」的页需要回看渲染图重新整理；「改字」页原样复用即可")

    if len(new) > n:
        print("新增页: p%d–p%d（共 %d 页）" % (n + 1, len(new), len(new) - n))
    elif len(old) > len(new):
        print("提示: 旧文件比新文件多 %d 页" % (len(old) - len(new)))


if __name__ == "__main__":
    main()
