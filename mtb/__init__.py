import subprocess
from pathlib import Path

from ._version import __version__ as _built_version


def _detect_version() -> str:
    """Версия релиза — это git-тег.

    CI при сборке бинарника и Docker-образа записывает версию из тега в
    _version.py (в репозитории там 0.0.0-dev). При запуске из git-клона
    берём `git describe`: 0.2.0 на теге, 0.2.0-3-gabc1234 — три коммита после.
    """
    root = Path(__file__).resolve().parent.parent
    if (root / ".git").exists():
        try:
            out = subprocess.run(["git", "-C", str(root), "describe", "--tags", "--dirty", "--match", "v*"],
                                 capture_output=True, text=True, timeout=5)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip().lstrip("v")
        except (OSError, subprocess.SubprocessError):
            pass
    return _built_version


__version__ = _detect_version()

__all__ = ["__version__"]
