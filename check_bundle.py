"""Check the actual frozen executable, including the LSP wire protocol."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Timer

binary = Path("dist/latex-rendering/latex-rendering" + (".exe" if sys.platform == "win32" else "")).resolve()
examples = Path("examples").resolve()
subprocess.run([binary, "preview", examples / "paper.tex"], check=True, timeout=180)
subprocess.run([binary, "preview", examples / "notes.md"], check=True, timeout=180)
png = subprocess.run([binary, "math", "--directory", examples], input=b"\\LocalSet", capture_output=True, check=True, timeout=180)
assert png.stdout.startswith(b"\x89PNG")
with tempfile.TemporaryDirectory() as temporary:
    path = Path(temporary) / "test.ipynb"
    path.write_text(json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {"kernelspec": {"name": "zedtex-test", "display_name": "ZedTeX test", "language": "python"}}, "cells": [
        {"id": "example", "cell_type": "markdown", "metadata": {}, "source": "# Bundle check\n\n$x^2$"},
        {"id": "code", "cell_type": "code", "metadata": {}, "source": "print('fresh-bundle-output')", "execution_count": None, "outputs": []}
    ]}))
    original = path.read_bytes()
    for kind in ("html", "pdf"):
        subprocess.run([binary, "export", path, "--to", kind], check=True, timeout=360)
    output = path.with_name(path.name + ".zed-output")
    assert "fresh-bundle-output" in (output / "test.html").read_text(encoding="utf-8")
    assert (output / "test.pdf").read_bytes().startswith(b"%PDF")
    assert path.read_bytes() == original
process = subprocess.Popen([binary, "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
deadline = Timer(120, process.kill)
deadline.start()
def send(message):
    data = json.dumps(message).encode()
    process.stdin.write(f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
    process.stdin.flush()
def read():
    headers = {}
    while (line := process.stdout.readline().strip()):
        key, value = line.split(b":", 1)
        headers[key.lower()] = value.strip()
    assert b"content-length" in headers, "LSP server exited or wrote non-protocol output"
    return json.loads(process.stdout.read(int(headers[b"content-length"])))
try:
    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"processId": None, "rootUri": examples.as_uri(), "capabilities": {}}})
    response = read()
    assert response["result"]["capabilities"]["codeActionProvider"]
    send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
    send({"jsonrpc": "2.0", "id": 2, "method": "textDocument/codeAction", "params": {"textDocument": {"uri": (examples / "paper.tex").as_uri()}, "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}, "context": {"diagnostics": []}}})
    response = read()
    assert any(action["command"]["command"] == "latex.preview" for action in response["result"])
    send({"jsonrpc": "2.0", "id": 4, "method": "workspace/executeCommand", "params": {"command": "latex.preview", "arguments": [(examples / "paper.tex").as_uri()]}})
    opened = False
    while True:
        response = read()
        if response.get("method") == "window/showDocument":
            assert response["params"]["uri"].endswith("page-001.png")
            opened = True
            send({"jsonrpc": "2.0", "id": response["id"], "result": {"success": True}})
        elif response.get("id") == 4:
            assert "error" not in response and opened, response
            break
        elif response.get("method") == "window/showMessage":
            assert response["params"]["type"] != 1, response
    send({"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": None})
    response = read()
    while "id" not in response:
        response = read()
    assert response["id"] == 3
    send({"jsonrpc": "2.0", "method": "exit", "params": None})
    assert process.wait(timeout=10) == 0
finally:
    deadline.cancel()
    if process.poll() is None:
        process.kill()
        process.wait()
print("PASS: frozen renderer, PNG, executed notebook HTML/PDF, LSP preview command and image opening")
