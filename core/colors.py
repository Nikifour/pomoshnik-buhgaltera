"""Работа с цветами: подбор цветовой схемы по логотипу."""
from __future__ import annotations

import colorsys
from pathlib import Path

from PIL import Image

# Готовые схемы для ручного выбора
PRESETS = {
    "Синяя": "#1F4E79",
    "Зелёная": "#284F0D",
    "Изумрудная": "#0F6B5C",
    "Бордовая": "#8B1E2D",
    "Фиолетовая": "#4B2C83",
    "Оранжевая": "#B4541A",
    "Графит": "#374151",
}


def hex_to_rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def rgb_to_hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(v))) for v in rgb))


def mix(c1: str, c2: str, t: float) -> str:
    """Смесь цветов: t=0 — c1, t=1 — c2."""
    a, b = hex_to_rgb(c1), hex_to_rgb(c2)
    return rgb_to_hex(x + (y - x) * t for x, y in zip(a, b))


def luminance(c: str) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in hex_to_rgb(c))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def readable_accent(c: str) -> str:
    """Затемняет цвет, пока белый текст на нём не станет читаемым (контраст ≥ 4.5)."""
    for _ in range(20):
        if 1.05 / (luminance(c) + 0.05) >= 4.5:
            return c
        c = mix(c, "#000000", 0.12)
    return c


def _saturation(rgb) -> tuple[float, float]:
    h, l, s = colorsys.rgb_to_hls(*(v / 255 for v in rgb))
    return s, l


def logo_palette(path: str | Path, n: int = 5) -> list[str]:
    """Основные цвета логотипа: без белого фона и серых оттенков, самые заметные первыми."""
    im = Image.open(path).convert("RGBA")
    im.thumbnail((200, 200))
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    rgb = Image.alpha_composite(bg, im).convert("RGB")
    q = rgb.quantize(colors=16, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors(), reverse=True)

    colorful, grey = [], []
    for count, idx in counts:
        c = tuple(pal[idx * 3: idx * 3 + 3])
        s, l = _saturation(c)
        if l > 0.92:  # фон
            continue
        (colorful if s > 0.25 and 0.12 < l < 0.85 else grey).append((count * (0.5 + s), c))
    picked = sorted(colorful, reverse=True) or sorted(grey, reverse=True)

    result: list[str] = []
    for _, c in picked:
        h = rgb_to_hex(c)
        # пропускаем почти одинаковые цвета
        if all(sum(abs(a - b) for a, b in zip(hex_to_rgb(h), hex_to_rgb(x))) > 60 for x in result):
            result.append(h)
        if len(result) >= n:
            break
    return result


def accent_from_logo(path: str | Path) -> str | None:
    pal = logo_palette(path)
    return readable_accent(pal[0]) if pal else None
