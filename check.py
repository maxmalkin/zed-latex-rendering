"""Run with the installed companion Python; uses real TeX, PDFium, nbconvert and Edge."""
from pathlib import Path
from contextlib import closing
import tempfile
import time
from unittest.mock import patch

import nbformat
import pypdfium2

import zed_latex as tools


def check():
    with tempfile.TemporaryDirectory(prefix="zed-latex-check-") as temporary:
        directory = Path(temporary)
        (directory / "localmath.sty").write_text(r"\ProvidesPackage{localmath}\newcommand{\LocalSet}{\mathbb{R}}")
        (directory / "latex-preamble.tex").write_text(tools.DEFAULT_PREAMBLE + "\\usepackage{localmath}\n")
        fragment = directory / "part.tex"
        fragment.write_text(r"Local package: $\LocalSet$.")
        document = directory / "sample.tex"
        document.write_text(r"\documentclass{article}\usepackage{amsmath,amssymb,localmath}"
                            r"\begin{document}\input{part}\newpage Second page.\end{document}")
        start = time.perf_counter()
        preview = tools.preview(document)
        pdf = preview.parent / "sample.pdf"
        with pypdfium2.PdfDocument(pdf) as parsed:
            assert len(parsed) == 2
        assert len(list(preview.parent.glob("page-*.png"))) == 2
        before = pdf.stat().st_mtime_ns
        with patch.object(tools, "compile_tex", side_effect=AssertionError("Unchanged document recompiled")):
            tools.preview(document)
        assert pdf.stat().st_mtime_ns == before
        print(f"Two-page TeX + raster: {time.perf_counter() - start:.3f}s", flush=True)
        fragment.write_text(r"Changed local package content: $\LocalSet$.")
        tools.preview(document)
        assert pdf.stat().st_mtime_ns != before
        valid_pdf = pdf.read_bytes()
        fragment.write_text(r"\undefinedFailOnPurpose")
        try:
            tools.preview(document)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Invalid TeX succeeded")
        assert pdf.read_bytes() == valid_pdf
        fragment.write_text(r"Local package: $\LocalSet$.")
        markdown = directory / "sample.md"
        original = ("# Package check\n\nInline $\\LocalSet$ and ~~old~~.\n\n"
                    "$$\n\\frac{1}{2} \\in \\LocalSet\n$$\n\n"
                    "```tex\n$not_math$\n```\n\n"
                    "[relative](part.tex)\n\n| A | B |\n|---|---|\n| $x$ | text |\n")
        markdown.write_text(original)
        rendered = tools.preview(markdown)
        text = rendered.read_text(encoding="utf-8")
        assert "../part.tex" in text and "$not_math$" in text and "|" in text
        assert "\\LocalSet" not in text and "![equation]" in text
        with patch.object(tools, "compile_tex", side_effect=AssertionError("Cached math recompiled")):
            tools.preview(markdown)
        assert markdown.read_text() == original
        image = tools.tex(r"\LocalSet", directory=directory)
        assert image.data.startswith(b"\x89PNG")
        notebook = nbformat.v4.new_notebook(cells=[
            nbformat.v4.new_markdown_cell(original),
            nbformat.v4.new_code_cell("raise RuntimeError('Export must not execute code')", execution_count=1,
                outputs=[nbformat.v4.new_output("display_data", data={"text/latex": r"$\LocalSet$", "text/plain": "set"}),
                         nbformat.v4.new_output("stream", name="stdout", text="saved-output-123")]),
        ])
        path = directory / "sample.ipynb"
        nbformat.write(notebook, path)
        saved_source = path.read_bytes()
        html = tools.export_notebook(path, "html")
        html_text = html.read_text(encoding="utf-8")
        assert "data:image/png;base64," in html_text and "saved-output-123" in html_text
        exported_pdf = tools.export_notebook(path, "pdf")
        with pypdfium2.PdfDocument(exported_pdf) as parsed:
            assert len(parsed) > 0
            with closing(parsed[0]) as page, closing(page.get_textpage()) as textpage:
                assert "Package check" in textpage.get_text_range()
        assert path.read_bytes() == saved_source
        generated = nbformat.read(html.with_name("sample.rendered.ipynb"), as_version=4)
        assert generated.cells[0].attachments
        assert "image/png" in generated.cells[1].outputs[0].data
        print("PASS: local packages, document changes, failure retention, cache, Markdown, saved outputs, HTML and PDF.")


if __name__ == "__main__":
    check()
