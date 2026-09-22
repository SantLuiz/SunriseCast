"""Package only the verified distributable; never include local backups or runtime data."""
import hashlib
import json
import platform
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release" / "2.0.0"
BUNDLE = RELEASE / "SunriseCast"
FORBIDDEN = {".env", ".spotify_cache", "podcasts.json", "settings.json", "state.json", "app.log"}


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    executable = BUNDLE / "SunriseCast.exe"
    if not executable.is_file():
        raise RuntimeError("Build ausente")
    for file in BUNDLE.rglob("*"):
        if file.name in FORBIDDEN or (file.is_dir() and file.name in ("data", "logs")):
            raise RuntimeError(f"Arquivo pessoal no pacote: {file.name}")
    report = json.loads((ROOT / "artifacts" / "ui-executable" / "smoke-result.json").read_text())
    if not report["ok"] or report["network_used"] or report["personal_data_loaded"]:
        raise RuntimeError("Smoke test inválido")
    sources = sorted((ROOT / "app").rglob("*.py")) + [ROOT / name for name in (
        "run.py", "SunriseCast.spec", "build_windows.ps1", "update_installation.ps1", "requirements-lock.txt")]
    info = {"version": "2.0.0", "python": platform.python_version(), "platform": platform.platform(),
            "executable_sha256": sha256(executable), "smoke_test": report,
            "source_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p) for p in sources}}
    (RELEASE / "BUILD_INFO.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    documents = ["UPDATE_GUIDE.md", "UI_OVERHAUL_PLAN.md", "VALIDATION.md", "requirements-lock.txt", "update_installation.ps1"]
    for name in documents:
        shutil.copy2(ROOT / name, RELEASE / name)
    archive = ROOT / "release" / "SunriseCast-2.0.0-windows-x64.zip"
    selected = [p for p in BUNDLE.rglob("*") if p.is_file()]
    selected += [RELEASE / name for name in documents + ["BUILD_INFO.json"]]
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=6) as output:
        for file in sorted(selected):
            output.write(file, file.relative_to(RELEASE))
    with ZipFile(archive) as check:
        assert not any(Path(name).name in FORBIDDEN for name in check.namelist())
        assert check.testzip() is None
    checksum = sha256(archive)
    archive.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive.name}\n", encoding="utf-8")
    print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size,
                      "sha256": checksum, "entries": len(selected)}, indent=2))


if __name__ == "__main__":
    main()
