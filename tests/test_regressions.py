import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pdfdiff", ROOT / "scripts/pdfdiff.py")
pdfdiff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pdfdiff)


class PdfTests(unittest.TestCase):
    def doc(self, text="hello", color=None):
        doc = pymupdf.open()
        self.addCleanup(doc.close)
        p = doc.new_page()
        if text:
            p.insert_text((40, 40), text)
        if color:
            p.draw_rect((60, 60, 100, 100), fill=color)
        return doc

    def test_identical(self):
        self.assertEqual(pdfdiff.compare_pages(self.doc(), self.doc()), [])

    def test_same_text_changed_drawing(self):
        rows = pdfdiff.compare_pages(self.doc(color=(1, 0, 0)), self.doc(color=(0, 0, 1)))
        self.assertIn("渲染变化", rows[0][1])

    def test_image_only(self):
        rows = pdfdiff.compare_pages(self.doc("", (1, 0, 0)), self.doc("", (0, 0, 1)))
        self.assertIn("视觉核对", rows[0][1])

    def test_identical_blank_still_needs_review(self):
        self.assertIn("视觉核对", pdfdiff.compare_pages(self.doc(""), self.doc(""))[0][1])

    def test_changed_embedded_image_with_same_text(self):
        old, new = self.doc(), self.doc()
        for doc, color in [(old, b"\xff\x00\x00"), (new, b"\x00\x00\xff")]:
            pix = pymupdf.Pixmap(pymupdf.csRGB, 8, 8, color * 64, False)
            doc[0].insert_image((60, 60, 100, 100), pixmap=pix)
        self.assertIn("渲染变化", pdfdiff.compare_pages(old, new)[0][1])

    def test_number_and_sign(self):
        for before, after in [("Force = 100 N", "Force = 101 N"), ("x = +1", "x = -1"), ("10 N", "10 kN")]:
            with self.subTest(after=after):
                self.assertIn("必须复核", pdfdiff.compare_pages(self.doc(before), self.doc(after))[0][1])

    def test_high_similarity_still_reviewed(self):
        text = "a long sentence\n" * 20
        rows = pdfdiff.compare_pages(self.doc(text + "cat"), self.doc(text + "bat"), 0.9)
        self.assertIn("仍需复核", rows[0][1])

    def test_inserted_page_not_silent_prefix(self):
        old, new = self.doc("first"), self.doc("inserted")
        new.insert_pdf(old)
        self.assertTrue(pdfdiff.compare_pages(old, new))

    def test_cli_real_files_and_dump(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            old, new = self.doc(), self.doc()
            new.new_page().insert_text((40, 40), "appended")
            old.save(tmp / "old.pdf")
            new.save(tmp / "new.pdf")
            result = subprocess.run([sys.executable, str(ROOT / "scripts/pdfdiff.py"), str(tmp / "old.pdf"), str(tmp / "new.pdf"), "--dump-text", str(tmp / "dump.txt")], capture_output=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("候选新增页", result.stdout)
            self.assertIn("appended", (tmp / "dump.txt").read_text(encoding="utf-8"))


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = Path(self.tmp.name)

    def write(self, name, text=""):
        p = self.vault / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def run_check(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts/checklinks.py"), "--vault", str(self.vault), *args], capture_output=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    def test_wrong_directory(self):
        self.write("Index.md", "[[missing/Target]]")
        self.write("Target.md")
        self.assertEqual(self.run_check().returncode, 1)

    def test_embedded_note_without_extension(self):
        self.write("folder/Index.md", "![[./Target#Heading]]")
        self.write("folder/Target.md", "# Heading")
        self.assertEqual(self.run_check().returncode, 0)

    def test_embedded_note_wrong_directory(self):
        self.write("Index.md", "![[missing/Target.md]]")
        self.write("Target.md")
        self.assertEqual(self.run_check().returncode, 1)

    def test_non_markdown_input(self):
        self.write("input.txt")
        self.assertNotEqual(self.run_check("--notes", "input.txt").returncode, 0)

    def test_explicit_and_relative_paths(self):
        self.write("folder/Index.md", "[[folder/Target]] [[./Target]] [[../Other]]")
        self.write("folder/Target.md")
        self.write("Other.md")
        self.assertEqual(self.run_check().returncode, 0)

    def test_missing_input_even_if_other_input_valid(self):
        self.write("Index.md")
        self.assertNotEqual(self.run_check("--notes", "Index.md", "--notes", "missing").returncode, 0)

    def test_empty_vault(self):
        self.assertNotEqual(self.run_check().returncode, 0)

    def test_excludes_everything(self):
        self.write("Index.md")
        self.assertNotEqual(self.run_check("--exclude", "Index").returncode, 0)

    def test_trash_not_a_target(self):
        self.write("Index.md", "[[Deleted]]")
        self.write(".trash/Deleted.md")
        self.assertEqual(self.run_check().returncode, 1)

    def test_code_math_and_escaped_alias(self):
        self.write("Index.md", "```python\nx = [[missing]]\n```\n$[[missing]]$\n[[Target\\|alias]]")
        self.write("Target.md")
        self.assertEqual(self.run_check().returncode, 0)

    def test_duplicate_names_warn(self):
        self.write("Index.md", "[[Target]]")
        self.write("a/Target.md")
        self.write("b/Target.md")
        self.assertIn("AMBIGUOUS LINK", self.run_check().stdout)


if __name__ == "__main__":
    unittest.main()
