# LaTeX Rendering for Zed

Real TeX packages in Markdown previews and Jupyter output, PDF page images inside **official Zed**, and notebook export to HTML or PDF. No custom Zed build is required.

This repository contains an **installable Zed snippet extension plus a Python companion**. The extension supplies editing shortcuts; the companion does the rendering and exports through Zed tasks. Installing the extension alone does **not** add a PDF viewer or replace Zed's Markdown/Jupyter renderers: the current extension API has no such hooks.

## Windows setup

1. Clone or download this repository.
2. In Zed, run **zed: install dev extension** and select this directory (the one containing `extension.toml`). This installs the snippets without a Rust build. Alternatively, after running the installer, select `%LOCALAPPDATA%\Programs\Zed-LaTeX-Tools\extension`.
3. Install Python 3.11 or later if necessary. Run the following from this directory in PowerShell:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\install-windows.ps1
   ```

4. Install [Tectonic](https://tectonic-typesetting.github.io/) on PATH, or set `ZED_LATEX_TECTONIC` to its executable. On this machine the installer reuses the Tectonic binary from the previous Zed LaTeX installation, copying it into the companion directory so the old build can be removed independently.
5. Run **repl: refresh kernelspecs** and select **Python (Zed LaTeX tools)** when using the supplied Jupyter helper.

The installer creates `%LOCALAPPDATA%\Programs\Zed-LaTeX-Tools` and a separate Python environment, with ready-to-open examples in its `examples` directory. It registers a new kernel and installs `tasks.windows.json` into `%APPDATA%\Zed\tasks.json` only if that file does not already exist. Otherwise, merge the task entries manually; existing task files are preserved. Your editor settings are not changed.

Microsoft Edge, already installed on Windows, is used for notebook PDF export. No additional browser or full TeX distribution is downloaded. Tectonic fetches TeX packages on first use and caches them.

## TeX preview inside Zed

Open a saved `.tex` document and run **task: spawn → LaTeX: preview and watch current TeX or Markdown**.

The task creates `document.tex.zed-output/` beside your document:

| File | Purpose |
| --- | --- |
| `document.pdf` | The real compiled PDF, ready to share or print. |
| `preview.md` | Open in Zed's Markdown preview for the first page and links to every page image. |
| `page-001.png`, `page-002.png`, … | Open these directly in an adjacent Zed pane. Zed's image viewer reloads an open page when its file changes. |

Save the source to rebuild. The watcher also detects changes to TeX inputs, local packages, bibliography files and common image files **under the source directory**. It debounces saves and skips unchanged documents. Compilation runs sequentially; pages are rasterized one at a time. The overview displays one page to avoid filling the GPU cache with a whole document.

This is a page-image preview, not a native PDF viewer: no PDF text selection, SyncTeX, or continuous scrolling through all pages. Use the numbered image links or file tree to change pages. A genuine PDF is always retained separately. Stop the task with **Ctrl+C**.

Tectonic reruns the document when an input changes; it reuses its package/font cache. It is not incremental typesetting of individual paragraphs. For complex projects needing BibTeX/Biber, another TeX engine, or dependencies outside this directory, use a full TeX distribution and `latexmk` instead.

## Markdown and package imports

Place `latex-preamble.tex` beside the Markdown file or notebook:

```tex
\usepackage{amsmath,amssymb,mathtools}
\usepackage{localmath} % localmath.sty in this directory
\boldmath
```

It replaces the default `amsmath,amssymb` and `\boldmath` preamble. TeX documents continue to use their own preambles. Packages supported by Tectonic's XeTeX engine can be used; shell-escape packages are disabled.

For a Markdown source containing `$inline$` math and `$$` display blocks, run the same preview/watch task. Open `notes.md.zed-output/preview.md` with **Ctrl+Shift+V**. It contains ordinary image links that official Zed already understands. **Edit the original `.md`; the generated preview is disposable.** Code spans/fences are not rendered as math. Display `$$` delimiters should be on separate lines. Formatting is normalized in the generated copy.

Equations compile in batches of up to 32. Unchanged equations reuse PNGs from `.zed-latex-cache`; changes to the preamble or local TeX inputs invalidate them. The cache is capped at 64 MiB / 512 entries. Add `.zed-latex-cache/` and `*.zed-output/` to your project's `.gitignore` if desired.

## Jupyter

In a Python cell, type **ztex** to insert:

```python
from zed_latex import tex
tex(r"\frac{a}{b}")
```

Execute it using Zed's Jupyter REPL. The result is a standard PNG MIME output, so Zed can display it and notebook tools can save it. **ztexcell** adds a `# %%` cell separator too. **ztexpreamble** in a LaTeX buffer inserts a starter preamble.

The helper reads `latex-preamble.tex` and local packages from the kernel's working directory. For a notebook in a different directory, pass `tex(r"\LocalSet", directory=r"C:\path\to\notebook")`. To use an existing kernel instead of the supplied one, install this Python package into that kernel's environment with `python -m pip install .` from this repository.

There is no automatic interception of arbitrary live `text/latex` output or raw Markdown notebook cells in official Zed. Use `tex(...)` for live equations; the exporter renders math in saved Markdown cells and `text/latex` outputs. This keeps real package support without editor changes.

## Export notebooks

Save the `.ipynb`, then use **task: spawn**:

- **Notebook: export saved outputs to HTML**
- **Notebook: export saved outputs to PDF**

The resulting files are in `notebook.ipynb.zed-output/`. HTML embeds equation images; PDF is printed from the same HTML. Markdown equations and LaTeX output are compiled with your actual preamble and packages before export, rather than relying on browser MathJax package support. A `notebook.rendered.ipynb` copy is also written with rendered math. The original notebook is left intact.

Exporting saved outputs **does not execute notebook code**. The two explicitly named **run all cells and export** tasks execute code in a fresh kernel first. They are useful for Zed's `# %%` Python scripts, which are read using Jupytext. A `.py` file does not contain the live REPL session's outputs; exporting it without execution includes only its saved code and Markdown cells. For saved outputs, use an `.ipynb` notebook. Native notebook UI availability in official Zed remains dependent on its notebook feature flag; scripts plus the REPL do not require that UI.

Exports are static. Interactive widgets and JavaScript-only plots are not reproduced in PDF. Local Markdown images are embedded, but arbitrary external HTML resources are not guaranteed to work offline.

## Command line

Using the companion environment's Python:

```powershell
$python = "$env:LOCALAPPDATA\Programs\Zed-LaTeX-Tools\.venv\Scripts\python.exe"
& $python -m zed_latex preview .\paper.tex --watch
& $python -m zed_latex preview .\notes.md --watch
& $python -m zed_latex export .\notebook.ipynb --to html
& $python -m zed_latex export .\notebook.ipynb --to pdf
& $python -m zed_latex export .\analysis.py --to pdf --execute
```

Use trusted documents. TeX runs with Tectonic's `--untrusted` mode and a three-minute timeout; rendering real TeX still reads local inputs and may download packages. Notebook execution occurs only when explicitly requested.

## Validation and maintenance

Run `check.py` using the installed companion Python. It exercises real compilation with a local `.sty`, a two-page document, dependency changes, retention of the last valid PDF after a compiler error, cached equations, Markdown, saved notebook outputs, and actual HTML/PDF export. It uses a temporary directory and removes its fixtures afterward.

Measured on the development Windows machine with a warm package cache: the two-page TeX compile plus page rasterization took approximately **0.66 seconds**. This is a small fixture, not a guarantee for large documents. Previews are limited to 200 pages, a 100-MB PDF, and 16 million raster pixels per document page; equation rasters are limited to one million pixels.

Official Zed continues updating normally. Updating this repository and rerunning the installer updates the companion without rebuilding the editor. No Cargo build or GPU code is involved. The companion does not remove Zed's multiplayer features; that customization remains specific to the earlier fork.

## Credits

Built from the lessons of the [Zed LaTeX fork](https://github.com/maxmalkin/zed). Rendering uses Tectonic and PDFium through pypdfium2; notebook export uses Jupyter nbconvert; Markdown parsing uses Mistune; static PDF export uses Playwright with Edge. This is an independent community project, not an official Zed extension.

The companion and extension source are licensed under [GPL-3.0-or-later](LICENSE). Third-party dependencies retain their own licenses.
