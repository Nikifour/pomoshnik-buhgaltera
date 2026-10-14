"""Чтение счёта на оплату (выгрузка 1С в Excel).

Колонки ищутся по заголовкам («Товары», «Количество», «Цена», «Сумма»),
а не по фиксированным адресам ячеек, поэтому небольшие изменения
макета счёта парсер переживает.
"""
from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import openpyxl

MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


class InvoiceError(Exception):
    pass


@dataclass
class Item:
    name: str
    qty: float
    unit: str
    price: float
    total: float


@dataclass
class Invoice:
    number: str = ""
    date: date | None = None
    buyer: str = ""
    buyer_details: str = ""
    items: list[Item] = field(default_factory=list)
    total: float = 0.0
    vat: float | None = None
    vat_label: str = "В т.ч. НДС:"
    source: str = ""


def _num(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.replace("\xa0", "").replace(" ", "").replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _parse_date(text: str) -> date | None:
    text = text.strip()
    m = re.search(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", text, re.I)
    if m and m.group(2).lower() in MONTHS:
        return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def split_buyer(text: str) -> tuple[str, str]:
    """«ТОО "Ромашка", БИН / ИИН 123, г.Алматы» -> (название, реквизиты)."""
    m = re.search(r",\s*(БИН|ИИН)", text)
    if m:
        return text[: m.start()].strip(), text[m.start() + 1:].strip()
    return text.strip(), ""


def _convert_xls(path: Path) -> Path:
    """Старый .xls через установленный Excel пересохраняем в .xlsx."""
    try:
        import win32com.client  # noqa: WPS433
    except ImportError as e:
        raise InvoiceError("Для файлов .xls нужен установленный Microsoft Excel.") from e
    out = Path(tempfile.mkdtemp()) / (path.stem + ".xlsx")
    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        wb = excel.Workbooks.Open(str(path.resolve()), ReadOnly=True)
        wb.SaveAs(str(out), FileFormat=51)
        wb.Close(False)
    finally:
        excel.Quit()
    return out


def parse_invoice(path: str | Path) -> Invoice:
    path = Path(path)
    if path.suffix.lower() == ".xls":
        path = _convert_xls(path)
    try:
        wb = openpyxl.load_workbook(path, data_only=True)
    except Exception as e:
        raise InvoiceError(f"Не удалось открыть файл:\n{e}") from e
    ws = wb.worksheets[0]

    grid: dict[tuple[int, int], object] = {}
    for row in ws.iter_rows():
        for c in row:
            if c.value is not None and str(c.value).strip() != "":
                grid[(c.row, c.column)] = c.value

    def row_values(r: int) -> list[tuple[int, object]]:
        return sorted((col, v) for (rr, col), v in grid.items() if rr == r)

    inv = Invoice(source=str(path))

    # Номер и дата
    for (r, c), v in grid.items():
        if isinstance(v, str):
            m = re.search(r"Сч[её]т\s+на\s+оплату\s*№\s*(\S+)\s+от\s+(.+)", v, re.I)
            if m:
                inv.number = m.group(1)
                inv.date = _parse_date(m.group(2))
                break

    # Покупатель — первое значение справа от «Покупатель:»
    for (r, c), v in sorted(grid.items()):
        if isinstance(v, str) and v.strip().lower().startswith("покупатель"):
            rest = [val for col, val in row_values(r) if col > c]
            if rest:
                inv.buyer, inv.buyer_details = split_buyer(str(rest[0]))
            break

    # Шапка таблицы товаров
    header_row = None
    cols: dict[str, int] = {}
    for (r, c), v in sorted(grid.items()):
        if isinstance(v, str) and v.strip().lower().startswith("товары"):
            header_row = r
            cols["name"] = c
            for col, val in row_values(r):
                s = str(val).strip().lower()
                if s == "№":
                    cols["no"] = col
                elif s.startswith("количество") or s.startswith("кол-во"):
                    cols["qty"] = col
                elif s.startswith("цена"):
                    cols["price"] = col
                elif s.startswith("сумма"):
                    cols["sum"] = col
            break
    if header_row is None or not {"no", "qty", "price", "sum"} <= cols.keys():
        raise InvoiceError("В файле не найдена таблица товаров.\n"
                           "Ожидаются колонки: №, Товары (работы, услуги), Количество, Цена, Сумма.")

    started = False
    r = header_row + 1
    max_row = max(rr for rr, _ in grid)
    while r <= max_row:
        no = _num(grid.get((r, cols["no"])))
        if no is None:
            if started:
                break
            r += 1
            continue
        started = True
        qty = _num(grid.get((r, cols["qty"]))) or 0
        # единица измерения — первое текстовое значение между «Количество» и «Цена»
        unit = ""
        for col, val in row_values(r):
            if cols["qty"] < col < cols["price"] and isinstance(val, str):
                unit = val.strip()
                break
        price = _num(grid.get((r, cols["price"]))) or 0
        total = _num(grid.get((r, cols["sum"])))
        inv.items.append(Item(
            name=" ".join(str(grid.get((r, cols["name"]), "")).split()),
            qty=qty, unit=unit, price=price,
            total=total if total is not None else round(qty * price, 2),
        ))
        r += 1

    if not inv.items:
        raise InvoiceError("В счёте нет ни одной позиции.")

    # Итоги
    for rr in range(r, max_row + 1):
        vals = row_values(rr)
        labels = [str(v) for _, v in vals if isinstance(v, str)]
        nums = [_num(v) for _, v in vals if _num(v) is not None and not isinstance(v, str)]
        if not labels or not nums:
            continue
        label = labels[0].strip()
        if "ндс" in label.lower() and "итого с" not in label.lower():
            inv.vat, inv.vat_label = nums[-1], label
        elif label.lower().startswith("итого"):
            inv.total = nums[-1]
    if not inv.total:
        inv.total = round(sum(i.total for i in inv.items), 2)

    return inv
