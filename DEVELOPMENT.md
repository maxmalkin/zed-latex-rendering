# ZedTeX

A language-server extension for official Zed: real TeX packages, page-image previews, Markdown math, and notebook HTML/PDF export.

**Development status:** native renderer bundles pass actual TeX, Markdown, executed notebook HTML/PDF, and LSP checks on Windows x64, Linux x64, and Intel/Apple Silicon macOS. Releases download automatically through the extension API. Registry publication is pending.

## Install

Once the registry submission is accepted, install **ZedTeX** from Zed's Extensions UI. The extension downloads its matching native renderer on first use, using Zed's extension API. Python and a full TeX distribution will not need to be installed separately. Real TeX packages are fetched and cached by Tectonic as needed.

The extension adds a supplementary language server for LaTeX, Markdown, Python and notebook JSON. `.tex` recognition comes from the existing **LaTeX** language extension, also installed through Zed’s Extensions UI. It keeps existing language servers in place. It does not replace Zed's native renderers or add a PDF viewer.

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

Math compiles only missing equations in batches and reuses a bounded disk cache. Unchanged TeX inputs skip compilation. After a TeX rebuild, unchanged page objects reuse their PNGs; shared font or resource changes conservatively invalidate affected pages. Rasterization processes one page at a time. Limits: three-minute compilation, 8-MB compiler log, 100-MB PDF, 200 preview pages, 16 million raster pixels per document page, one million pixels per equation, and 64 MiB / 512 entries in the math cache.

On one Windows run, cached standalone requests took 0.28–0.54 seconds including process startup, with 41–44 MiB peak process-tree RSS; the idle LSP used 63 MiB. These are small-document measurements, not limits or guarantees.

Add `*.zed-output/` and `.zed-latex-cache/` to your project's ignore file if desired. Official Zed updates independently. This extension does not remove multiplayer features from the editor.

## Development

To use **Install Dev Extension**, install [Rust through rustup](https://rust-lang.org/tools/install/) on the same OS as Zed. Windows-native Zed needs Windows Rust; a WSL Rust installation does not supply its compiler. Restart Zed after installing Rust so it sees the updated PATH. Zed installs the `wasm32-wasip2` target automatically. Windows builds also need the Visual C++ build tools required by Rust.

Then select the local clone from Zed’s **Install Dev Extension** dialog. If installation fails, use **zed: open log** to see the underlying compiler error. Registry installations download prebuilt extension code and do not require Rust.

`check.py` exercises the renderer with real local packages, preview updates, caching, error retention, and notebook exports. `cargo build --release --target wasm32-wasip2` builds the Zed extension. Native server bundles are built separately for each supported OS/architecture, then downloaded by the extension; they are not bundled into the extension registry archive.

The source is GPL-3.0-or-later; see [LICENSE](LICENSE). Third-party components retain their licenses. Built from the lessons of the [Zed LaTeX fork](https://github.com/maxmalkin/zed), using Tectonic, pypdfium2, Jupyter nbconvert, Mistune, and Playwright.
