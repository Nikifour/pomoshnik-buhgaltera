"""Значки для КП, которые программа рисует сама (без файлов-картинок в репозитории)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WHATSAPP_GREEN = (37, 211, 102)
_CACHE = Path(tempfile.gettempdir()) / "pomoshnik-buhgaltera-icons"


def whatsapp_icon() -> Path:
    """Значок «есть WhatsApp»: зелёный пузырь с белой трубкой, 128×128, прозрачный фон."""
    path = _CACHE / "whatsapp_v1.png"
    if path.exists():
        return path
    _CACHE.mkdir(exist_ok=True)
    s = 512  # рисуем крупно и уменьшаем — так края гладкие
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((28, 20, 484, 476), fill=WHATSAPP_GREEN)
    d.polygon([(60, 350), (16, 500), (190, 444)], fill=WHATSAPP_GREEN)
    d.ellipse((80, 72, 432, 424), outline="white", width=28)
    handset = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    hd = ImageDraw.Draw(handset)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/seguisym.ttf", 250)
        hd.text((s // 2, s // 2), "\U0001F57B", font=font, fill="white", anchor="mm")
    except OSError:  # нет шрифта — простая трубка из линий
        hd.arc((170, 150, 340, 360), 100, 260, fill="white", width=46)
    handset = handset.rotate(-28, resample=Image.BICUBIC, center=(s // 2, s // 2))
    im.alpha_composite(handset, (0, -6))
    im.resize((128, 128), Image.LANCZOS).save(path)
    return path
