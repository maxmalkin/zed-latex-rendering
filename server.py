"""Standard LSP code actions; rendering never runs on Zed's UI thread."""
import asyncio
from pathlib import Path
import sys

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer
from pygls.uris import to_fs_path

import zed_latex as renderer


server = LanguageServer("ZedTeX", "0.1.2")
active_previews = set()
render_lock = asyncio.Lock()
pending_saves = {}


def source_path(uri):
    path = to_fs_path(uri)
    if not path or not uri.startswith("file:"):
        raise ValueError("Save the document to a local file first.")
    source = Path(path).resolve()
    if source.is_relative_to(renderer.cache_directory()) or any(part.endswith(".zed-output") for part in source.parts):
        raise ValueError("Open the original source, not a generated preview.")
    return source


@server.feature(lsp.TEXT_DOCUMENT_CODE_ACTION, lsp.CodeActionOptions(code_action_kinds=[lsp.CodeActionKind.Source, lsp.CodeActionKind.RefactorRewrite]))
def code_actions(params):
    try:
        source = source_path(params.text_document.uri)
    except ValueError:
        return []
    if source.name.lower() == "latex-preamble.tex":
        return []
    actions = []
    if source.suffix.lower() in (".tex", ".md"):
        actions.append(("LaTeX: build and open preview", "latex.preview"))
        if source in active_previews:
            actions.append(("LaTeX: stop rebuilding preview on save", "latex.stop"))
    if source.suffix.lower() in (".ipynb", ".py"):
        actions.extend([(f"Notebook: run all cells and export to {kind.upper()}", f"latex.export.{kind}")
                        for kind in ("html", "pdf")])
    result = [lsp.CodeAction(title=title, kind=lsp.CodeActionKind.Source,
                            command=lsp.Command(title=title, command=command, arguments=[params.text_document.uri]))
              for title, command in actions]
    if source.suffix.lower() == ".py":
        executable = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(renderer.__file__).resolve())]
        # The user explicitly invokes this edit. Existing kernels need only their standard IPython.
        helper = ("# %% LaTeX rendering helper (run this cell once)\n"
                  "import subprocess\nfrom IPython.display import Image\n\n"
                  "def tex(source):\n"
                  f"    command = {executable + ['math', '--directory', str(source.parent)]!r}\n"
                  "    result = subprocess.run(command, input=source.encode('utf-8'), capture_output=True, timeout=180)\n"
                  "    if result.returncode:\n"
                  "        raise RuntimeError(result.stderr.decode('utf-8', errors='replace'))\n"
                  "    return Image(data=result.stdout, retina=True)\n\n# %%\n")
        beginning = lsp.Position(line=0, character=0)
        result.append(lsp.CodeAction(
            title="LaTeX: insert Jupyter rendering helper", kind=lsp.CodeActionKind.RefactorRewrite,
            edit=lsp.WorkspaceEdit(changes={params.text_document.uri: [lsp.TextEdit(lsp.Range(beginning, beginning), helper)]}),
        ))
    return result


async def build(uri, kind=None, show=True):
    try:
        source = source_path(uri)
        async with render_lock:
            if kind:
                result = await asyncio.to_thread(renderer.export_notebook, source, kind)
            else:
                result = await asyncio.to_thread(renderer.preview, source)
                if show:
                    active_previews.add(source)
                if source.suffix.lower() == ".tex":
                    result = result.parent / "page-001.png"
        if show:
            await server.window_show_document_async(lsp.ShowDocumentParams(uri=result.as_uri(), take_focus=True, external=bool(kind)))
        if show:
            server.window_show_message(lsp.ShowMessageParams(type=lsp.MessageType.Info, message=f"Rendered {result.name}"))
    except Exception as error:
        server.window_show_message(lsp.ShowMessageParams(type=lsp.MessageType.Error, message=str(error)))


@server.command("latex.preview")
async def preview(uri: str):
    await build(uri)


@server.command("latex.stop")
def stop(uri: str):
    source = source_path(uri)
    active_previews.discard(source)
    pending_saves.pop(source, None)


async def rebuild_after_saves(source):
    try:
        while source in pending_saves:
            version = pending_saves[source]
            await asyncio.sleep(0.3)
            if version != pending_saves.get(source):
                continue
            await build(source.as_uri(), show=False)
            if version == pending_saves.get(source):
                break
    finally:
        pending_saves.pop(source, None)


@server.command("latex.export.html")
async def export_html(uri: str):
    await build(uri, "html")


@server.command("latex.export.pdf")
async def export_pdf(uri: str):
    await build(uri, "pdf")


@server.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
async def saved(params):
    try:
        changed = source_path(params.text_document.uri)
    except ValueError:
        return
    for source in list(active_previews):
        if changed == source or (changed.suffix.lower() in (".tex", ".sty", ".cls", ".bib")
                                 and changed.is_relative_to(source.parent)):
            running = source in pending_saves
            pending_saves[source] = pending_saves.get(source, 0) + 1
            if not running:
                asyncio.create_task(rebuild_after_saves(source))
