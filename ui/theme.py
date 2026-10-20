"""Оформление интерфейса: цвета светлой/тёмной темы и таблица стилей Qt (QSS).

Фирменные цвета вычисляются из одного акцентного цвета (настройка «Цветовая схема»,
её же можно подобрать по логотипу). Смена схемы или темы применяется мгновенно —
apply() пересобирает таблицу стилей для всего приложения.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from core.colors import mix, readable_accent
from core.settings_store import DEFAULT_ACCENT

FONT_FAMILY = "Segoe UI"

LIGHT = {
    "bg": "#F3F4F6", "card": "#FFFFFF", "border": "#E2E4E8", "text": "#1F2937", "muted": "#6B7280",
    "input": "#F9FAFB", "alt": "#F9FAFB", "warn_bg": "#FEF3C7", "warn_text": "#92400E", "danger": "#B91C1C",
}
DARK = {
    "bg": "#16171A", "card": "#212226", "border": "#33353A", "text": "#E5E7EB", "muted": "#9CA3AF",
    "input": "#1A1B1F", "alt": "#26272C", "warn_bg": "#3A2F12", "warn_text": "#FCD34D", "danger": "#F87171",
}

_mode = "light"            # light | dark | system
_accent = DEFAULT_ACCENT
BRAND = DEFAULT_ACCENT     # текущий акцент (уже затемнённый до читаемого)


def set_mode(mode: str):
    global _mode
    _mode = mode if mode in ("light", "dark", "system") else "light"


def is_dark() -> bool:
    if _mode == "system":
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    return _mode == "dark"


def apply_accent(accent: str):
    global _accent, BRAND
    try:
        BRAND = readable_accent(accent)
        _accent = accent
    except (ValueError, IndexError):
        BRAND = _accent = DEFAULT_ACCENT


def colors() -> dict:
    """Все цвета текущей темы, включая производные от акцента."""
    c = dict(DARK if is_dark() else LIGHT)
    dark = is_dark()
    sidebar = mix(BRAND, "#000000", 0.62 if dark else 0.25)
    c.update(
        brand=BRAND,
        brand_hover=mix(BRAND, "#000000", 0.2),
        brand_soft=mix(BRAND, c["card"], 0.86),
        sidebar=sidebar,
        sidebar_active=mix(sidebar, "#FFFFFF", 0.14),
        sidebar_hover=mix(sidebar, "#FFFFFF", 0.07),
        sidebar_muted=mix(sidebar, "#FFFFFF", 0.65),
        sidebar_border=mix(sidebar, "#FFFFFF", 0.28),
        info_bg=mix(BRAND, c["card"], 0.85 if not dark else 0.6),
    )
    return c


def _arrows(c: dict) -> dict:
    """Стрелки для выпадающих списков и счётчиков: рисуем PNG под цвет темы (без внешних файлов)."""
    from PySide6.QtGui import QPainter, QPen, QPixmap
    folder = Path(tempfile.gettempdir()) / "pomoshnik-buhgaltera-ui"
    folder.mkdir(exist_ok=True)
    out = {}
    for name, color, up in (("down", c["muted"], False), ("up", c["muted"], True), ("down_white", "#FFFFFF", False)):
        path = folder / f"arrow_{name}_{color.lstrip('#')}.png"
        if not path.exists():
            pm = QPixmap(40, 40)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            pen = QPen(QColor(color), 5)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            pts = [(8, 26), (20, 14), (32, 26)] if up else [(8, 14), (20, 26), (32, 14)]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                p.drawLine(x1, y1, x2, y2)
            p.end()
            pm.save(str(path))
        out[name] = path.as_posix()
    return out


def stylesheet() -> str:
    c = colors()
    arrows = _arrows(c)
    return f"""
* {{ font-family: "{FONT_FAMILY}"; font-size: 10pt; }}
QWidget {{ color: {c['text']}; }}
QMainWindow, QDialog, #content, #page {{ background: {c['bg']}; }}
QToolTip {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 4px 8px; }}

/* --- боковая панель --- */
#sidebar {{ background: {c['sidebar']}; }}
#sidebar QLabel {{ color: white; background: transparent; }}
#sidebar QLabel[muted="true"] {{ color: {c['sidebar_muted']}; }}
QPushButton#nav {{
    text-align: left; padding: 11px 14px; border: none; border-radius: 8px;
    color: white; background: transparent; font-size: 11pt;
}}
QPushButton#nav:hover {{ background: {c['sidebar_hover']}; }}
QPushButton#nav:checked {{ background: {c['sidebar_active']}; font-weight: 600; }}
QPushButton#sideButton {{
    padding: 7px 10px; border-radius: 8px; color: white; background: transparent;
    border: 1px solid {c['sidebar_border']};
}}
QPushButton#sideButton:hover {{ background: {c['sidebar_hover']}; }}
#sidebar QComboBox {{
    background: {c['sidebar_active']}; color: white; border: none; border-radius: 8px; padding: 6px 10px;
}}
#sidebar QComboBox QAbstractItemView {{ background: {c['card']}; color: {c['text']}; }}

/* --- текст --- */
QLabel#h1 {{ font-size: 19pt; font-weight: 700; }}
QLabel#h2 {{ font-size: 12pt; font-weight: 700; }}
QLabel#big {{ font-size: 16pt; font-weight: 700; }}
QLabel[muted="true"] {{ color: {c['muted']}; }}
QLabel[small="true"] {{ font-size: 9pt; }}
QLabel#warn {{ background: {c['warn_bg']}; color: {c['warn_text']}; border-radius: 8px; padding: 9px 14px; }}
QLabel#success {{ color: {c['brand']}; font-size: 13pt; font-weight: 700; }}

/* --- карточки и баннеры --- */
QFrame#card {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 12px; }}
QFrame#card QLabel {{ background: transparent; }}
QFrame#banner {{ background: {c['info_bg']}; border-radius: 10px; }}
QFrame#preview {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 12px; }}
QFrame#row {{ background: transparent; border-radius: 8px; }}
QFrame#row[alt="true"] {{ background: {c['alt']}; }}
QFrame#dropzone {{ background: {c['card']}; border: 2px dashed {c['border']}; border-radius: 12px; }}
QFrame#dropzone[active="true"] {{ border-color: {c['brand']}; background: {c['brand_soft']}; }}

/* --- кнопки --- */
QPushButton {{
    background: {c['card']}; border: 1px solid {c['border']}; border-radius: 8px;
    padding: 7px 16px; min-height: 20px;
}}
QPushButton:hover {{ background: {c['border']}; }}
QPushButton:disabled {{ color: {c['muted']}; }}
QPushButton[kind="primary"] {{
    background: {c['brand']}; color: white; border: none; font-weight: 600; padding: 8px 18px;
}}
QPushButton[kind="primary"]:hover {{ background: {c['brand_hover']}; }}
QPushButton[kind="primary"]:disabled {{ background: {c['border']}; color: {c['muted']}; }}
QPushButton[size="large"] {{ font-size: 11pt; padding: 11px 24px; }}

/* --- поля ввода --- */
QLineEdit, QPlainTextEdit, QDateEdit, QSpinBox, QComboBox {{
    background: {c['input']}; border: 1px solid {c['border']}; border-radius: 8px;
    padding: 6px 10px; selection-background-color: {c['brand']}; selection-color: white;
}}
QLineEdit:focus, QPlainTextEdit:focus, QDateEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {c['brand']};
}}
QComboBox::drop-down, QDateEdit::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right; width: 26px; border: none; background: transparent;
}}
QComboBox::down-arrow, QDateEdit::down-arrow, QSpinBox::down-arrow {{ image: url("{arrows['down']}"); width: 10px; height: 10px; }}
QSpinBox::up-arrow {{ image: url("{arrows['up']}"); width: 10px; height: 10px; }}
#sidebar QComboBox::down-arrow {{ image: url("{arrows['down_white']}"); }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 20px; border: none; background: transparent; }}
QComboBox QAbstractItemView {{
    background: {c['card']}; border: 1px solid {c['border']}; selection-background-color: {c['brand']};
}}
QCalendarWidget QWidget {{ alternate-background-color: {c['alt']}; }}
QCalendarWidget QToolButton {{ color: {c['text']}; background: transparent; padding: 4px; }}
QCalendarWidget QAbstractItemView {{ selection-background-color: {c['brand']}; selection-color: white; }}

/* --- таблицы --- */
QTableWidget {{
    background: {c['card']}; border: none; gridline-color: transparent;
    alternate-background-color: {c['alt']};
    selection-background-color: {c['brand']}; selection-color: white;
}}
QTableWidget::item {{ padding: 4px 6px; border: none; }}
QHeaderView::section {{
    background: {c['bg']}; color: {c['muted']}; border: none; padding: 8px 6px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {c['bg']}; border: none; }}

/* --- вкладки --- */
QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 12px; background: {c['card']}; top: -1px; }}
QTabWidget::tab-bar {{ alignment: center; }}
QTabBar::tab {{
    padding: 7px 18px; margin: 0 2px 8px 2px; border-radius: 8px;
    color: {c['muted']}; background: {c['border']};
}}
QTabBar::tab:selected {{ background: {c['brand']}; color: white; font-weight: 600; }}
QTabBar::tab:hover:!selected {{ color: {c['text']}; }}

/* --- прокрутка --- */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
QScrollBar:horizontal {{ height: 0; }}

/* --- прочее --- */
QProgressBar {{ background: {c['border']}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {c['brand']}; border-radius: 4px; }}
QMenu {{ background: {c['card']}; border: 1px solid {c['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['brand']}; color: white; }}
QMessageBox QLabel {{ background: transparent; }}
"""


def apply(app: QApplication | None = None):
    """Применить тему и акцент ко всему приложению."""
    app = app or QApplication.instance()
    c = colors()
    pal = QPalette()
    for role, key in ((QPalette.Window, "bg"), (QPalette.Base, "card"), (QPalette.AlternateBase, "alt"),
                      (QPalette.Button, "card"), (QPalette.ToolTipBase, "card")):
        pal.setColor(role, QColor(c[key]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText, QPalette.ToolTipText):
        pal.setColor(role, QColor(c["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(c["muted"]))
    pal.setColor(QPalette.Highlight, QColor(c["brand"]))
    pal.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet())
