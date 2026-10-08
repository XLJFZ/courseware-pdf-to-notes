# courseware-pdf-to-notes

> 把课程课件 / 讲义 / PPT 导出的 PDF，转成（或补进）Obsidian 笔记的 Skill。

一个给 AI 编码助手用的 **Skill**：丢一份课件 PDF 进去，让它按统一结构整理成中英对照、带配图、可回查页码的课堂笔记；**新课件是旧课件超集时，只处理新增页**，不整份重做。

## 它能做什么

- **增量比对**：先跟已有 PDF 逐页比文字，定位首个差异页与新增页范围；用相似度把「改字」和「新内容」分开，避免把 `vetors→vectors` 这种拼写修正当成新页重做。
- **看图核对数值**：课件里的公式、矢量记号、图片数字基本抽不出文字层，改为**按页渲染成 PNG 再直接读图**核对；关键细节（箭头方向、梯形哪端更高、零线位置）强制 4–6× 裁剪放大确认。
- **自动补全解答**：课件只给题面、不给解答时，按同一例题模板补出完整解题步骤；自筹数值标 🔶 并用独立路径复核，不留空、不硬凑。
- **笔记分层**：区分「课堂讲义层」（手写、可编辑）与「教材章节层」（脚本产出、改了会被覆盖），并给出目录布局与编号约定（`0X - <主题关键词>`）。
- **防覆盖**：识别脚本产出的笔记，避免手改后被下次重跑覆盖。
- **收尾校验**：图片嵌入与 wikilink 全量校验、孤儿配图清理、MOC 同步、记忆落盘。

## 安装

Skill 是「一个文件夹 + 一份 `SKILL.md`」的通用格式。把本仓库整个文件夹复制进你所用的 AI 助手的 **skills 目录**即可 —— 该目录通常形如 `<助手配置目录>/skills/`：

```bash
git clone https://github.com/XLJFZ/courseware-pdf-to-notes.git
cp -r courseware-pdf-to-notes <助手配置目录>/skills/
```

> 也可以直接把 `SKILL.md` 的内容贴给 AI 当提示词用，不装 Skill 同样能跑。

## 触发方式

对 AI 说这些话即可激活：

- 「我放了课件」
- 「有新的课件了，更新一下」
- 「根据课件改一下笔记」
- 「课件更新了」
- 「按讲义整理一下」

## 工作流概览

```
第 0 步  看清课件覆盖范围 / 现有笔记结构 / 新旧 PDF 是否超集
第 1 步  抽文字（判结构）+ 增量定位（只取新增页）
第 2 步  按页渲染关键页 → 直接读图核对公式与数值
第 3 步  写笔记（讲义层 / 前置基础层，固定骨架 + 例题模板）
第 4 步  更新 MOC
第 5 步  链接校验 + 孤儿配图清理 + 记忆落盘
```

细节见 [`SKILL.md`](./SKILL.md)。

## 依赖

- **Python 3.10+**，以及 [`pymupdf`](https://pypi.org/project/pymupdf/)（PDF 抽文字与按页渲染）
- 笔记落点：**Obsidian** vault（任意路径；Skill 不写死路径）
- 读图核对依赖助手的**多模态看图能力**（能直接读 PNG 的 AI 助手即可）

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install pymupdf   # Linux/macOS: .venv/bin/pip install pymupdf
```

## 仓库结构

```
courseware-pdf-to-notes/
├── SKILL.md          # Skill 本体（元数据 + 完整工作流）
├── README.md         # 本文件
├── LICENSE           # MIT
├── .gitignore
└── .gitattributes
```

## License

[MIT](./LICENSE) © 2026 XLJFZ
