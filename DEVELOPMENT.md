# ZedTeX

A language-server extension for official Zed: real TeX packages, page-image previews, Markdown math, and notebook HTML/PDF export.

**Development status:** the renderer has passed Windows end-to-end checks. Automatic extension installation is being implemented and is not yet published in Zed's registry. No manual PowerShell installer or task-file setup is required by the intended distribution.

## Install

Once the registry submission is accepted, install **ZedTeX** from Zed's Extensions UI. The extension downloads its matching native renderer on first use, using Zed's extension API. Python and a full TeX distribution will not need to be installed separately. Real TeX packages are fetched and cached by Tectonic as needed.

The extension adds a supplementary language server for LaTeX, Markdown, Python and notebook JSON. It keeps existing language servers in place. It does not replace Zed's native renderers or add a PDF viewer.

## Preview

For a saved `.tex` or `.md` file, open Zed's code-actions menu and choose **LaTeX: build and open preview**. Generated files are stored beside the source in `<filename>.zed-output`.

- TeX: a real PDF plus numbered PNG pages. The first page opens in Zed's existing image viewer. Split it beside the source; open other page images from the file tree.
- Markdown: a generated `preview.md` with math replaced by normal image links. Open it with Ctrl+Shift+V. Edit the original source file.
- Save the original to rebuild an activated preview. A code action stops rebuilding.

Image previews do not provide PDF text selection, SyncTeX, or native multi-page controls. The real PDF remains available separately. Generated copies are disposable; source documents are preserved.

## Packages

TeX documents use their own preambles. For Markdown and notebook equations, put `latex-preamble.tex` beside the source:

```tex
\usepackage{amsmath,amssymb,mathtools}
\usepackage{localmath}
\boldmath
```

Local `.sty` files resolve from that directory. This replaces the default amsmath/amssymb and boldmath preamble. Tectonic uses XeTeX; external shell commands and packages requiring other engines are unsupported.

## Jupyter and exports

In a Python document, invoke **LaTeX: insert Jupyter rendering helper**, then run the inserted cell with your existing Jupyter kernel. Use `tex(r"x^2")` in subsequent cells. The helper calls the downloaded renderer and returns a standard PNG output; no package installation into your kernel is needed. The kernel must run on the same machine as the rendering server.

For a saved `.ipynb` opened as JSON, use **Notebook: run all cells and export to HTML/PDF**. Markdown equations and `text/latex` outputs are rendered with actual TeX packages before export. All cells run in order in the notebook’s installed Jupyter kernel, then fresh outputs are exported. The source notebook stays unchanged; the executed copy is saved beside the export. Cell failures stop export and preserve the previous successful export. Native notebook cells are not extension render hooks; arbitrary live kernel LaTeX and Markdown cells cannot be intercepted automatically.

Python `# %%` scripts also execute before export. Notebook dependencies must be installed in the selected Jupyter kernel; the renderer does not supply your computation environment. The developer CLI supports `--no-execute` to export saved outputs. HTML embeds rendered equations; PDF is generated from the same static HTML. Interactive widgets are not reproduced.

## Resource use

Math compiles in batches and reuses a bounded disk cache. Unchanged TeX inputs skip compilation; rasterization processes one page at a time. Limits: three-minute compilation, 8-MB compiler log, 100-MB PDF, 200 preview pages, 16 million raster pixels per document page, one million pixels per equation, and 64 MiB / 512 entries in the math cache.

Add `*.zed-output/` and `.zed-latex-cache/` to your project's ignore file if desired. Official Zed updates independently. This extension does not remove multiplayer features from the editor.

## Development

`check.py` exercises the renderer with real local packages, preview updates, caching, error retention, and notebook exports. `cargo build --release --target wasm32-wasip2` builds the Zed extension. Native server bundles are built separately for each supported OS/architecture, then downloaded by the extension; they are not bundled into the extension registry archive.

The source is GPL-3.0-or-later; see [LICENSE](LICENSE). Third-party components retain their licenses. Built from the lessons of the [Zed LaTeX fork](https://github.com/maxmalkin/zed), using Tectonic, pypdfium2, Jupyter nbconvert, Mistune, and Playwright.
