#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出（并可选删除）assets 目录里没有被任何笔记引用的「孤儿」配图。

典型场景：按页导出了一批 slide-*.png，改完笔记后有些页被删掉/合并了，
对应的图就没人引用。孤儿图会悄悄堆积，这个脚本负责找出来。

安全设计：
  * **默认只列出，不删**（dry-run）。要真删必须显式加 --delete。
  * 删除前强制**白名单**：文件名必须以 --prefix 开头、以 --ext 结尾，其余一律跳过。
  * 用 os.remove 删除（在 Git Bash 里 `rm` 可能卡住，改用 Python 更稳）。

用法:
    # 只看孤儿
    python orphan_assets.py --notes "<学科目录>" --assets "<学科目录>/assets"
    # 导出清单供复核
    python orphan_assets.py --notes ... --assets ... --write-list orphans.txt
    # 确认后删除
    python orphan_assets.py --notes ... --assets ... --delete
"""
import argparse
import glob
import os
import sys


def collect_notes(paths):
    out = []
    for p in paths:
        p = os.path.abspath(p)
        if os.path.isfile(p):
            out.append(p)
        else:
            for dp, _dn, fn in os.walk(p):
                out += [os.path.join(dp, f) for f in fn if f.lower().endswith(".md")]
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser(description="列出/删除 assets 中未被笔记引用的孤儿图")
    ap.add_argument("--notes", action="append", required=True,
                    help="笔记文件或目录（可重复）；这些文件的内容构成「引用池」")
    ap.add_argument("--assets", required=True, help="配图目录")
    ap.add_argument("--prefix", default="slide-", help="白名单前缀（默认 slide-）")
    ap.add_argument("--ext", default=".png", help="白名单后缀（默认 .png）")
    ap.add_argument("--write-list", metavar="OUT", help="把孤儿清单写到 OUT")
    ap.add_argument("--delete", action="store_true", help="真删除（不加则只列出）")
    args = ap.parse_args()

    assets = os.path.abspath(args.assets)
    if not os.path.isdir(assets):
        sys.exit("assets 目录不存在: %s" % assets)

    notes = collect_notes(args.notes)
    if not notes:
        sys.exit("没有找到任何笔记（--notes 给对了吗？）")
    blob = "\n".join(open(f, encoding="utf-8").read() for f in notes)

    candidates = sorted(
        os.path.basename(p) for p in glob.glob(os.path.join(assets, args.prefix + "*" + args.ext))
    )
    orphans = [name for name in candidates if name not in blob]

    print("notes: %d | candidates(%s*%s): %d | orphans: %d"
          % (len(notes), args.prefix, args.ext, len(candidates), len(orphans)))
    for name in orphans:
        print("  ORPHAN", name)

    if args.write_list and orphans:
        with open(args.write_list, "w", encoding="utf-8") as f:
            f.write("\n".join(orphans) + "\n")
        print("清单已写入:", args.write_list)

    if not args.delete:
        if orphans:
            print("\n（dry-run，未删除。确认后加 --delete 执行）")
        return

    deleted, skipped = 0, 0
    for name in orphans:
        if not (name.startswith(args.prefix) and name.endswith(args.ext)):
            print("  SKIP(非白名单):", name)
            skipped += 1
            continue
        os.remove(os.path.join(assets, name))
        deleted += 1
    print("\ndeleted=%d skipped=%d" % (deleted, skipped))
    rest = os.listdir(assets)
    for pre in sorted({args.prefix, "fig-", "svg-"}):
        print("  剩余 %s*: %d" % (pre, len([x for x in rest if x.startswith(pre)])))


if __name__ == "__main__":
    main()
