![ZedTeX](assets/zedtex.png)

| What you write | What you get |
| --- | --- |
| **TeX documents** | A real PDF and page images you can view inside Zed. |
| **Markdown** | A preview copy with beautifully rendered equations. |
| **Jupyter notebooks** | Equation images and HTML/PDF exports with fresh outputs. |

## Install

**Registry publication pending.** The renderer releases are tested on Windows x64, Linux x64, and Intel/Apple Silicon macOS. Once approved, install **ZedTeX** through Zed’s Extensions UI. The renderer downloads automatically; no installer scripts or custom Zed build are needed.

## Use

Open a saved document and choose an action from Zed's **code-actions menu**:

- **LaTeX: build and open preview** — TeX or Markdown. Save to update it.
- **LaTeX: insert Jupyter rendering helper** — run the inserted Python cell, then use `tex(r"x^2")`.
- **Notebook: run all cells and export to HTML/PDF** — open a saved `.ipynb` as JSON. Export runs the notebook’s installed Jupyter kernel and includes fresh outputs.

TeX previews use Zed's image viewer. Markdown previews use generated image links. Your original files stay intact.

## Bring your packages

TeX files use their own preambles. For Markdown and notebooks, put `latex-preamble.tex` beside the source:

```tex
\usepackage{amsmath,amssymb,mathtools}
\usepackage{localmath} % your local .sty file
\boldmath
```

## Built to stay responsive

Unchanged equations are cached. Saves are coalesced, compilation runs in the background, and pages are rasterized one at a time. TeX may still need a full compile when layout or references change.

**A few limits:** page images are not a native PDF viewer; live Jupyter math uses the helper cell; the helper and kernel must run on the same machine. Raw notebook Markdown cells are rendered during export. Export runs cells in a fresh kernel; install your notebook’s dependencies in that kernel.

[Examples](examples) · [Technical details](DEVELOPMENT.md) · [License](LICENSE)
