import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "update_installation.ps1"


@pytest.mark.skipif(not shutil.which("powershell"), reason="Windows updater")
def test_updater_prepare_apply_rollback_preserves_personal_data(tmp_path):
    install = tmp_path / "installation"
    bundle = tmp_path / "bundle"
    backups = tmp_path / "backups"
    install.mkdir()
    bundle.mkdir()
    for root, version in ((install, "old"), (bundle, "new")):
        (root / "SunriseCast.exe").write_text(version)
        (root / "_internal").mkdir()
        (root / "_internal" / f"{version}.dll").write_text(version)
    personal = {".env": "FAKE=demo", ".spotify_cache": "fake-token", "iniciar_oculto.vbs": "fake-startup",
                "data/state.json": '{"processed_episode_ids": ["kept"]}', "data/podcasts.json": "[]",
                "data/settings.json": "{}"}
    personal["logs/app.log"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ",000 [WARNING] Retry will occur after: 86000 s\n"
    for name, value in personal.items():
        file = install / name
        file.parent.mkdir(exist_ok=True)
        file.write_text(value)

    def run(mode, *extra):
        process = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
                                  "-Mode", mode, "-InstallPath", str(install), "-BundlePath", str(bundle),
                                  "-BackupRoot", str(backups), *extra], capture_output=True, timeout=30)
        assert process.returncode == 0, process.stdout.decode(errors="replace") + process.stderr.decode(errors="replace")

    run("Prepare")
    assert (install / "SunriseCast.exe").read_text() == "old"
    original_backup = next(backups.iterdir())
    run("Apply")
    assert (install / "SunriseCast.exe").read_text() == "new"
    assert not (install / "_internal" / "old.dll").exists()
    for name, value in personal.items():
        assert (install / name).read_text() == value
    wait = json.loads((install / "data/legacy_spotify_wait.json").read_text(encoding="utf-8-sig"))
    assert wait["seconds"] == 86000
    run("Rollback", "-BackupPath", str(original_backup))
    assert (install / "SunriseCast.exe").read_text() == "old"
    assert not (install / "_internal" / "new.dll").exists()
    for name, value in personal.items():
        assert (install / name).read_text() == value
