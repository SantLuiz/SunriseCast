import os
import sys
from pathlib import Path

_DLL_HANDLES = []


def _prepare_frozen_dll_paths() -> None:
    if not getattr(sys, "frozen", False):
        return
    internal_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    for relative in ("PySide6", "shiboken6"):
        dll_dir = internal_dir / relative
        if dll_dir.exists() and hasattr(os, "add_dll_directory"):
            _DLL_HANDLES.append(os.add_dll_directory(str(dll_dir)))


def main() -> None:
    _prepare_frozen_dll_paths()
    if "--smoke-test" in sys.argv:
        from app.demo import smoke_test
        destination = Path(sys.argv[sys.argv.index("--smoke-test") + 1]).resolve()
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        smoke_test(destination)
        return
    # Personal data always lives beside the executable, regardless of the shortcut's cwd.
    if getattr(sys, "frozen", False):
        os.chdir(Path(sys.executable).resolve().parent)
    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app.config.logging_config import setup_logging
    qt_app = QApplication.instance() or QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    lock = QLockFile(str(Path(".sunrisecast.lock").resolve()))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None, "SunriseCast", "O SunriseCast já está aberto nesta instalação. Use o ícone na bandeja.")
        return
    try:
        setup_logging()
        from app.bootstrap import build_application
        application = build_application()
        application.run()
    except Exception as exc:
        QMessageBox.critical(None, "SunriseCast", f"Não foi possível iniciar: {exc}")
    finally:
        lock.unlock()


if __name__ == "__main__":
    main()
