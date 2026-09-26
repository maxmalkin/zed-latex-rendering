"""Run with the installed companion Python; uses real TeX, PDFium, nbconvert and Edge."""
from pathlib import Path
from contextlib import closing
import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import tomllib
from urllib.parse import quote
from unittest.mock import patch

import nbformat
import pypdfium2
from PIL import Image

import zed_latex as tools


def check():
    repository = Path(__file__).parent
    manifest = tomllib.loads((repository / "extension.toml").read_text())
    for filename in manifest["snippets"]:
        snippets = json.loads((repository / filename).read_text())
        assert all("prefix" in value and "body" in value for value in snippets.values())
    assert manifest["language_servers"]["latex-rendering"]["languages"]
    with tempfile.TemporaryDirectory(prefix="zed-latex-check-") as temporary:
        directory = Path(temporary)
        (directory / "localmath.sty").write_text(r"\ProvidesPackage{localmath}\newcommand{\LocalSet}{\mathbb{R}}")
        (directory / "latex-preamble.tex").write_text(tools.DEFAULT_PREAMBLE + "\\usepackage{localmath}\n")
        with patch.object(tools, "compile_tex", side_effect=AssertionError("Preamble compiled as a document")):
            try:
                tools.preview(directory / "latex-preamble.tex")
            except ValueError as error:
                assert "not a standalone document" in str(error)
            else:
                raise AssertionError("Preamble accepted as a document")
        fragment = directory / "part.tex"
        fragment.write_text(r"Local package: $\LocalSet$.")
        document = directory / "sample.tex"
        document.write_text(r"\documentclass{article}\usepackage{amsmath,amssymb,localmath}"
                            r"\begin{document}\input{part}\newpage Second page.\end{document}")
        start = time.perf_counter()
        preview = tools.preview(document)
        assert not preview.is_relative_to(directory)
        pdf = preview.parent / "sample.pdf"
        with pypdfium2.PdfDocument(pdf) as parsed:
            assert len(parsed) == 2
        assert len(list(preview.parent.glob("page-*.png"))) == 2
        assert "data:image/png;base64," in preview.read_text(), "TeX cover relies on sibling image files"
        before = pdf.stat().st_mtime_ns
        with patch.object(tools, "compile_tex", side_effect=AssertionError("Unchanged document recompiled")):
            tools.preview(document)
        assert pdf.stat().st_mtime_ns == before
        print(f"Two-page TeX + raster: {time.perf_counter() - start:.3f}s", flush=True)
        fragment.write_text(r"Local package: \hspace{5pt}$\LocalSet$.")
        rastered = []
        original_raster = tools.page_png
        def track_raster(pdf, index, *args, **kwargs):
            rastered.append(index)
            return original_raster(pdf, index, *args, **kwargs)
        with patch.object(tools, "page_png", side_effect=track_raster):
            tools.preview(document)
        assert rastered == [0], f"Expected only edited page to rasterize, got {rastered}"
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
        with Image.new("RGB", (4, 4), "red") as image:
            image.save(directory / "local image.png")
        original = ("# Package check\n\nInline $\\LocalSet$ and ~~old~~.\n\n"
                    "$$\n\\frac{1}{2} \\in \\LocalSet\n$$\n\n"
                    "```tex\n$not_math$\n```\n\n"
                    "[relative](part.tex)\n\n![local](local%20image.png)\n\n"
                    "![reference][picture]\n\n[picture]: local%20image.png\n\n"
                    "| A | B |\n|---|---|\n| $x$ | text |\n")
        markdown.write_text(original)
        rendered = tools.preview(markdown)
        text = rendered.read_text(encoding="utf-8")
        relative_link = quote(Path(os.path.relpath(fragment, rendered.parent)).as_posix(), safe="/:")
        assert relative_link in text and "$not_math$" in text and "|" in text
        assert "\\LocalSet" not in text and "![equation]" in text
        tokens, _ = tools.markdown_parser().parse(text)
        def image_urls(tokens):
            for token in tokens:
                if token["type"] == "image":
                    yield token["attrs"]["url"]
                yield from image_urls(token.get("children", []))
        urls = list(image_urls(tokens))
        assert len(urls) == 5 and all(url.startswith("data:image/png;base64,") for url in urls)
        local_url = tools.image_data_url((directory / "local image.png").read_bytes())
        assert urls.count(local_url) == 2 and text.count(local_url) == 1, "Repeated local image was not deduplicated"
        for url in set(urls) - {local_url}:
            with Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1], validate=True))) as image:
                assert image.mode == "RGBA" and image.getchannel("A").getextrema() == (0, 255)
        assert list(rendered.parent.iterdir()) == [rendered], "Preview should not depend on sibling assets"
        assert tools.output_directory(directory / "subfolder" / "sample.md") != rendered.parent
        with patch.object(tools, "compile_tex", side_effect=AssertionError("Cached math recompiled")):
            previous_mtime = rendered.stat().st_mtime_ns
            tools.preview(markdown)
            assert rendered.stat().st_mtime_ns == previous_mtime, "Unchanged preview was rewritten"
        assert markdown.read_text() == original
        markdown.write_text(original.replace("$x$", "$y$"))
        with patch.object(tools, "compile_tex", wraps=tools.compile_tex) as compile_math:
            tools.preview(markdown)
        assert compile_math.call_count == 1
        compiled_math = compile_math.call_args.args[0]
        assert "y$" in compiled_math and r"\LocalSet" not in compiled_math
        print("Changed equation: 1 compiled; other equations reused.", flush=True)
        before_change = rendered.read_text(encoding="utf-8")
        (directory / "localmath.sty").write_text(r"\ProvidesPackage{localmath}\newcommand{\LocalSet}{\mathbb{C}}")
        tools.preview(markdown)
        assert rendered.read_text(encoding="utf-8") != before_change
        image = tools.tex(r"\LocalSet", directory=directory)
        assert image.data.startswith(b"\x89PNG")
        notebook = nbformat.v4.new_notebook(cells=[
            nbformat.v4.new_markdown_cell(original),
            nbformat.v4.new_code_cell("from IPython.display import display, Latex\nprint('fresh-output-123')\ndisplay(Latex(r'$\\LocalSet$'))", execution_count=1,
                outputs=[nbformat.v4.new_output("display_data", data={"text/latex": r"$\LocalSet$", "text/plain": "set"}),
                         nbformat.v4.new_output("stream", name="stdout", text="saved-output-123")]),
        ])
        path = directory / "sample.ipynb"
        nbformat.write(notebook, path)
        saved_source = path.read_bytes()
        html = tools.export_notebook(path, "html")
        html_text = html.read_text(encoding="utf-8")
        assert "data:image/png;base64," in html_text and "fresh-output-123" in html_text and "saved-output-123" not in html_text
        exported_pdf = tools.export_notebook(path, "pdf")
        with pypdfium2.PdfDocument(exported_pdf) as parsed:
            assert len(parsed) > 0
            with closing(parsed[0]) as page, closing(page.get_textpage()) as textpage:
                assert "Package check" in textpage.get_text_range()
        assert path.read_bytes() == saved_source
        previous_html, previous_pdf = html.read_bytes(), exported_pdf.read_bytes()
        notebook.cells[1].source = "raise RuntimeError('intentional execution failure')"
        nbformat.write(notebook, path)
        try:
            tools.export_notebook(path, "html")
        except Exception as error:
            assert "intentional execution failure" in str(error)
        else:
            raise AssertionError("Failed notebook execution produced an export")
        assert html.read_bytes() == previous_html and exported_pdf.read_bytes() == previous_pdf
        tools.export_notebook(path, "html", execute=False)
        assert "saved-output-123" in html.read_text(encoding="utf-8")
        generated = nbformat.read(html.with_name("sample.rendered.ipynb"), as_version=4)
        assert generated.cells[0].attachments
        assert "image/png" in generated.cells[1].outputs[0].data
        script = directory / "script.py"
        script.write_text("# %% [markdown]\n# Script example: $\\LocalSet$\n\n# %%\nprint('executed-output-456')\n")
        executed_html = tools.export_notebook(script, "html", execute=True)
        assert "executed-output-456" in executed_html.read_text(encoding="utf-8")
        # Run the actual CLI watcher, then modify an included TeX source.
        watched_pdf = tools.output_directory(document) / "sample.pdf"
        watcher = subprocess.Popen([sys.executable, str(repository / "zed_latex.py"), "preview", str(document), "--watch"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(2)
            previous = watched_pdf.stat().st_mtime_ns
            fragment.write_text(r"Watched update $\LocalSet$.")
            deadline = time.monotonic() + 20
            while watched_pdf.stat().st_mtime_ns == previous and time.monotonic() < deadline:
                assert watcher.poll() is None
                time.sleep(0.25)
            assert watched_pdf.stat().st_mtime_ns != previous
        finally:
            watcher.terminate()
            watcher.wait(timeout=10)
        assert {path.name for path in directory.iterdir()} == {
            "localmath.sty", "latex-preamble.tex", "part.tex", "sample.tex", "sample.md", "sample.ipynb", "script.py", "local image.png"
        }, "Renderer left intermediate files beside the source"
        print("PASS: local packages, document changes, failure retention, cache, Markdown, fresh notebook outputs, failure retention, HTML and PDF.")


if __name__ == "__main__":
    check()
