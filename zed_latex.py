"""TeX outside the editor; ordinary image files and Jupyter MIME inside it."""

import argparse
import base64
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

import mistune
from mistune.renderers.markdown import MarkdownRenderer
import nbformat
import pypdfium2 as pdfium


DEFAULT_PREAMBLE = "\\usepackage{amsmath,amssymb}\n\\boldmath\n"


def write_changed(path, data):
    path = Path(path)
    data = data.encode("utf-8") if isinstance(data, str) else data
    if path.exists() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def compiler():
    configured = os.environ.get("ZED_LATEX_TECTONIC")
    if configured:
        return configured
    found = shutil.which("tectonic")
    if found:
        return found
    if sys.platform == "win32":
        programs = Path(os.environ["LOCALAPPDATA"]) / "Programs"
        for folder in ("Zed-LaTeX-Tools", "Zed-LaTeX"):
            candidate = programs / folder / "tectonic.exe"
            if candidate.is_file():
                return str(candidate)
    raise RuntimeError("Install Tectonic or set ZED_LATEX_TECTONIC to its executable.")


def compile_tex(source, directory, output, *, document=None):
    output.mkdir(parents=True, exist_ok=True)
    args = [compiler(), "--untrusted", "--keep-intermediates", "--outdir", str(output),
            str(document) if document else "-"]
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(
            args, cwd=directory, stdin=subprocess.PIPE if source is not None else subprocess.DEVNULL,
            stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        try:
            # Sources are capped below, so piping stdin cannot fill the log pipe.
            if source is not None:
                process.stdin.write(source.encode("utf-8"))
                process.stdin.close()
            deadline = time.monotonic() + 180
            while process.poll() is None:
                if time.monotonic() > deadline or os.fstat(log.fileno()).st_size > 8 * 1024 * 1024:
                    raise RuntimeError("TeX exceeded its 180-second or 8-MB log limit.")
                time.sleep(0.1)
            if process.returncode:
                log.seek(max(0, os.fstat(log.fileno()).st_size - 8000))
                raise RuntimeError(log.read().decode("utf-8", errors="replace"))
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
    pdf = output / (document.stem + ".pdf" if document else "texput.pdf")
    if pdf.stat().st_size > 100 * 1024 * 1024:
        raise RuntimeError("PDF exceeds 100 MB.")
    return pdf


def page_png(pdf, index, scale, pixel_limit=16_000_000):
    with closing(pdf[index]) as page:
        width, height = page.get_size()
        if width * height * scale * scale > pixel_limit:
            raise RuntimeError(f"Page raster exceeds {pixel_limit} pixels.")
        bitmap = page.render(scale=scale)
        try:
            with bitmap.to_pil() as image:
                output = io.BytesIO()
                image.save(output, format="PNG")
                return output.getvalue(), image.width, image.height
        finally:
            bitmap.close()


def input_stamp(directory):
    # ponytail: watch TeX inputs under this directory; use latexmk for dependencies outside it.
    values = []
    for root, directories, files in os.walk(directory):
        directories[:] = [name for name in directories if not name.startswith(".")
                           and not name.endswith(".zed-output")
                           and name not in ("node_modules", "target", "venv")]
        for name in sorted(files):
            path = Path(root) / name
            if path.suffix.lower() in (".tex", ".sty", ".cls", ".bib", ".png", ".jpg", ".pdf"):
                stat = path.stat()
                values.append((str(path.relative_to(directory)), stat.st_mtime_ns, stat.st_size))
    return sorted(values)


class Renderer:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        preamble = self.directory / "latex-preamble.tex"
        self.preamble = preamble.read_text(encoding="utf-8") if preamble.exists() else DEFAULT_PREAMBLE
        self.images = {}
        self.cache = self.directory / ".zed-latex-cache"
        self.signature = json.dumps(input_stamp(self.directory))

    def render(self, equations):
        from PIL import Image
        missing = []
        cache_paths = {}
        for equation in dict.fromkeys(equations):
            if equation in self.images:
                continue
            key = json.dumps([equation, self.preamble, self.signature, "raster-v1"])
            path = self.cache / (hashlib.sha256(key.encode()).hexdigest() + ".png")
            cache_paths[equation] = path
            if path.exists():
                with Image.open(path) as image:
                    self.images[equation] = (path.read_bytes(), image.width, image.height)
            else:
                missing.append(equation)
        for offset in range(0, len(missing), 32):
            batch = missing[offset:offset + 32]
            source = ("\\documentclass[border=2pt,multi=preview]{standalone}\n"
                      + self.preamble + "\n\\begin{document}\n")
            for text, display in batch:
                style = r"\displaystyle " if display else r"\textstyle "
                source += "\\begin{preview}$" + style + text + "$\\end{preview}\n"
            source += "\\end{document}\n"
            if len(source.encode("utf-8")) > 262144:
                raise ValueError("Math batch exceeds 256 KB.")
            with tempfile.TemporaryDirectory(prefix="zed-math-") as temporary:
                path = compile_tex(source, self.directory, Path(temporary))
                with pdfium.PdfDocument(path) as pdf:
                    if len(pdf) != len(batch):
                        raise ValueError("Each equation must produce exactly one page.")
                    for index, equation in enumerate(batch):
                        self.images[equation] = page_png(pdf, index, 2, pixel_limit=1_000_000)
                        write_changed(cache_paths[equation], self.images[equation][0])
        cached = sorted(self.cache.glob("*.png"), key=lambda path: path.stat().st_mtime, reverse=True)
        size = 0
        for index, path in enumerate(cached):
            size += path.stat().st_size
            if size > 64 * 1024 * 1024 or index >= 512:
                path.unlink()


def markdown_parser():
    return mistune.create_markdown(renderer=None, plugins=["math", "table", "strikethrough", "url"])


def math_tokens(tokens):
    for token in tokens:
        if token["type"] in ("inline_math", "block_math"):
            yield token["raw"], token["type"] == "block_math"
        yield from math_tokens(token.get("children", []))


class ImageMarkdown(MarkdownRenderer):
    def __init__(self, render_image):
        super().__init__()
        self.render_image = render_image

    def inline_math(self, token, state):
        return self.render_image((token["raw"], False))

    def block_math(self, token, state):
        return "\n\n" + self.render_image((token["raw"], True)) + "\n\n"

    def strikethrough(self, token, state):
        return "~~" + self.render_children(token, state) + "~~"


def convert_markdown(source, renderer, render_image, *, rebase=False):
    parser = markdown_parser()
    tokens, state = parser.parse(source)
    renderer.render(math_tokens(tokens))
    if rebase:
        def fix_url(attrs):
            url = attrs.get("url", "")
            if url and not urlsplit(url).scheme and not url.startswith(("/", "#")):
                attrs["url"] = "../" + url
        def fix_tokens(tokens):
            for token in tokens:
                fix_url(token.get("attrs", {}))
                fix_tokens(token.get("children", []))
        fix_tokens(tokens)
        for attrs in state.env["ref_links"].values():
            fix_url(attrs)
    writer = ImageMarkdown(render_image)
    return writer(tokens, state)


def output_directory(source):
    return source.with_name(source.name + ".zed-output")


def preview(source):
    source = Path(source).resolve()
    output = output_directory(source)
    if source.suffix.lower() == ".tex":
        stamp = input_stamp(source.parent)
        state = output / "inputs.json"
        if state.exists() and json.loads(state.read_text()) == [list(value) for value in stamp]:
            print("Unchanged; reusing PDF and pages.", flush=True)
            return output / "preview.md"
        compiled = compile_tex(None, source.parent, output / "build", document=source)
        pdf_path = output / compiled.name
        write_changed(pdf_path, compiled.read_bytes())
        with pdfium.PdfDocument(pdf_path) as pdf:
            if len(pdf) > 200:
                raise ValueError("Preview is limited to 200 pages; the PDF is still available.")
            links = []
            first_page = ""
            for index in range(len(pdf)):
                data, _, _ = page_png(pdf, index, 1.5)
                name = f"page-{index + 1:03}.png"
                write_changed(output / name, data)
                links.append(f"[{index + 1}]({name})")
                if not index:
                    # Markdown caches image URLs; native image tabs watch stable filenames.
                    first_page = "cover-" + hashlib.sha256(data).hexdigest()[:12] + ".png"
                    write_changed(output / first_page, data)
            # One visible page avoids loading an entire document into Zed's GPU image cache.
            text = (f"# {source.name}\n\nPages: " + " · ".join(links)
                    + f"\n\nPDF: [{pdf_path.name}]({pdf_path.name})\n\n"
                    + f"![Page 1]({first_page})\n")
        write_changed(output / "preview.md", text)
        for old in list(output.glob("page-*.png")) + list(output.glob("cover-*.png")):
            if old.name not in text:
                old.unlink()
        write_changed(state, json.dumps(stamp))
    elif source.suffix.lower() == ".md":
        renderer = Renderer(source.parent)
        def image_link(equation):
            data, _, _ = renderer.images[equation]
            name = hashlib.sha256(data).hexdigest()[:20] + ".png"
            write_changed(output / name, data)
            return f"![equation]({name})"
        text = convert_markdown(source.read_text(encoding="utf-8"), renderer, image_link, rebase=True)
        text = f"<!-- Generated from {source.name}; edit the source file. -->\n\n" + text
        write_changed(output / "preview.md", text)
        for old in output.glob("*.png"):
            if old.name not in text:
                old.unlink()
    else:
        raise ValueError("Preview expects a .tex or .md file.")
    print(output / "preview.md", flush=True)
    return output / "preview.md"


def latex_content(text):
    text = text.strip()
    for start, end in (("$$", "$$"), ("$", "$"), (r"\[", r"\]"), (r"\(", r"\)")):
        if text.startswith(start) and text.endswith(end):
            return text[len(start):-len(end)].strip()
    return text


def export_notebook(source, kind, *, execute=False):
    source = Path(source).resolve()
    if source.suffix == ".py":
        import jupytext
        notebook = jupytext.read(source)
        if not execute:
            print("Script export has no saved REPL outputs. Use --execute or export a saved .ipynb.", flush=True)
    elif source.suffix == ".ipynb":
        notebook = nbformat.read(source, as_version=4)
    else:
        raise ValueError("Export expects .ipynb or a Jupytext # %% .py script.")
    if execute:
        from nbconvert.preprocessors import ExecutePreprocessor
        ExecutePreprocessor(timeout=180).preprocess(notebook, {"metadata": {"path": str(source.parent)}})
    renderer = Renderer(source.parent)
    equations = []
    for cell in notebook.cells:
        if cell.cell_type == "markdown":
            tokens, _ = markdown_parser().parse(cell.source)
            equations.extend(math_tokens(tokens))
        for result in cell.get("outputs", []):
            data = result.get("data", {})
            if "text/latex" in data and "image/png" not in data:
                equations.append((latex_content(data["text/latex"]), True))
    renderer.render(equations)
    for cell in notebook.cells:
        if cell.cell_type == "markdown":
            def attachment(equation):
                data, _, _ = renderer.images[equation]
                name = hashlib.sha256(data).hexdigest()[:20] + ".png"
                cell.setdefault("attachments", {})[name] = {"image/png": base64.b64encode(data).decode("ascii")}
                return f"![equation](attachment:{name})"
            cell.source = convert_markdown(cell.source, renderer, attachment)
        for result in cell.get("outputs", []):
            data = result.get("data", {})
            if "text/latex" in data:
                if "image/png" not in data:
                    png, width, height = renderer.images[(latex_content(data["text/latex"]), True)]
                    data["image/png"] = base64.b64encode(png).decode("ascii")
                    result.setdefault("metadata", {})["image/png"] = {"width": width // 2, "height": height // 2}
                # Ensure nbconvert chooses the package-aware raster over a MathJax/HTML fallback.
                for mime in ("text/latex", "text/html", "image/svg+xml"):
                    data.pop(mime, None)
    from nbconvert import HTMLExporter
    exporter = HTMLExporter(embed_images=True, mathjax_url="", require_js_url="")
    html, _ = exporter.from_notebook_node(notebook, resources={"metadata": {"path": str(source.parent)}})
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    sizes = {base64.b64encode(data).decode("ascii"): (width // 2, height // 2)
             for data, width, height in renderer.images.values()}
    for image in soup.find_all("img", alt="equation"):
        encoded = image.get("src", "").partition("base64,")[2]
        if encoded in sizes:
            image["width"], image["height"] = map(str, sizes[encoded])
    html = str(soup)
    output = output_directory(source)
    html_path = output / (source.stem + ".html")
    write_changed(html_path, html)
    write_changed(output / (source.stem + ".rendered.ipynb"), nbformat.writes(notebook))
    if kind == "pdf":
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge" if sys.platform == "win32" else "chromium")
            try:
                page = browser.new_page(java_script_enabled=False)
                page.goto(html_path.as_uri(), wait_until="load")
                page.emulate_media(media="print")
                pdf = page.pdf(format="A4", print_background=True,
                               margin={"top": "12mm", "bottom": "12mm", "left": "12mm", "right": "12mm"})
            finally:
                browser.close()
        result = html_path.with_suffix(".pdf")
        write_changed(result, pdf)
    else:
        result = html_path
    print(result, flush=True)
    return result


def tex(source, *, directory=None, display=True):
    """Use in a Jupyter cell: tex(r'\\frac{1}{2}'). Returns a persisted PNG output."""
    from IPython.display import Image
    renderer = Renderer(directory or Path.cwd())
    equation = (latex_content(source), display)
    renderer.render([equation])
    data, width, height = renderer.images[equation]
    return Image(data=data, width=width // 2, height=height // 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    viewer = commands.add_parser("preview")
    viewer.add_argument("source", type=Path)
    viewer.add_argument("--watch", action="store_true")
    exporter = commands.add_parser("export")
    exporter.add_argument("source", type=Path)
    exporter.add_argument("--to", choices=("html", "pdf"), required=True)
    exporter.add_argument("--execute", action="store_true", help="Explicitly run notebook code before export")
    args = parser.parse_args()
    try:
        if args.command == "export":
            export_notebook(args.source, args.to, execute=args.execute)
        else:
            source = args.source.resolve()
            previous = None
            while True:
                stamp = (source.stat().st_mtime_ns, input_stamp(source.parent))
                if stamp != previous:
                    time.sleep(0.25)
                    if stamp != (source.stat().st_mtime_ns, input_stamp(source.parent)):
                        continue
                    try:
                        preview(source)
                    except Exception as error:
                        if not args.watch:
                            raise
                        print(f"Build failed; last successful preview retained: {error}", file=sys.stderr, flush=True)
                    previous = stamp
                if not args.watch:
                    break
                time.sleep(0.75)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
