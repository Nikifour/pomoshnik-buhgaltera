"""Кнопки «Экспорт настроек» / «Импорт настроек» — общие для шаблона и мастера первого запуска."""
from __future__ import annotations

import re
from pathlib import Path
from tkinter import filedialog, messagebox

from core.profile_transfer import EXTENSION, TransferError, apply_profile, export_profile, read_profile
from core.settings_store import APP_NAME, Settings

FILETYPES = [("Настройки «Помощник Бухгалтера»", f"*{EXTENSION}"), ("Все файлы", "*.*")]


def export_settings(parent, s: Settings):
    include_stamp = False
    if s.image_path("stamp"):
        answer = messagebox.askyesnocancel(
            APP_NAME,
            "Включить в файл печать и подпись?\n\n"
            "Да — сотрудник сможет ставить печать в КП.\n"
            "Нет — файл можно спокойно пересылать: в нём будут только контакты, тексты и логотипы.",
            icon="warning", parent=parent)
        if answer is None:
            return
        include_stamp = answer
    name = re.sub(r'[\\/:*?"<>|«»]+', "", s["company_name"]).strip() or "Настройки"
    path = filedialog.asksaveasfilename(parent=parent, title="Сохранить настройки", defaultextension=EXTENSION,
                                        initialfile=f"{name}{EXTENSION}", filetypes=FILETYPES)
    if not path:
        return
    try:
        out = export_profile(s, Path(path), include_stamp)
    except OSError as e:
        messagebox.showerror(APP_NAME, f"Не удалось сохранить файл:\n{e}", parent=parent)
        return
    extra = "Печать и подпись включены — передавайте файл только тем, кому положено." if include_stamp \
        else "Печать и подпись не включены."
    messagebox.showinfo(APP_NAME, f"Настройки сохранены:\n{out}\n\n{extra}\n\n"
                                  "На другом компьютере откройте файл двойным щелчком или:\n"
                                  "«Шаблон КП» → «Прочее» → «Импорт настроек».", parent=parent)


def import_settings(parent, s: Settings, path: str | Path | None = None) -> bool:
    """True — настройки применены (интерфейс нужно перестроить).

    path — файл уже известен (открыли .pbsettings двойным щелчком), иначе спрашиваем.
    """
    if path is None:
        path = filedialog.askopenfilename(parent=parent, title="Файл настроек", filetypes=FILETYPES)
    if not path:
        return False
    try:
        profile = read_profile(Path(path))
    except TransferError as e:
        messagebox.showerror(APP_NAME, str(e), parent=parent)
        return False
    m = profile["manifest"]
    names = {"logo": "логотип", "logo2": "второй логотип", "stamp": "печать и подпись"}
    imgs = ", ".join(names[k] for k in profile["images"]) or "нет"
    created = str(m.get("created", ""))[:16].replace("T", " ")
    if not messagebox.askyesno(
            APP_NAME,
            f"Импортировать настройки компании «{m.get('company') or '—'}»?\n\n"
            f"Создан: {created}\nКартинки: {imgs}\n\n"
            "Текущий шаблон будет заменён (он сохранится в резервную копию).",
            parent=parent):
        return False
    try:
        apply_profile(s, profile)
    except OSError as e:
        messagebox.showerror(APP_NAME, f"Не удалось применить настройки:\n{e}", parent=parent)
        return False
    s.set_state("logo_setup_done", True)
    messagebox.showinfo(APP_NAME, "Настройки импортированы.", parent=parent)
    return True
