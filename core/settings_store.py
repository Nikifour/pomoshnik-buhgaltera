"""Хранение данных компании (редактируемая часть шаблона КП).

Макет КП зашит в программу (kp_builder.py), а здесь лежат только поля,
которые пользователь может менять: контакты, тексты, логотипы, печать.
Всё это живёт в папке data рядом с программой и в репозиторий не попадает.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path

IMAGE_KINDS = ("logo", "logo2", "stamp")
DATA_FILES = ("settings.json",) + tuple(f"{k}.png" for k in IMAGE_KINDS)

APP_NAME = "Помощник Бухгалтера"
MAX_BACKUPS = 10

# В коде нет данных конкретной компании: всё, что относится к компании
# (контакты, реквизиты, тексты, логотипы, печать), хранится только в папке data
# у пользователя и в репозиторий не попадает.
DEFAULT_ACCENT = "#1F4E79"

DEFAULTS = {
    "company_name": "",
    "company_full_name": "",
    "address": "",
    "phone": "",
    "email": "",
    "website": "",
    "manager_name": "",
    "manager_position": "Директор",
    "manager_phone": "",
    "greeting": (
        "Уважаемые коллеги!\n"
        "Компания {КОМПАНИЯ} благодарит Вас за интерес к нашей продукции "
        "и предлагает ознакомиться с предложением по следующим позициям:"
    ),
    "conditions": (
        "Цены указаны в тенге с учётом НДС\n"
        "Предложение не является счётом на оплату — для оплаты запросите счёт у менеджера\n"
        "Оплата: 100% предоплата по выставленному счёту\n"
        "Наличие товара и цены уточняйте у менеджера при запросе счёта"
    ),
    "footer": "",
    "accent_color": DEFAULT_ACCENT,
    "show_stamp": True,
    "validity_days": 10,
    # что переносить из счёта на оплату
    "fill_number": True,         # № КП = № счёта (иначе — свой счётчик)
    "fill_date": False,          # дата КП = дата счёта (иначе — сегодня)
    "fill_buyer": True,          # «Кому» — покупатель из счёта
    "fill_buyer_details": True,  # БИН и адрес покупателя
    "show_vat": True,            # строки «Итого» и «В т.ч. НДС»
    "show_amount_words": True,   # «Всего наименований…» и сумма прописью
    "output_dir": str(Path.home() / "Documents" / "Коммерческие предложения"),
    "also_pdf": True,
    "editor_password_hash": "",
}


def resource_path(rel: str) -> Path:
    """Файлы, зашитые в .exe (PyInstaller распаковывает их в _MEIPASS)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / rel


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Папка «data» рядом с программой (удобно положить на общий сетевой диск),
    а если туда нельзя писать — %APPDATA%\\Помощник Бухгалтера."""
    candidate = _app_dir() / "data"
    try:
        candidate.mkdir(exist_ok=True)
        probe = candidate / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        return candidate
    except OSError:
        fallback = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def hash_password(pw: str) -> str:
    return hashlib.sha256(("kp-salt:" + pw).encode("utf-8")).hexdigest()


class Settings:
    def __init__(self):
        self.dir = data_dir()
        self.file = self.dir / "settings.json"
        self.state_file = self.dir / "state.json"
        self.backup_dir = self.dir / "backups"
        self.values = copy.deepcopy(DEFAULTS)
        self.load()

    # --- картинки -----------------------------------------------------------
    def image_path(self, kind: str) -> Path | None:
        """kind: 'logo' | 'logo2' | 'stamp'. Картинки есть только в папке data."""
        own = self.dir / f"{kind}.png"
        return own if own.exists() else None

    def images(self) -> dict[str, Path | None]:
        return {k: self.image_path(k) for k in IMAGE_KINDS}

    def set_image(self, kind: str, src: str | Path | None):
        """src=None — убрать картинку."""
        from PIL import Image
        own = self.dir / f"{kind}.png"
        if src is None:
            own.unlink(missing_ok=True)
            return
        Image.open(src).convert("RGBA").save(own)

    # --- загрузка / сохранение -----------------------------------------------
    def load(self):
        if self.file.exists():
            try:
                stored = json.loads(self.file.read_text(encoding="utf-8"))
                self.values.update({k: v for k, v in stored.items() if k in DEFAULTS})
            except (OSError, ValueError):
                pass

    def save(self, new_values: dict):
        self.backup()
        self.values.update(new_values)
        self.file.write_text(json.dumps(self.values, ensure_ascii=False, indent=2), encoding="utf-8")

    def __getitem__(self, key):
        return self.values[key]

    # --- резервные копии -----------------------------------------------------
    def backup(self):
        self.backup_dir.mkdir(exist_ok=True)
        stamp = f"{datetime.now():%Y-%m-%d_%H-%M-%S}"
        name = self.backup_dir / f"{stamp}.zip"
        n = 1
        while name.exists():
            n += 1
            name = self.backup_dir / f"{stamp}_{n}.zip"
        with zipfile.ZipFile(name, "w") as z:
            for f in DATA_FILES:
                if (self.dir / f).exists():
                    z.write(self.dir / f, f)
        for old in self.list_backups()[MAX_BACKUPS:]:
            old.unlink(missing_ok=True)

    def list_backups(self) -> list[Path]:
        if not self.backup_dir.exists():
            return []
        return sorted(self.backup_dir.glob("*.zip"), reverse=True)

    def _clear_files(self, keep: tuple[str, ...] = ()):
        for f in DATA_FILES:
            if f not in keep:
                (self.dir / f).unlink(missing_ok=True)

    def restore(self, backup: Path):
        self.backup()
        self._clear_files()
        with zipfile.ZipFile(backup) as z:
            z.extractall(self.dir)
        self.values = copy.deepcopy(DEFAULTS)
        self.load()

    def reset_to_defaults(self):
        self.backup()
        pw = self.values.get("editor_password_hash", "")
        # логотипы и печать при сбросе не трогаем — сбрасываются только тексты и настройки
        self._clear_files(keep=tuple(f"{k}.png" for k in IMAGE_KINDS))
        self.values = copy.deepcopy(DEFAULTS)
        self.values["editor_password_hash"] = pw  # пароль сбросом не снимаем
        self.file.write_text(json.dumps(self.values, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- нумерация КП (не считается изменением шаблона) ---------------------
    def _state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def get_state(self, key: str, default=None):
        return self._state().get(key, default)

    def set_state(self, key: str, value):
        st = self._state()
        st[key] = value
        self.state_file.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")

    def next_number(self) -> int:
        return int(self._state().get("last_number", 0)) + 1

    def commit_number(self, n: int):
        st = self._state()
        st["last_number"] = max(n, int(st.get("last_number", 0)))
        self.state_file.write_text(json.dumps(st), encoding="utf-8")

