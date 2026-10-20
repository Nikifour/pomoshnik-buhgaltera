"""Макет КП: список блоков сверху вниз.

Блок — словарь {"id", "type", "visible", "props"}. Стандартные блоки (шапка, таблица, подпись…)
встречаются ровно по одному разу, их можно передвигать и скрывать, но не удалять.
Свои блоки (текст, картинка, две колонки, разделитель, отступ) можно добавлять сколько угодно.

Макет хранится в настройках (settings["layout"]); пустой список — стандартный макет.
Всё, что приходит извне (импорт файла настроек), проходит через normalize().
"""
from __future__ import annotations

import copy
import re
import uuid

ALIGN = {"left": "Слева", "center": "По центру", "right": "Справа"}
SIDE = {"left": "Слева", "right": "Справа"}
TEXT_COLOR = {"text": "Обычный", "muted": "Серый", "accent": "Фирменный цвет"}
DIVIDER_COLOR = {"accent": "Фирменный цвет", "grey": "Серый"}
THICKNESS = {"thin": "Тонкая", "thick": "Толстая"}

# Описание свойств: ключ -> (вид, значение по умолчанию, подпись, доп. параметры)
#   вид: text | multiline | int | bool | choice | image
BLOCKS: dict[str, dict] = {
    "header": {
        "title": "Шапка: логотипы и контакты", "icon": "🏢", "standard": True,
        "props": {
            "logo_side": ("choice", "left", "Логотипы", SIDE),
            "line": ("bool", True, "Линия под шапкой", None),
        },
    },
    "title": {
        "title": "Заголовок", "icon": "🔠", "standard": True,
        "props": {
            "text": ("text", "КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ", "Текст заголовка", None),
            "size": ("int", 20, "Размер шрифта", (10, 36)),
            "align": ("choice", "left", "Выравнивание", ALIGN),
            "show_number": ("bool", True, "Номер, дата и срок действия", None),
        },
    },
    "parties": {
        "title": "Кому / От", "icon": "👥", "standard": True,
        "props": {
            "show_to": ("bool", True, "Строка «Кому»", None),
            "show_from": ("bool", True, "Строка «От»", None),
        },
    },
    "greeting": {
        "title": "Приветствие", "icon": "💬", "standard": True,
        "note": "Текст приветствия редактируется в «Шаблон КП» → «Тексты».",
        "props": {
            "size": ("int", 10, "Размер шрифта", (8, 16)),
        },
    },
    "table": {
        "title": "Таблица товаров", "icon": "📋", "standard": True, "required": True,
        "note": "Таблица обязательна: её можно передвинуть, но нельзя скрыть.",
        "props": {},
    },
    "totals": {
        "title": "Итоги", "icon": "∑", "standard": True,
        "note": "Строки «Итого» и «НДС» включаются в «Шаблон КП» → «Из счёта».",
        "props": {},
    },
    "amount_words": {
        "title": "Сумма прописью", "icon": "🔤", "standard": True,
        "props": {},
    },
    "conditions": {
        "title": "Условия предложения", "icon": "📌", "standard": True,
        "note": "Пункты условий редактируются в «Шаблон КП» → «Тексты».",
        "props": {
            "heading": ("text", "Условия предложения", "Заголовок блока", None),
        },
    },
    "signature": {
        "title": "Подпись и печать", "icon": "✍", "standard": True,
        "props": {
            "stamp_side": ("choice", "right", "Печать", SIDE),
        },
    },
    # ---- свои блоки
    "text": {
        "title": "Текст", "icon": "📝", "standard": False,
        "props": {
            "text": ("multiline", "", "Текст", None),
            "size": ("int", 10, "Размер шрифта", (7, 32)),
            "bold": ("bool", False, "Жирный", None),
            "italic": ("bool", False, "Курсив", None),
            "align": ("choice", "left", "Выравнивание", ALIGN),
            "color": ("choice", "text", "Цвет текста", TEXT_COLOR),
            "background": ("bool", False, "Фон фирменного цвета (светлый)", None),
        },
    },
    "image": {
        "title": "Картинка", "icon": "🖼", "standard": False,
        "props": {
            "image": ("image", "", "Картинка", None),
            "width": ("int", 200, "Ширина, px", (30, 700)),
            "align": ("choice", "left", "Выравнивание", ALIGN),
        },
    },
    "columns": {
        "title": "Две колонки", "icon": "◫", "standard": False,
        "note": "В каждой колонке — картинка или текст. Если выбрана картинка, текст колонки не выводится.",
        "props": {
            "left_image": ("image", "", "Левая колонка: картинка", None),
            "left_text": ("multiline", "", "Левая колонка: текст", None),
            "right_image": ("image", "", "Правая колонка: картинка", None),
            "right_text": ("multiline", "", "Правая колонка: текст", None),
            "size": ("int", 10, "Размер шрифта", (7, 24)),
            "image_width": ("int", 180, "Ширина картинок, px", (30, 340)),
        },
    },
    "divider": {
        "title": "Разделитель", "icon": "➖", "standard": False,
        "props": {
            "color": ("choice", "accent", "Цвет линии", DIVIDER_COLOR),
            "thickness": ("choice", "thin", "Толщина", THICKNESS),
        },
    },
    "spacer": {
        "title": "Отступ", "icon": "↕", "standard": False,
        "props": {
            "height": ("int", 12, "Высота, pt", (2, 120)),
        },
    },
}

STANDARD_ORDER = ["header", "title", "parties", "greeting", "table", "totals", "amount_words",
                  "conditions", "signature"]
CUSTOM_TYPES = [t for t, d in BLOCKS.items() if not d["standard"]]
IMAGE_NAME_RE = re.compile(r"^[a-z0-9_]{1,40}\.png$")


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def default_props(btype: str) -> dict:
    return {k: copy.deepcopy(spec[1]) for k, spec in BLOCKS[btype]["props"].items()}


def make_block(btype: str, visible=True) -> dict:
    return {"id": btype if BLOCKS[btype]["standard"] else new_id(), "type": btype,
            "visible": visible, "props": default_props(btype)}


def default_layout(settings: dict | None = None) -> list[dict]:
    lay = [make_block(t) for t in STANDARD_ORDER]
    if settings is not None and not settings.get("show_amount_words", True):
        next(b for b in lay if b["type"] == "amount_words")["visible"] = False
    return lay


def _clean_prop(spec, value):
    kind, default, _, extra = spec
    if kind == "bool":
        return value if isinstance(value, bool) else default
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        lo, hi = extra
        return int(min(max(value, lo), hi))
    if kind == "choice":
        return value if value in extra else default
    if kind == "image":
        return value if isinstance(value, str) and (value == "" or IMAGE_NAME_RE.match(value)) else ""
    if isinstance(value, str):
        return value[:5000]
    return default


def normalize(raw, settings: dict | None = None) -> list[dict]:
    """Привести макет к допустимому виду: известные типы, проверенные свойства,
    каждый стандартный блок ровно один раз, таблица всегда видима."""
    if not isinstance(raw, list) or not raw:
        return default_layout(settings)
    out, seen_std, seen_ids = [], set(), set()
    for b in raw:
        if not isinstance(b, dict) or b.get("type") not in BLOCKS:
            continue
        btype = b["type"]
        spec = BLOCKS[btype]
        if spec["standard"]:
            if btype in seen_std:
                continue
            seen_std.add(btype)
            bid = btype
        else:
            bid = str(b.get("id", ""))
            if not re.fullmatch(r"[a-z0-9]{6,20}", bid) or bid in seen_ids:
                bid = new_id()
        seen_ids.add(bid)
        props_in = b.get("props") if isinstance(b.get("props"), dict) else {}
        props = {k: _clean_prop(s, props_in.get(k, s[1])) for k, s in spec["props"].items()}
        visible = True if spec.get("required") else bool(b.get("visible", True))
        out.append({"id": bid, "type": btype, "visible": visible, "props": props})
    # недостающие стандартные блоки — на их обычное место относительно соседей
    for i, btype in enumerate(STANDARD_ORDER):
        if btype in seen_std:
            continue
        pos = len(out)
        for prev in reversed(STANDARD_ORDER[:i]):
            idx = next((j for j, b in enumerate(out) if b["type"] == prev), None)
            if idx is not None:
                pos = idx + 1
                break
        else:
            pos = 0
        out.insert(pos, make_block(btype))
    return out


def referenced_images(layout: list[dict]) -> set[str]:
    """Имена файлов картинок своих блоков, на которые ссылается макет."""
    names = set()
    for b in layout:
        for k, spec in BLOCKS[b["type"]]["props"].items():
            if spec[0] == "image" and b["props"].get(k):
                names.add(b["props"][k])
    return names


def block_title(b: dict) -> str:
    spec = BLOCKS[b["type"]]
    title = spec["title"]
    if b["type"] == "text" and b["props"].get("text"):
        first = b["props"]["text"].strip().splitlines()[0] if b["props"]["text"].strip() else ""
        if first:
            title += f": {first[:28]}{'…' if len(first) > 28 else ''}"
    return f"{spec['icon']}  {title}"
