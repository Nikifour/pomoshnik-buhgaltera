"""Сборка КП в Excel. Здесь живёт макет — пользователь его не видит и не меняет."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.drawing.image import Image as XLImage
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
from openpyxl.drawing.xdr import XDRPositiveSize2D
from openpyxl.utils import column_index_from_string
from openpyxl.utils.units import pixels_to_EMU
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.page import PageMargins

from core.invoice_parser import Invoice, Item
from core.num_words import amount_in_words

FONT = "Calibri"
GREY = "6B7280"
DARK = "1F2937"
LINE = "E5E7EB"

# Колонки: поле, №, наименование, кол-во, ед., цена, сумма, поле
COLS = {"A": 1.5, "B": 5, "C": 50, "D": 9, "E": 7, "F": 14, "G": 16, "H": 1.5}
TABLE_WIDTH = sum(COLS[c] for c in "BCDEFG")
FIRST, LAST = "B", "G"


@dataclass
class KPMeta:
    number: str  # по умолчанию — номер счёта на оплату
    date: date
    buyer: str
    buyer_details: str = ""


def _hex(color: str) -> str:
    return color.lstrip("#").upper()


def _tint(color: str, factor: float) -> str:
    """Осветлить цвет (factor 0..1, ближе к 1 — светлее)."""
    c = _hex(color)
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda x: round(x + (255 - x) * factor)  # noqa: E731
    return f"{mix(r):02X}{mix(g):02X}{mix(b):02X}"


def _lines(text: str, width_chars: float) -> int:
    return sum(max(1, math.ceil(len(p) / max(width_chars, 1))) for p in text.split("\n"))


def _fmt_money(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def _fmt_qty(v: float) -> float | int:
    return int(v) if float(v).is_integer() else v


def fill_placeholders(text: str, s: dict, meta: KPMeta) -> str:
    return (text.replace("{КОМПАНИЯ}", s["company_name"])
                .replace("{ПОКУПАТЕЛЬ}", meta.buyer)
                .replace("{МЕНЕДЖЕР}", s["manager_name"]))


def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "", name).strip()[:150]


def build_kp(inv: Invoice, meta: KPMeta, s: dict, images: dict[str, Path | None],
             out_path: Path) -> Path:
    """images: {'logo': ..., 'logo2': ..., 'stamp': ...}, None — картинки нет."""
    accent = _hex(s["accent_color"])
    light = _tint(accent, 0.92)

    wb = Workbook()
    ws = wb.active
    ws.title = "КП"
    ws.sheet_view.showGridLines = False
    for col, w in COLS.items():
        ws.column_dimensions[col].width = w

    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.4, bottom=0.5)
    ws.print_options.horizontalCentered = True
    # Подвал печатается внизу каждой страницы и не сдвигает содержимое
    footer_text = " ".join(s["footer"].split()).replace("&", "&&")[:200]
    if footer_text:
        ws.oddFooter.left.text = footer_text
        ws.oddFooter.left.size = 7
        ws.oddFooter.left.color = GREY
    ws.oddFooter.right.text = "стр. &P из &N"
    ws.oddFooter.right.size = 7
    ws.oddFooter.right.color = GREY

    def font(size=10, bold=False, color=DARK, italic=False):
        return Font(name=FONT, size=size, bold=bold, color=color, italic=italic)

    def put(row, col, value, merge_to=None, f=None, align="left", valign="center", wrap=False,
            fill=None, fmt=None):
        cell = ws[f"{col}{row}"]
        cell.value = value
        cell.font = f or font()
        cell.alignment = Alignment(horizontal=align, vertical=valign, wrap_text=wrap)
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill)
        if fmt:
            cell.number_format = fmt
        if merge_to:
            ws.merge_cells(f"{col}{row}:{merge_to}{row}")
        return cell

    def fill_row(row, color, c1=FIRST, c2=LAST):
        for c in range(ord(c1), ord(c2) + 1):
            ws[f"{chr(c)}{row}"].fill = PatternFill("solid", fgColor=color)

    def height(row, h):
        ws.row_dimensions[row].height = h

    def place_image(path, cell, max_w, max_h, dy=0):
        """Вписать картинку в рамку max_w x max_h px со смещением dy px вниз от ячейки."""
        img = XLImage(str(path))
        k = min(max_w / img.width, max_h / img.height)
        img.width, img.height = img.width * k, img.height * k
        col = column_index_from_string(re.match(r"[A-Z]+", cell).group()) - 1
        row = int(re.search(r"\d+", cell).group()) - 1
        # Excel не даёт смещению выйти за высоту строки — переносим его на нужную строку
        while True:
            row_px = (ws.row_dimensions[row + 1].height or 15) * 96 / 72
            if dy < row_px:
                break
            dy -= row_px
            row += 1
        img.anchor = OneCellAnchor(
            _from=AnchorMarker(col=col, colOff=0, row=row, rowOff=pixels_to_EMU(dy)),
            ext=XDRPositiveSize2D(pixels_to_EMU(img.width), pixels_to_EMU(img.height)),
        )
        ws.add_image(img)
        return img

    def paragraph(row, text, f=None, h_per_line=14.5, width=TABLE_WIDTH):
        put(row, FIRST, text, LAST, f=f, wrap=True, valign="top")
        height(row, _lines(text, width * 1.05) * h_per_line + 3)

    # ---------- Шапка: логотип + контакты ----------
    height(1, 8)
    r = 2
    contacts = [
        (s["company_full_name"] or s["company_name"], font(11, True)),
        (s["address"], font(9, color=GREY)),
        ("   ·   ".join(x for x in (s["phone"] and f"Тел.: {s['phone']}", s["email"]) if x),
         font(9, color=GREY)),
        (s["website"], font(9, True, accent)),
    ]
    contacts = [c for c in contacts if c[0]]
    for i, (text, f) in enumerate(contacts):
        put(r + i, "C", text, LAST, f=f, align="right", wrap=True)
        height(r + i, 16 if _lines(text, TABLE_WIDTH - 20) == 1 else 28)
    header_rows = max(len(contacts), 4)
    # основной логотип сверху, второй (бренд магазинов) под ним
    logo_h = 0
    if images.get("logo"):
        logo_h = place_image(images["logo"], f"B{r}", 240, 46, dy=2).height
    if images.get("logo2"):
        place_image(images["logo2"], f"B{r}", 150, 22, dy=logo_h + 12 if logo_h else 2)
    r += header_rows
    height(r, 6)
    r += 1
    fill_row(r, accent)
    height(r, 3)
    r += 2

    # ---------- Заголовок ----------
    put(r, FIRST, "КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ", LAST, f=font(20, True, accent))
    height(r, 30)
    r += 1
    sub = f"№ {meta.number} от {meta.date:%d.%m.%Y}"
    if s.get("validity_days"):
        sub += f"   ·   действительно до {meta.date + timedelta(days=int(s['validity_days'])):%d.%m.%Y}"
    put(r, FIRST, sub, LAST, f=font(10, color=GREY))
    height(r, 16)
    r += 2

    # ---------- Кому / От кого ----------
    def labeled(row, label, value, details=""):
        rich = CellRichText(
            TextBlock(InlineFont(rFont=FONT, sz=10, color=GREY), f"{label}  "),
            TextBlock(InlineFont(rFont=FONT, sz=10, b=True, color=DARK), value),
        )
        if details:
            rich.append(TextBlock(InlineFont(rFont=FONT, sz=9, color=GREY), f"\n{details}"))
        put(row, FIRST, rich, LAST, wrap=True, valign="top", fill=light)
        fill_row(row, light)
        height(row, _lines(label + value, TABLE_WIDTH) * 15 + (_lines(details, TABLE_WIDTH * 1.1) * 13 if details else 0) + 6)

    if meta.buyer or meta.buyer_details:
        labeled(r, "Кому:", meta.buyer or "—", meta.buyer_details)
        r += 1
    if s["company_name"]:
        labeled(r, "От:", s["company_name"])
        r += 1
    r += 1

    # ---------- Приветствие ----------
    greeting = fill_placeholders(s["greeting"], s, meta).strip()
    if greeting:
        paragraph(r, greeting, font(10.5))
        r += 2

    # ---------- Таблица ----------
    thin = Side(style="thin", color=LINE)
    headers = [("B", "№", "center"), ("C", "Наименование", "left"), ("D", "Кол-во", "center"),
               ("E", "Ед.", "center"), ("F", "Цена", "right"), ("G", "Сумма", "right")]
    for col, title, al in headers:
        put(r, col, title, f=font(10, True, "FFFFFF"), align=al, fill=accent)
    height(r, 22)
    r += 1

    for i, it in enumerate(inv.items, 1):
        zebra = "FFFFFF" if i % 2 else "F9FAFB"
        vals = [("B", i, "center", None), ("C", it.name, "left", None),
                ("D", _fmt_qty(it.qty), "center", None), ("E", it.unit, "center", None),
                ("F", it.price, "right", "#,##0.00"), ("G", it.total, "right", "#,##0.00")]
        for col, v, al, fmt in vals:
            c = put(r, col, v, align=al, wrap=(col == "C"), fill=zebra, fmt=fmt,
                    f=font(10, bold=(col == "G")))
            c.border = Border(bottom=thin)
        height(r, max(20, _lines(it.name, COLS["C"] * 1.12) * 14 + 6))
        r += 1

    # ---------- Итоги ----------
    r += 1
    def total_row(label, value, big=False):
        nonlocal r
        put(r, "D", label, "F", f=font(12 if big else 10, big, DARK if big else GREY), align="right")
        put(r, "G", value, f=font(12 if big else 10, True, accent if big else DARK), align="right",
            fmt="#,##0.00")
        if big:
            fill_row(r, light, "D", "G")
        height(r, 24 if big else 17)
        r += 1

    if s.get("show_vat", True) and inv.vat is not None:
        total_row("Итого:", inv.total)
        total_row(inv.vat_label.rstrip(":") + ":", inv.vat)
    total_row("Сумма предложения, KZT:", inv.total, big=True)
    r += 1
    if s.get("show_amount_words", True):
        paragraph(r, f"Всего наименований {len(inv.items)}, на сумму {_fmt_money(inv.total)} KZT\n"
                     f"{amount_in_words(inv.total)}", font(10, italic=True, color=GREY))
        r += 2

    # ---------- Условия ----------
    conditions = [c.strip() for c in s["conditions"].splitlines() if c.strip()]
    if conditions:
        put(r, FIRST, "Условия предложения", LAST, f=font(12, True, accent))
        height(r, 20)
        for c in range(ord(FIRST), ord(LAST) + 1):
            ws[f"{chr(c)}{r}"].border = Border(bottom=Side(style="thin", color=accent))
        r += 1
        for line in conditions:
            put(r, FIRST, "•", f=font(10, True, accent), align="center", valign="top")
            put(r, "C", line, LAST, wrap=True, valign="top")
            height(r, _lines(line, (TABLE_WIDTH - COLS["B"]) * 1.25) * 14.5 + 2)
            r += 1
        r += 1

    # ---------- Подпись ----------
    sign_start = r
    put(r, FIRST, "С уважением,", "C", f=font(10, color=GREY))
    r += 1
    put(r, FIRST, s["manager_name"], "C", f=font(11, True))
    r += 1
    if s["manager_position"]:
        put(r, FIRST, f"{s['manager_position']}, {s['company_name']}", "C", f=font(10, color=GREY))
        r += 1
    if s["manager_phone"]:
        put(r, FIRST, f"Тел.: {s['manager_phone']}", "C", f=font(10, color=GREY))
        r += 1
    if s["email"]:
        put(r, FIRST, s["email"], "C", f=font(10, color=GREY))
        r += 1
    for rr in range(sign_start, r):
        height(rr, 16)
    if s["show_stamp"] and images.get("stamp"):
        place_image(images["stamp"], f"D{max(sign_start - 1, 1)}", 260, 115)
        r = max(r, sign_start + 6)
    r += 1

    ws.print_area = f"A1:H{r}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path


def export_pdf(xlsx: Path) -> Path:
    """PDF через установленный Excel. Бросает исключение, если Excel недоступен."""
    import pythoncom
    import win32com.client
    pdf = xlsx.with_suffix(".pdf")
    pythoncom.CoInitialize()
    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        wb = excel.Workbooks.Open(str(xlsx.resolve()), ReadOnly=True)
        wb.ExportAsFixedFormat(0, str(pdf.resolve()))
        wb.Close(False)
    finally:
        excel.Quit()
        pythoncom.CoUninitialize()
    return pdf


def demo_invoice() -> tuple[Invoice, KPMeta]:
    """Данные для предпросмотра в редакторе шаблона.

    Только вымышленные обезличенные позиции — без брендов и без данных из реальных документов.
    """
    inv = Invoice(
        number="0000", date=date.today(), buyer="ТОО «Пример покупателя»",
        buyer_details="БИН / ИИН 000000000000, г. Город, ул. Примерная, 1",
        items=[
            Item("Пример товара № 1", 1, "шт", 10000, 10000),
            Item("Пример товара № 2", 2, "шт", 2500, 5000),
            Item("Пример товара № 3 с длинным названием, чтобы проверить перенос строк "
                 "в таблице коммерческого предложения", 3, "шт", 1500, 4500),
        ],
        total=19500, vat=round(19500 * 16 / 116, 2), vat_label="В т.ч. НДС (16%):",
    )
    return inv, KPMeta(number="0000", date=date.today(), buyer=inv.buyer, buyer_details=inv.buyer_details)
