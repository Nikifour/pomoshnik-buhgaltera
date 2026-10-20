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

from core.layout import IMAGE_NAME_RE, normalize, referenced_images
from core.settings_store import DEFAULTS, IMAGE_KINDS, Settings
from version import __version__

EXTENSION = ".pbsettings"
# Подпись в начале файла: без неё файл начинается как обычный zip, и Windows, почта и мессенджеры
# показывают его как «папку» с картинками или сами переименовывают в .zip / распаковывают.
# zipfile читает архив и с таким «префиксом» — он ищет оглавление в конце файла.
MAGIC = b"POMOSHNIK-BUHGALTERA-SETTINGS\r\n"
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
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("settings.json", json.dumps(values, ensure_ascii=False, indent=2))
        for kind in IMAGE_KINDS:
            if kind == "stamp" and not include_stamp:
                continue
            p = s.image_path(kind)
            if p:
                z.write(p, f"{kind}.png")
                manifest["images"].append(kind)
        # картинки своих блоков конструктора
        for name in sorted(referenced_images(normalize(values.get("layout"), values))):
            f = s.blocks_dir / name
            if f.exists():
                z.write(f, f"blocks/{name}")
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    target.write_bytes(MAGIC + buf.getvalue())
    return target


class _ZipSource:
    def __init__(self, path: Path):
        try:
            self.z = zipfile.ZipFile(path)  # работает и с подписью в начале файла
        except (zipfile.BadZipFile, OSError) as e:
            raise TransferError("Это не файл настроек программы.") from e
        self.names = set(self.z.namelist())

    def read(self, name: str) -> bytes:
        if self.z.getinfo(name).file_size > MAX_FILE_SIZE:
            raise TransferError(f"Слишком большой файл внутри архива: {name}")
        return self.z.read(name)

    def close(self):
        self.z.close()


class _FolderSource:
    """Файл настроек уже распаковали в папку (почта, мессенджер, архиватор) — читаем из неё
    только известные имена, без перехода в другие папки."""

    def __init__(self, folder: Path):
        self.folder = folder
        known = ["manifest.json", "settings.json"] + [f"{k}.png" for k in IMAGE_KINDS]
        self.names = {n for n in known if (folder / n).is_file()}
        blocks = folder / "blocks"
        if blocks.is_dir():
            self.names |= {f"blocks/{f.name}" for f in blocks.iterdir()
                           if f.is_file() and IMAGE_NAME_RE.match(f.name)}

    def read(self, name: str) -> bytes:
        p = self.folder / name
        if p.stat().st_size > MAX_FILE_SIZE:
            raise TransferError(f"Слишком большой файл: {name}")
        return p.read_bytes()

    def close(self):
        pass


def _open_source(path: Path):
    path = Path(path)
    if path.is_dir():
        return _FolderSource(path)
    if path.name.lower() in ("settings.json", "manifest.json"):  # выбрали файл внутри распакованной папки
        return _FolderSource(path.parent)
    return _ZipSource(path)


def read_profile(path: Path) -> dict:
    """Проверяет файл (или распакованную папку) и возвращает содержимое (без применения)."""
    src = _open_source(path)
    try:
        names, read = src.names, src.read

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

        blocks: dict[str, bytes] = {}
        for name in names:
            if name.startswith("blocks/") and IMAGE_NAME_RE.match(name[len("blocks/"):]):
                data = read(name)
                try:
                    Image.open(io.BytesIO(data)).verify()
                except Exception as e:  # noqa: BLE001
                    raise TransferError(f"Повреждена картинка в файле настроек: {name}") from e
                blocks[name[len("blocks/"):]] = data
    finally:
        src.close()

    clean = {}
    for k, v in values.items():
        if k in DEFAULTS and k not in LOCAL_KEYS and isinstance(v, type(DEFAULTS[k])):
            clean[k] = v
    if "layout" in clean:
        clean["layout"] = normalize(clean["layout"], clean)
    return {"manifest": manifest, "values": clean, "images": images, "blocks": blocks}


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
    if profile.get("blocks"):
        s.blocks_dir.mkdir(exist_ok=True)
        for name, data in profile["blocks"].items():
            Image.open(io.BytesIO(data)).convert("RGBA").save(s.blocks_dir / name)
