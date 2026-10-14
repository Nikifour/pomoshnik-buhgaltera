"""Экспорт и импорт настроек компании одним файлом (.pbsettings).

Файл — zip-архив: manifest.json, settings.json и картинки (логотипы, печать).
Нужен, чтобы раздать сотрудникам одинаковый шаблон без общей сетевой папки.
При импорте читаются только известные имена файлов (никакого extractall),
картинки проверяются, а текущие настройки сначала сохраняются в резервную копию.
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from PIL import Image

from core.settings_store import DEFAULTS, IMAGE_KINDS, Settings
from version import __version__

EXTENSION = ".pbsettings"
FORMAT = "pomoshnik-buhgaltera-settings"
FORMAT_VERSION = 1
MAX_FILE_SIZE = 10 * 1024 * 1024
# Настройки конкретного компьютера — их не переносим
LOCAL_KEYS = ("output_dir",)


class TransferError(Exception):
    pass


def export_profile(s: Settings, target: Path, include_stamp: bool) -> Path:
    if target.suffix.lower() != EXTENSION:
        target = target.with_suffix(EXTENSION)
    values = {k: v for k, v in s.values.items() if k not in LOCAL_KEYS}
    manifest = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "app_version": __version__,
        "created": datetime.now().isoformat(timespec="seconds"),
        "company": s["company_name"],
        "images": [],
    }
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("settings.json", json.dumps(values, ensure_ascii=False, indent=2))
        for kind in IMAGE_KINDS:
            if kind == "stamp" and not include_stamp:
                continue
            p = s.image_path(kind)
            if p:
                z.write(p, f"{kind}.png")
                manifest["images"].append(kind)
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return target


def read_profile(path: Path) -> dict:
    """Проверяет файл и возвращает его содержимое (без применения)."""
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise TransferError("Это не файл настроек программы.") from e
    with z:
        names = set(z.namelist())

        def read(name: str) -> bytes:
            info = z.getinfo(name)
            if info.file_size > MAX_FILE_SIZE:
                raise TransferError(f"Слишком большой файл внутри архива: {name}")
            return z.read(name)

        if "manifest.json" not in names or "settings.json" not in names:
            raise TransferError("Это не файл настроек программы.")
        try:
            manifest = json.loads(read("manifest.json"))
            values = json.loads(read("settings.json"))
        except ValueError as e:
            raise TransferError("Файл настроек повреждён.") from e
        if manifest.get("format") != FORMAT:
            raise TransferError("Это не файл настроек программы.")
        if int(manifest.get("format_version", 0)) > FORMAT_VERSION:
            raise TransferError("Файл создан более новой версией программы — сначала обновите программу.")
        if not isinstance(values, dict):
            raise TransferError("Файл настроек повреждён.")

        images: dict[str, bytes] = {}
        for kind in IMAGE_KINDS:
            name = f"{kind}.png"
            if name in names:
                data = read(name)
                try:
                    Image.open(io.BytesIO(data)).verify()
                except Exception as e:  # noqa: BLE001
                    raise TransferError(f"Повреждена картинка в файле настроек: {name}") from e
                images[kind] = data

    clean = {}
    for k, v in values.items():
        if k in DEFAULTS and k not in LOCAL_KEYS and isinstance(v, type(DEFAULTS[k])):
            clean[k] = v
    return {"manifest": manifest, "values": clean, "images": images}


def apply_profile(s: Settings, profile: dict):
    """Применяет прочитанный профиль. Текущие настройки уходят в резервную копию.

    Логотипы заменяются целиком (нет в файле — убираются), печать — только если она есть
    в файле, чтобы импорт без печати не стирал уже настроенную печать.
    """
    s.save(profile["values"])  # save() сам делает резервную копию
    images = profile["images"]
    for kind in IMAGE_KINDS:
        if kind in images:
            s.set_image(kind, io.BytesIO(images[kind]))
        elif kind != "stamp":
            s.set_image(kind, None)
