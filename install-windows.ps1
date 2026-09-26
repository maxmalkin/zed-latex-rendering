param([switch]$SkipTasks)
$ErrorActionPreference = 'Stop'
$destination = Join-Path $env:LOCALAPPDATA 'Programs\Zed-LaTeX-Tools'
New-Item -ItemType Directory -Force $destination | Out-Null
Copy-Item "$PSScriptRoot\zed_latex.py","$PSScriptRoot\pyproject.toml" $destination -Force
$extension = Join-Path $destination 'extension'
New-Item -ItemType Directory -Force $extension | Out-Null
Copy-Item "$PSScriptRoot\extension.toml","$PSScriptRoot\README.md","$PSScriptRoot\LICENSE" $extension -Force
Copy-Item "$PSScriptRoot\snippets" $extension -Recurse -Force
if (!(Test-Path "$destination\examples")) {
    Copy-Item "$PSScriptRoot\examples" $destination -Recurse
}
$compiler = Join-Path $env:LOCALAPPDATA 'Programs\Zed-LaTeX\tectonic.exe'
if (!(Test-Path "$destination\tectonic.exe") -and (Test-Path $compiler)) {
    Copy-Item $compiler "$destination\tectonic.exe"
}
if (!(Test-Path "$destination\.venv\Scripts\python.exe")) {
    python -m venv "$destination\.venv"
    if ($LASTEXITCODE) { throw 'Could not create Python environment' }
}
$python = "$destination\.venv\Scripts\python.exe"
& $python -m pip install --disable-pip-version-check --no-cache-dir $destination
if ($LASTEXITCODE) { throw 'Could not install companion tools' }
& $python -m ipykernel install --user --name zed-latex-tools --display-name 'Python (Zed LaTeX tools)'
if ($LASTEXITCODE) { throw 'Could not register Jupyter kernel' }
if (!$SkipTasks) {
    $taskFile = Join-Path $env:APPDATA 'Zed\tasks.json'
    if (Test-Path $taskFile) {
        Write-Output "Existing tasks preserved. Merge tasks.windows.json into $taskFile manually."
    } else {
        New-Item -ItemType Directory -Force (Split-Path $taskFile) | Out-Null
        Copy-Item "$PSScriptRoot\tasks.windows.json" $taskFile
        Write-Output "Installed tasks in $taskFile"
    }
}
Write-Output "Installed in $destination"
Write-Output "In Zed: install dev extension -> $extension"
if (Test-Path "$destination\build") { Remove-Item "$destination\build" -Recurse -Force }
