"""Текст с оформлением для полей шаблона (подпись, приветствие).

Формат хранения — список строк, строка — список кусочков:
    [[{"t": "ТОО «Инкомстрой»", "b": true, "i": false, "c": "text", "s": 11}], ...]
t — текст, b — жирный, i — курсив, c — цвет (text | muted | accent), s — размер шрифта.
Такой формат легко проверить при импорте и легко превратить в форматированную ячейку Excel.
"""
from __future__ import annotations

COLORS = ("text", "muted", "accent")
SIZE_RANGE = (7, 28)


def run(t: str, b=False, i=False, c="text", s=10) -> dict:
    return {"t": t, "b": b, "i": i, "c": c, "s": s}


def normalize(lines) -> list[list[dict]]:
    """Привести к допустимому виду (данные могут прийти из чужого файла настроек)."""
    out = []
    if not isinstance(lines, list):
        return out
    for line in lines[:200]:
        runs = []
        if isinstance(line, list):
            for r in line[:200]:
                if not isinstance(r, dict) or not isinstance(r.get("t"), str):
                    continue
                size = r.get("s", 10)
                size = int(min(max(size, SIZE_RANGE[0]), SIZE_RANGE[1])) if isinstance(size, (int, float)) \
                    and not isinstance(size, bool) else 10
                runs.append(run(r["t"][:2000], r.get("b") is True, r.get("i") is True,
                                r.get("c") if r.get("c") in COLORS else "text", size))
        out.append(runs)
    return out


def plain(lines) -> str:
    return "\n".join("".join(r["t"] for r in line) for line in normalize(lines))


def from_plain(text: str, style_for_line) -> list[list[dict]]:
    """Простой текст -> оформленные строки; style_for_line(номер) -> dict(b, i, c, s)."""
    return [[run(line, **style_for_line(i))] if line else [] for i, line in enumerate(text.split("\n"))]


def is_empty(lines) -> bool:
    return not plain(lines).strip()
