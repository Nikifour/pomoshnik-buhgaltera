"""Кнопки «Экспорт настроек» / «Импорт настроек» — общие для шаблона и мастера первого запуска."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from core.profile_transfer import EXTENSION, TransferError, apply_profile, export_profile, read_profile
from core.settings_store import Settings
from ui.widgets import ask, ask_cancel, error, info

FILTER = f"Настройки «Помощник Бухгалтера» (*{EXTENSION});;Все файлы (*.*)"
# при импорте принимаем и то, во что файл мог превратиться по дороге: .zip или распакованную папку
IMPORT_FILTER = (f"Настройки «Помощник Бухгалтера» (*{EXTENSION} *.zip settings.json);;"
                 "Все файлы (*.*)")


def export_settings(parent, s: Settings):
    include_stamp = False
    if s.image_path("stamp"):
        answer = ask_cancel(
            parent,
            "Включить в файл печать и подпись?\n\n"
            "Да — сотрудник сможет ставить печать в КП.\n"
            "Нет — файл можно спокойно пересылать: в нём будут только контакты, тексты и логотипы.")
        if answer is None:
            return
        include_stamp = answer
    name = re.sub(r'[\\/:*?"<>|«»]+', "", s["company_name"]).strip() or "Настройки"
    path, _ = QFileDialog.getSaveFileName(parent, "Сохранить настройки",
                                          str(Path.home() / "Desktop" / f"{name}{EXTENSION}"), FILTER)
    if not path:
        return
    try:
        out = export_profile(s, Path(path), include_stamp)
    except OSError as e:
        error(parent, f"Не удалось сохранить файл:\n{e}")
        return
    extra = ("Печать и подпись включены — передавайте файл только тем, кому положено."
             if include_stamp else "Печать и подпись не включены.")
    info(parent, f"Настройки сохранены:\n{out}\n\n{extra}\n\n"
                 "На другом компьютере откройте файл двойным щелчком или:\n"
                 "«Шаблон КП» → «Прочее» → «Импорт настроек».")


def import_settings(parent, s: Settings, path: str | Path | None = None) -> bool:
    """True — настройки применены (интерфейс нужно обновить).

    path — файл уже известен (открыли .pbsettings двойным щелчком), иначе спрашиваем.
    """
    if path is None:
        path, _ = QFileDialog.getOpenFileName(
            parent, "Файл настроек (или settings.json внутри распакованной папки)",
            str(Path.home() / "Desktop"), IMPORT_FILTER)
    if not path:
        return False
    try:
        profile = read_profile(Path(path))
    except TransferError as e:
        error(parent, str(e))
        return False
    m = profile["manifest"]
    names = {"logo": "логотип", "logo2": "второй логотип", "stamp": "печать и подпись"}
    imgs = ", ".join(names[k] for k in profile["images"]) or "нет"
    created = str(m.get("created", ""))[:16].replace("T", " ")
    if not ask(parent, f"Импортировать настройки компании «{m.get('company') or '—'}»?\n\n"
                       f"Создан: {created}\nКартинки: {imgs}\n\n"
                       "Текущий шаблон будет заменён (он сохранится в резервную копию)."):
        return False
    try:
        apply_profile(s, profile)
    except OSError as e:
        error(parent, f"Не удалось применить настройки:\n{e}")
        return False
    s.set_state("logo_setup_done", True)
    info(parent, "Настройки импортированы.")
    return True
