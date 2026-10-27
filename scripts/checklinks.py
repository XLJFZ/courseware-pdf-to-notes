#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 Obsidian 笔记里的 ![[附件嵌入]] 与 [[wikilink]] 能否解析。

校验规则（带路径的笔记采用严格检查，不模拟 Obsidian 的全部回退行为）：
  * 附件嵌入 `![[assets/xxx.png]]` 按「后缀匹配」解析——只要 vault 里有唯一一个
    以该路径结尾的文件即命中；命中多个或不命中都会解析失败。
  * wikilink 有目录时核对路径；纯文件名检查存在性，同名目标提示歧义。

为什么要校验：笔记改名 / 挪目录后，链接会静默失效，Obsidian 只在点开时才发现。
改完笔记跑一次，比人工翻安全。

★ 为什么必须先「屏蔽非正文区域」：
  `[[` 在代码和公式里是极常见的写法——Python 嵌套列表 `dp = [[0]*(m+1)]`、
  TOML/pyproject 的 `[[package]]`、LaTeX 矩阵 `$G=[[c,-s],[s,c]]$`。
  不先屏蔽，脚本会把它们全报成「LINK UNRESOLVED」，假阳性高到无法使用。
  故先按等长空白遮蔽：围栏代码块（``` / ~~~）、行内代码（`x`）、
  行内数学（$x$）与块级数学（$$...$$）——等长替换是为了让报错行号仍然准确。

调用方式:
    python checklinks.py --vault "<vault 根目录>"
    python checklinks.py --vault "<vault 根目录>" --notes "<学科目录>"
    python checklinks.py --vault "..." --notes dirA --notes dirB --notes "MOC.md"

不传 --notes 时校验整个 vault 的所有 .md（自动跳过 Obsidian 回收站 `.trash`）。
"""
import argparse
import os
import posixpath
import re
import sys

# 模板/示例占位符：含这些字符的目标不是真链接（`[[<课程名>]]`、`[[00 ...]]`）
PLACEHOLDER_CHARS = ("<", ">", "…", "...", "{{", "}}")
# Obsidian 别名分隔符：`[[笔记｜别名]]` 全角竖线常被误写，取竖线左侧即可
ALIAS_SEPS = ("|", "｜", "#")
# 附件扩展名：`[[附件/x.pdf]]`、`[[图.png]]`（不带 !）也是合法用法——点开即附件。
# 这类目标要按「文件存在」校验，不能拿去查笔记名，否则全是假阳性。
ATTACH_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".avif",
    ".pdf", ".epub", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
    ".csv", ".mp4", ".mov", ".mp3", ".wav", ".m4a", ".zip", ".canvas",
}


def list_md(path):
    path = os.path.abspath(path)
    if os.path.isfile(path):
        return [path] if path.lower().endswith(".md") else []
    out = []
    for dp, _dn, fn in os.walk(path):
        out += [os.path.join(dp, f) for f in fn if f.lower().endswith(".md")]
    return out


def _spaces(s):
    """等长空白替换（保留换行）。长度必须不变，否则后续报错行号会漂。"""
    return re.sub(r"[^\n]", " ", s)


def mask_non_prose(text):
    """把代码块 / 行内代码 / 数学公式替换为**等长**空白，保留换行与列位置。

    为什么必须等长：正则匹配得到的偏移还要拿去 raw 文本里换算行号。
    只要遮蔽过程改变了长度，报出的行号就会一路偏下去（踩过：代码块按整行删除后，
    后面所有行号少了 4 行）。所以这里一律「同长度空格替换」，不用删除。
    """
    # 1) 围栏代码块（``` 或 ~~~），整块连行内字符一起置为等长空白
    lines, fence = [], None
    for line in text.split("\n"):
        s = line.strip()
        if fence is None:
            if s.startswith("```") or s.startswith("~~~"):
                fence = s[:3]
                lines.append(_spaces(line))
                continue
            lines.append(line)
        else:
            if s.startswith(fence):
                fence = None
            lines.append(_spaces(line))
    text = "\n".join(lines)

    # 2) 块级数学 $$...$$（可跨行）
    text = re.sub(r"\$\$[\s\S]*?\$\$", lambda m: _spaces(m.group(0)), text)
    # 3) 行内代码 `...` 与行内数学 $...$
    text = re.sub(r"`[^`\n]*`", lambda m: _spaces(m.group(0)), text)
    text = re.sub(r"(?<!\\)\$[^$\n]*\$", lambda m: _spaces(m.group(0)), text)
    return text


def clean_target(t):
    """统一清洗捕获到的链接目标。"""
    t = t.strip().rstrip("\\").strip()
    for sep in ALIAS_SEPS:
        t = t.split(sep)[0].strip()
    return t


def is_placeholder(t):
    return any(c in t for c in PLACEHOLDER_CHARS)


def is_attachment(t):
    """目标是否指向附件（而不是笔记）。带已知附件后缀即算。"""
    return os.path.splitext(os.path.basename(t))[1].lower() in ATTACH_EXTS


def main():
    ap = argparse.ArgumentParser(description="校验 Obsidian 笔记里的嵌入与 wikilink 是否可解析")
    ap.add_argument("--vault", required=True, help="vault 根目录")
    ap.add_argument("--notes", action="append", default=None,
                    help="要校验的笔记文件或目录（相对 vault 或绝对路径），可重复；缺省=整个 vault")
    ap.add_argument("--exclude", action="append", default=None,
                    help="额外跳过路径中含该片段的笔记，可重复（例：--exclude _备份）。"
                         "历史备份里的失效链接通常无需修，否则会淹没真问题")
    args = ap.parse_args()

    vault = os.path.abspath(args.vault)
    if not os.path.isdir(vault):
        sys.exit("vault 不存在: %s" % vault)

    # 全 vault 的 md 文件名集合（wikilink 解析用）
    note_names = set()
    note_paths = []
    # 全 vault 的相对路径（附件后缀匹配用）
    all_rel = []
    for dp, _dn, fn in os.walk(vault):
        _dn[:] = [d for d in _dn if d != ".trash"]
        for f in fn:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, vault).replace("\\", "/")
            all_rel.append(rel)
            if f.lower().endswith(".md"):
                note_names.add(os.path.splitext(f)[0])
                note_paths.append(rel[:-3])

    def resolves_suffix(linkpath):
        """三态返回，模拟 Obsidian 的解析顺序。

        * "ok"    路径后缀命中且唯一
        * "stale" 路径后缀没命中，但按**文件名**唯一命中——Obsidian 会回退到文件名匹配，
                  链接其实点得开，只是写的路径已经过期（挪过目录 / 目录改过名）。
                  这种情况不该报成错误，但值得提示，否则「路径写着 A 实际在 B」会一直烂在那儿。
        * "miss"  真的找不到
        """
        lp = linkpath.replace("\\", "/")
        while lp.startswith("./"):
            lp = lp[2:]          # 只剥开头的 "./"；不能用 lstrip("./")，那会按字符集误伤
        if sum(1 for r in all_rel if r == lp or r.endswith("/" + lp)) == 1:
            return "ok"
        tail = lp.rsplit("/", 1)[-1]
        if sum(1 for r in all_rel if r.rsplit("/", 1)[-1] == tail) == 1:
            return "stale"
        return "miss"

    if args.notes:
        targets = []
        for n in args.notes:
            path = n if os.path.isabs(n) else os.path.join(vault, n)
            if not os.path.exists(path):
                ap.error("笔记路径不存在: %s" % n)
            found = list_md(path)
            if not found:
                ap.error("笔记路径中没有 Markdown 笔记: %s" % n)
            targets += found
    else:
        targets = list_md(vault)
    targets = sorted(set(targets))
    # Obsidian 回收站（.trash）里的旧笔记链接失效是正常的，一律跳过，避免淹没真问题
    excludes = list(args.exclude or []) + [".trash"]
    targets = [f for f in targets
               if not any(x and x in os.path.relpath(f, vault).replace("\\", "/")
                          for x in excludes)]

    if not targets:
        ap.error("没有可校验的 Markdown 笔记（检查路径及排除条件）")

    # 正则：[^\]|#] 到 | # 为止；表格里为转义写成 `\|`，故捕获后要 rstrip("\\")
    emb_re = re.compile(r"!\[\[([^\]|#]+)")
    lnk_re = re.compile(r"(?<!!)\[\[([^\]|#]+)")

    problems, warns, checked, skipped = [], [], 0, 0

    def check_attach(kind, name, line, t):
        st = resolves_suffix(t)
        if st == "miss":
            problems.append("%s UNRESOLVED %s:%d -> %s" % (kind, name, line, t))
        elif st == "stale":
            warns.append("STALE PATH        %s:%d -> %s（文件存在但路径已过期）" % (name, line, t))
        return st

    def check_note(kind, name, line, t):
        # 普通链接与嵌入笔记共享路径规则；只剥 .md，保留版本号中的点。
        target = t.replace("\\", "/")
        target = target[:-3] if target.lower().endswith(".md") else target
        if "/" in target:
            relative = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
            if target not in note_paths and relative not in note_paths:
                problems.append("%s UNRESOLVED   %s:%d -> %s" % (kind, name, line, t))
        else:
            hits = [p for p in note_paths if p.rsplit("/", 1)[-1] == target]
            if not hits:
                problems.append("%s UNRESOLVED   %s:%d -> %s" % (kind, name, line, t))
            elif len(hits) > 1:
                warns.append("AMBIGUOUS LINK    %s:%d -> %s（同名笔记，请写明确路径）" % (name, line, t))

    for f in targets:
        if not os.path.isfile(f):
            problems.append("FILE MISSING      %s" % f)
            continue
        checked += 1
        raw = open(f, encoding="utf-8").read()
        text = mask_non_prose(raw)
        name = os.path.relpath(f, vault).replace("\\", "/")

        def lineno(pos):
            return raw.count("\n", 0, pos) + 1

        for m in emb_re.finditer(text):
            t = clean_target(m.group(1))
            if not t:
                continue
            if is_placeholder(t):
                skipped += 1
                continue
            if is_attachment(t):
                check_attach("EMBED", name, lineno(m.start()), t)
            else:
                check_note("EMBED", name, lineno(m.start()), t)
        for m in lnk_re.finditer(text):
            t = clean_target(m.group(1))
            if not t:
                continue
            if is_placeholder(t):
                skipped += 1
                continue
            if is_attachment(t):
                # 普通 wikilink 指向附件（`[[附件/x.pdf]]`）：校验文件在不在，不查笔记名
                check_attach("ATTACH", name, lineno(m.start()), t)
                continue
            check_note("LINK", name, lineno(m.start()), t)

    print("checked notes: %d" % checked)
    print("vault md files: %d | vault files: %d" % (len(note_names), len(all_rel)))
    print("skipped placeholders: %d" % skipped)
    if warns:
        print("--- warnings (%d，不影响结论) ---" % len(warns))
        print("\n".join(warns))
    if problems:
        print("--- problems (%d) ---" % len(problems))
        print("\n".join(problems))
        sys.exit(1)
    print("OK: 所有图片嵌入与笔记链接均可解析")


if __name__ == "__main__":
    main()
