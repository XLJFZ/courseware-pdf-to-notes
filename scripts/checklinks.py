#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 Obsidian 笔记里的 ![[附件嵌入]] 与 [[wikilink]] 能否解析。

规则（Obsidian 的实际行为）：
  * 附件嵌入 `![[assets/xxx.png]]` 按「后缀匹配」解析——只要 vault 里有唯一一个
    以该路径结尾的文件即命中；命中多个或不命中都会解析失败。
  * wikilink `[[笔记名]]` 按「文件名（不含扩展名）唯一」解析。

为什么要校验：笔记改名 / 挪目录后，链接会静默失效，Obsidian 只在点开时才发现。
改完笔记跑一次，比人工翻安全。

用法:
    python checklinks.py --vault "<vault 根目录>"
    python checklinks.py --vault "<vault 根目录>" --notes "<学科目录>"
    python checklinks.py --vault "..." --notes dirA --notes dirB --notes "MOC.md"

不传 --notes 时校验整个 vault 的所有 .md。
"""
import argparse
import os
import re
import sys


def list_md(path):
    path = os.path.abspath(path)
    if os.path.isfile(path):
        return [path]
    out = []
    for dp, _dn, fn in os.walk(path):
        out += [os.path.join(dp, f) for f in fn if f.lower().endswith(".md")]
    return out


def main():
    ap = argparse.ArgumentParser(description="校验 Obsidian 笔记里的嵌入与 wikilink 是否可解析")
    ap.add_argument("--vault", required=True, help="vault 根目录")
    ap.add_argument("--notes", action="append", default=None,
                    help="要校验的笔记文件或目录（相对 vault 或绝对路径），可重复；缺省=整个 vault")
    args = ap.parse_args()

    vault = os.path.abspath(args.vault)
    if not os.path.isdir(vault):
        sys.exit("vault 不存在: %s" % vault)

    # 全 vault 的 md 文件名集合（wikilink 解析用）
    note_names = set()
    # 全 vault 的相对路径（附件后缀匹配用）
    all_rel = []
    for dp, _dn, fn in os.walk(vault):
        for f in fn:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, vault).replace("\\", "/")
            all_rel.append(rel)
            if f.lower().endswith(".md"):
                note_names.add(os.path.splitext(f)[0])

    def resolves_suffix(linkpath):
        """Obsidian：linkpath 是某文件全路径的后缀（按 / 分段）即命中；必须唯一。"""
        lp = linkpath.lstrip("./").replace("\\", "/")
        hits = sum(1 for r in all_rel if r == lp or r.endswith("/" + lp))
        return hits == 1

    if args.notes:
        targets = []
        for n in args.notes:
            targets += list_md(n if os.path.isabs(n) else os.path.join(vault, n))
    else:
        targets = list_md(vault)
    targets = sorted(set(targets))

    # 正则：[^\]|#] 到 | # 为止；表格里为转义写成 `\|`，故捕获后要 rstrip("\\")
    emb_re = re.compile(r"!\[\[([^\]|#]+)")
    lnk_re = re.compile(r"(?<!!)\[\[([^\]|#]+)")

    problems, checked = [], 0
    for f in targets:
        if not os.path.isfile(f):
            problems.append("FILE MISSING      %s" % f)
            continue
        checked += 1
        text = open(f, encoding="utf-8").read()
        name = os.path.relpath(f, vault).replace("\\", "/")
        for m in emb_re.finditer(text):
            t = m.group(1).strip().rstrip("\\").strip()
            if t and not resolves_suffix(t):
                problems.append("EMBED UNRESOLVED  %s -> %s" % (name, t))
        for m in lnk_re.finditer(text):
            t = m.group(1).strip().rstrip("\\").strip()
            if not t:
                continue
            if t.replace("\\", "/").startswith("assets/"):
                continue   # 附件链接交给上面那条规则管
            base = os.path.splitext(os.path.basename(t))[0]
            if base not in note_names:
                problems.append("LINK UNRESOLVED   %s -> %s" % (name, t))

    print("checked notes: %d" % checked)
    print("vault md files: %d | vault files: %d" % (len(note_names), len(all_rel)))
    if problems:
        print("--- problems (%d) ---" % len(problems))
        print("\n".join(problems))
        sys.exit(1)
    print("OK: 所有图片嵌入与笔记链接均可解析")


if __name__ == "__main__":
    main()
