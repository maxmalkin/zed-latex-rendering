"""Check the actual frozen executable, including the LSP wire protocol."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

binary = Path("dist/latex-rendering/latex-rendering" + (".exe" if sys.platform == "win32" else "")).resolve()
examples = Path("examples").resolve()
subprocess.run([binary, "preview", examples / "paper.tex"], check=True, timeout=180)
subprocess.run([binary, "preview", examples / "notes.md"], check=True, timeout=180)
png = subprocess.run([binary, "math", "--directory", examples], input=b"\\LocalSet", capture_output=True, check=True, timeout=180)
assert png.stdout.startswith(b"\x89PNG")
with tempfile.TemporaryDirectory() as temporary:
    path = Path(temporary) / "test.ipynb"
    path.write_text(json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [
        {"id": "example", "cell_type": "markdown", "metadata": {}, "source": "# Bundle check\n\n$x^2$"}
    ]}))
    subprocess.run([binary, "export", path, "--to", "html"], check=True, timeout=180)
process = subprocess.Popen([binary, "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
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
    send({"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": None})
    assert read()["id"] == 3
    send({"jsonrpc": "2.0", "method": "exit", "params": None})
    assert process.wait(timeout=10) == 0
finally:
    if process.poll() is None:
        process.kill()
        process.wait()
print("PASS: frozen renderer, PNG, notebook HTML, LSP initialization and code actions")
