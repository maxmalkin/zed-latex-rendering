"""Release packaging only; never run by extension users."""
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
from urllib.request import urlopen
import zipfile

target = os.environ["TECTONIC_TARGET"]
url = "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/tectonic-0.17.0-" + target
destination = Path("dist/latex-rendering")
with tempfile.TemporaryDirectory() as temporary:
    archive = Path(temporary) / target
    with urlopen(url, timeout=120) as response, archive.open("wb") as output:
        shutil.copyfileobj(response, output)
    if target.endswith(".zip"):
        with zipfile.ZipFile(archive) as bundle:
            # Only the known compiler executable is extracted from the upstream archive.
            name = next(name for name in bundle.namelist() if name.endswith("tectonic.exe"))
            (destination / "tectonic.exe").write_bytes(bundle.read(name))
    else:
        with tarfile.open(archive) as bundle:
            member = next(member for member in bundle.getmembers() if Path(member.name).name == "tectonic")
            (destination / "tectonic").write_bytes(bundle.extractfile(member).read())
            (destination / "tectonic").chmod(0o755)
shutil.copy("LICENSE", destination / "LICENSE")
shutil.make_archive(str(Path("dist") / ("latex-rendering-" + os.environ["BUNDLE_PLATFORM"])), "zip", destination)
