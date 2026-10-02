"""Индекс бэкапов для веб-интерфейса: без базы данных, прямо из хранилища.

  STORAGE=snapshots          каждая папка <device>/<stamp>/ — отдельный бэкап
  STORAGE=git (с историей)   каждый коммит, затронувший <device>/ — бэкап этого устройства
  STORAGE=git, GIT_HISTORY=false   только текущее состояние, по одному на устройство

Имя устройства — это и имя папки. После переименования старые снимки и
коммиты лежат под прежним именем: они показываются под текущим (псевдонимы из
базы), а читаются по фактической папке (Entry.dir).

Удаление: снимки и «только текущее» удаляются с диска; коммиты git не
удаляются — бэкап скрывается из списка (таблица hidden_backups), в истории git
и в Gitea он остаётся.

Идентификатор бэкапа — строка «вид|…», закодированная в base64url.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config
from .storage import SnapshotStorage

NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_CONTENT = 2 * 1024 * 1024


@dataclass
class Entry:
    id: str
    device: str          # текущее имя устройства
    created: datetime
    type: str
    notes: str
    size: int
    kind: str            # snapshot | git | plain
    ref: str             # stamp | sha | ""
    deletable: bool
    dir: str = ""        # папка на диске / в git на момент бэкапа
    changed: bool | None = None   # git: менялись ли файлы устройства в этом коммите

    def __post_init__(self):
        self.dir = self.dir or self.device

    @property
    def delete_mode(self) -> str:
        return "hide" if self.kind == "git" else "delete"

    @property
    def filename(self) -> str:
        return f"{self.device}_{self.created:%Y-%m-%d_%H%M%S}.rsc"

    def public(self) -> dict:
        return {
            "id": self.id, "device": self.device, "created_at": self.created.isoformat(),
            "type": self.type, "notes": self.notes, "size": self.size,
            "filename": self.filename, "deletable": self.deletable, "delete_mode": self.delete_mode,
            "changed": self.changed,
        }


def _enc(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _dec(token: str) -> str:
    try:
        return base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
    except Exception as exc:  # noqa: BLE001
        raise KeyError("неверный идентификатор") from exc


class Catalog:
    def __init__(self, s: config.Settings, db=None):
        self.s = s
        self.db = db
        self.root = s.backup_dir
        self.tz = ZoneInfo(s.timezone)
        self.encodings = {d.name: d.encoding for d in s.devices}
        current = {d.name for d in s.devices}
        # текущее имя важнее псевдонима: псевдоним применяется, только если такого устройства сейчас нет
        self.aliases = {old: new for old, new in (getattr(s, "aliases", None) or {}).items() if old not in current}

    def display(self, dir_name: str) -> str:
        return self.aliases.get(dir_name, dir_name)

    def _hidden(self) -> set[tuple[str, str]]:
        if self.db is None:
            return set()
        return {(r["ref"], r["dir"]) for r in self.db.query("SELECT ref, dir FROM hidden_backups")}

    # ---------------------------------------------------------------- режим

    @property
    def mode(self) -> str:
        if self.s.storage == "snapshots":
            return "snapshot"
        if (self.root / ".git").exists() and shutil.which("git"):
            return "git"
        return "plain"

    def _dirs(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir()
                      if p.is_dir() and NAME_RE.match(p.name) and not p.name.startswith("."))

    def devices(self) -> list[str]:
        names = {d.name for d in self.s.devices} | {self.display(d) for d in self._dirs()}
        if self.mode == "git":
            names |= {e.device for e in self._list_git()}
        return sorted(names)

    def decode(self, device: str, data: bytes) -> str:
        return data.decode(self.encodings.get(device, "utf-8"), errors="replace")

    # ---------------------------------------------------------------- git

    def _git(self, *args: str, input_: bytes | None = None) -> bytes:
        env = {**os.environ, "GIT_CONFIG_COUNT": "1",
               "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "*"}
        p = subprocess.run(["git", *args], cwd=self.root, env=env, input=input_,
                           capture_output=True, timeout=120)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.decode(errors="replace").strip())
        return p.stdout

    def _list_git(self) -> list[Entry]:
        try:
            raw = self._git("log", "--format=%x1e%H%x1f%aI%x1f%s%x1f%b%x1d", "--name-only")
        except RuntimeError:
            return []                                   # пустой репозиторий
        rows: list[tuple[str, str, datetime, str, str, bool]] = []
        for rec in raw.decode("utf-8", errors="replace").split("\x1e")[1:]:
            head, _, names = rec.partition("\x1d")
            parts = head.split("\x1f", 3)
            if len(parts) < 4:
                continue
            sha, date, subject, body = parts
            trailers = dict(m.groups() for m in re.finditer(r"^([A-Za-z-]+):\s*(.*)$", body, re.M))
            touched = {n.strip().split("/", 1)[0] for n in names.splitlines() if "/" in n}
            devices = touched | {d for d in trailers.get("Devices", "").split(",") if d}
            kind = trailers.get("Type") or ("manual" if subject.startswith("manual") else "scheduled")
            if kind == "rename":
                continue
            created = datetime.fromisoformat(date).astimezone(self.tz)
            for dev in devices:
                if NAME_RE.match(dev):
                    rows.append((sha, dev, created, kind, trailers.get("Notes", ""), dev in touched))
        if not rows:
            return []
        check = "".join(f"{row[0]}:{row[1]}/config.rsc\n" for row in rows).encode()
        sizes = self._git("cat-file", "--batch-check=%(objecttype) %(objectsize)", input_=check)
        out = []
        hidden = self._hidden()
        for row, line in zip(rows, sizes.decode().splitlines()):
            parts = line.split()
            if len(parts) != 2 or parts[0] != "blob":
                continue                                # у коммита нет config.rsc этого устройства
            sha, dev, created, kind, notes, touched = row
            if (sha, dev) in hidden:
                continue
            out.append(Entry(_enc(f"g|{sha}|{dev}"), self.display(dev), created, kind, notes,
                             int(parts[1]), "git", sha, True, dev, touched))
        return out

    # ---------------------------------------------------------------- snapshots / plain

    def _list_snapshots(self) -> list[Entry]:
        out = []
        for dev in self._dirs():
            d = self.root / dev
            if not d.is_dir():
                continue
            for snap in d.iterdir():
                if not (snap.is_dir() and SnapshotStorage.STAMP_RE.match(snap.name)):
                    continue
                cfg = snap / "config.rsc"
                if not cfg.exists():
                    continue
                info = {}
                try:
                    info = json.loads((snap / "info.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    pass
                created = datetime.strptime(snap.name[:17], SnapshotStorage.STAMP).replace(tzinfo=self.tz)
                out.append(Entry(_enc(f"s|{dev}|{snap.name}"), self.display(dev), created,
                                 info.get("type", "scheduled"), info.get("notes", ""),
                                 cfg.stat().st_size, "snapshot", snap.name, True, dev))
        return out

    def _list_plain(self) -> list[Entry]:
        out = []
        for dev in self._dirs():
            cfg = self.root / dev / "config.rsc"
            if cfg.exists():
                created = datetime.fromtimestamp(cfg.stat().st_mtime, self.tz)
                out.append(Entry(_enc(f"p|{dev}"), self.display(dev), created, "current", "",
                                 cfg.stat().st_size, "plain", "", True, dev))
        return out

    # ---------------------------------------------------------------- API

    def list(self) -> list[Entry]:
        entries = {"snapshot": self._list_snapshots, "git": self._list_git,
                   "plain": self._list_plain}[self.mode]()
        entries.sort(key=lambda e: (e.created, e.device), reverse=True)
        return entries

    def get(self, token: str) -> Entry:
        parts = _dec(token).split("|")
        kind = parts[0]
        if kind == "s" and len(parts) == 3 and NAME_RE.match(parts[1]) \
                and SnapshotStorage.STAMP_RE.match(parts[2]):
            snap = self.root / parts[1] / parts[2]
            if (snap / "config.rsc").exists():
                return next(e for e in self._list_snapshots() if e.id == token)
        elif kind == "g" and len(parts) == 3 and SHA_RE.match(parts[1]) and NAME_RE.match(parts[2]):
            for e in self._list_git():
                if e.id == token:
                    return e
        elif kind == "p" and len(parts) == 2 and NAME_RE.match(parts[1]):
            for e in self._list_plain():
                if e.id == token:
                    return e
        raise KeyError("бэкап не найден")

    def files(self, e: Entry) -> list[dict]:
        if e.kind == "git":
            raw = self._git("ls-tree", "-r", "-l", e.ref, "--", f"{e.dir}/").decode(errors="replace")
            out = []
            for line in raw.splitlines():
                meta, _, path = line.partition("\t")
                size = meta.split()[-1]
                out.append({"path": path.split("/", 1)[1], "size": int(size) if size.isdigit() else 0})
            return sorted(out, key=lambda x: x["path"])
        base = self.root / e.dir / (e.ref if e.kind == "snapshot" else "")
        return sorted(({"path": p.relative_to(base).as_posix(), "size": p.stat().st_size}
                       for p in base.rglob("*") if p.is_file()), key=lambda x: x["path"])

    def read(self, e: Entry, rel: str = "config.rsc") -> bytes:
        if rel not in {f["path"] for f in self.files(e)}:
            raise KeyError("файл не найден")
        if e.kind == "git":
            return self._git("show", f"{e.ref}:{e.dir}/{rel}")
        base = self.root / e.dir / (e.ref if e.kind == "snapshot" else "")
        return (base / rel).read_bytes()

    def delete(self, e: Entry, user: str | None = None) -> str:
        """Возвращает 'deleted' или 'hidden'."""
        if e.kind == "git":
            if self.db is None:
                raise PermissionError("этот бэкап нельзя удалить: он часть истории git")
            import time
            with self.db.tx() as c:
                c.execute("INSERT OR IGNORE INTO hidden_backups(ref, dir, hidden_at, user) VALUES(?,?,?,?)",
                          (e.ref, e.dir, time.time(), user))
            return "hidden"
        shutil.rmtree(self.root / e.dir / e.ref if e.kind == "snapshot" else self.root / e.dir)
        return "deleted"
