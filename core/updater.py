"""Автообновление из релизов GitHub.

Схема: GitHub Actions на каждый тег vX.Y.Z собирает .exe и выкладывает в релиз
вместе с SHA256SUMS.txt. Программа при запуске спрашивает API о последнем релизе,
скачивает новый .exe, сверяет контрольную сумму и запускает его в режиме
установки: новая версия дожидается закрытия старой, копирует себя на её место
и перезапускается (запущенный .exe нельзя перезаписать, пока он работает).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from version import GITHUB_REPO, __version__

API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ASSET_NAME = "Pomoshnik-Buhgaltera.exe"
SUMS_NAME = "SHA256SUMS.txt"
TIMEOUT = 15


class UpdateError(Exception):
    pass


@dataclass
class Release:
    version: str
    notes: str
    exe_url: str
    sums_url: str | None
    size: int


def parse_version(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v)
    return tuple(int(n) for n in nums[:3]) or (0,)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _get(url: str, accept: str = "application/octet-stream"):
    req = urllib.request.Request(url, headers={
        "Accept": accept,
        "User-Agent": f"Pomoshnik-Buhgaltera/{__version__}",
    })
    return urllib.request.urlopen(req, timeout=TIMEOUT)  # noqa: S310 — только https-адреса GitHub


def check_for_update() -> Release | None:
    """Новый релиз или None, если обновлений нет. Ошибки сети — UpdateError."""
    try:
        with _get(API_URL, "application/vnd.github+json") as r:
            data = json.load(r)
    except Exception as e:  # noqa: BLE001
        raise UpdateError(f"Не удалось проверить обновления: {e}") from e

    latest = data.get("tag_name", "")
    if parse_version(latest) <= parse_version(__version__):
        return None
    assets = {a["name"]: a for a in data.get("assets", [])}
    exe = assets.get(ASSET_NAME)
    if not exe:
        return None
    sums = assets.get(SUMS_NAME)
    return Release(
        version=latest.lstrip("v"),
        notes=(data.get("body") or "").strip(),
        exe_url=exe["browser_download_url"],
        sums_url=sums["browser_download_url"] if sums else None,
        size=exe.get("size", 0),
    )


def download(release: Release, progress: Callable[[float], None] | None = None) -> Path:
    """Скачивает новый .exe рядом с текущим и проверяет SHA-256."""
    target_dir = Path(sys.executable).parent if is_frozen() else Path(tempfile.gettempdir())
    tmp = target_dir / f".{ASSET_NAME}.download"
    h = hashlib.sha256()
    try:
        with _get(release.exe_url) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or release.size or 0)
            done = 0
            while chunk := r.read(256 * 1024):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)
    except Exception as e:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        raise UpdateError(f"Ошибка загрузки: {e}") from e

    if release.sums_url:
        try:
            with _get(release.sums_url) as r:
                sums = r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            tmp.unlink(missing_ok=True)
            raise UpdateError(f"Не удалось получить контрольную сумму: {e}") from e
        expected = next((line.split()[0].lower() for line in sums.splitlines()
                         if line.strip().endswith(ASSET_NAME)), None)
        if expected != h.hexdigest():
            tmp.unlink(missing_ok=True)
            raise UpdateError("Контрольная сумма не совпала — файл повреждён. Обновление отменено.")
    return tmp


def install_and_restart(new_exe: Path):
    """Запускает скачанную версию в режиме установки; текущий процесс должен сразу завершиться."""
    if not is_frozen():
        raise UpdateError("Обновление работает только в собранной программе (.exe).")
    runner = new_exe.with_name("_kp_update.exe")
    runner.unlink(missing_ok=True)
    new_exe.rename(runner)
    subprocess.Popen([str(runner), "--finish-update", sys.executable, str(os.getpid())])  # noqa: S603


def handle_update_args(argv: list[str]) -> bool:
    """Служебные режимы запуска. True — интерфейс не запускать, сразу выйти.

    --finish-update <путь к старому exe> <pid>: копируем себя на место старой версии
        (ждём, пока старый процесс отпустит файл) и запускаем обновлённую программу.
    --cleanup <путь>: обновлённая программа удаляет временный файл установщика.
    """
    if len(argv) >= 3 and argv[1] == "--finish-update":
        target = Path(argv[2])
        for _ in range(120):  # до 60 секунд
            try:
                shutil.copy2(sys.executable, target)
                break
            except OSError:
                time.sleep(0.5)
        else:
            return True  # не удалось — старая версия осталась на месте и рабочая
        subprocess.Popen([str(target), "--cleanup", sys.executable])  # noqa: S603
        return True
    if len(argv) >= 3 and argv[1] == "--cleanup":
        def cleanup(path=Path(argv[2])):
            for _ in range(60):
                try:
                    path.unlink(missing_ok=True)
                    return
                except OSError:
                    time.sleep(0.5)
        threading.Thread(target=cleanup, daemon=True).start()
    return False
