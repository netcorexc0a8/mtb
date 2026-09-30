import subprocess
from pathlib import Path

from ._version import __version__ as _built_version


def _detect_version() -> str:
    """Версия релиза.

    Сборка CI (бинарник, Docker-образ) записывает версию из git-тега в _version.py.
    scripts/release.sh делает то же при выпуске, так что исходники с тега тоже
    знают свою версию. В git-клоне между релизами берём `git describe`:
    например, 0.1.1-3-gabc1234 — три коммита после v0.1.1.
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
