"""Страница «Новое КП»: счёт -> данные КП -> файл."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QAbstractItemView, QDateEdit, QDialog, QFileDialog, QFrame, QGridLayout,
                               QHeaderView, QLineEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core.invoice_parser import Invoice, InvoiceError, parse_invoice
from core.kp_builder import KPMeta, build_kp, export_pdf, safe_filename
from core.settings_store import Settings
from ui.widgets import (Card, Toggle, button, error, hbox, label, open_path, page_header, repolish,
                        run_in_background, warn, ask)

INVOICE_EXT = (".xlsx", ".xlsm", ".xls")


def money(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


class DropZone(QFrame):
    """Карточка выбора счёта: кнопка или перетаскивание файла мышкой."""

    def __init__(self, on_file, on_click):
        super().__init__()
        self.setObjectName("dropzone")
        self.setAcceptDrops(True)
        self.on_file = on_file
        lay = QGridLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setHorizontalSpacing(18)
        self.btn = button("📄  Выбрать счёт на оплату", on_click, primary=True, large=True)
        lay.addWidget(self.btn, 0, 0, 2, 1)
        self.title = label("Счёт не выбран", name="h2")
        self.sub = label("Нажмите кнопку или перетащите сюда файл Excel (.xlsx / .xls), выгруженный из 1С",
                         muted=True, wrap=True)
        lay.addWidget(self.title, 0, 1)
        lay.addWidget(self.sub, 1, 1)
        lay.setColumnStretch(1, 1)

    def _files(self, event):
        return [u.toLocalFile() for u in event.mimeData().urls()
                if u.toLocalFile().lower().endswith(INVOICE_EXT)]

    def _set_active(self, on):
        self.setProperty("active", on)
        repolish(self)

    def dragEnterEvent(self, e):  # noqa: N802
        if self._files(e):
            e.acceptProposedAction()
            self._set_active(True)

    def dragLeaveEvent(self, e):  # noqa: N802
        self._set_active(False)

    def dropEvent(self, e):  # noqa: N802
        self._set_active(False)
        files = self._files(e)
        if files:
            self.on_file(files[0])


class NewKPPage(QWidget):
    def __init__(self, settings: Settings, on_created=None):
        super().__init__()
        self.setObjectName("page")
        self.s = settings
        self.on_created = on_created
        self.invoice: Invoice | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        root.addWidget(page_header("Новое коммерческое предложение",
                                   "Выберите счёт на оплату — данные перенесутся в КП автоматически"))
        root.addSpacing(4)

        # --- 1. Счёт
        self.drop = DropZone(self.load_invoice, self.choose_invoice)
        root.addWidget(self.drop)

        # --- 2. Данные КП
        c2 = Card("Данные КП")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self.ed_buyer = QLineEdit()
        self.ed_details = QLineEdit()
        self.ed_number = QLineEdit()
        self.ed_number.setFixedWidth(130)
        self.ed_date = QDateEdit()
        self.ed_date.setCalendarPopup(True)
        self.ed_date.setDisplayFormat("dd.MM.yyyy")
        self.ed_date.setDate(QDate.currentDate())
        self.ed_date.setFixedWidth(140)
        self.tg_pdf = Toggle("Сохранить также в PDF")
        grid.addWidget(label("Кому", muted=True), 0, 0)
        grid.addWidget(self.ed_buyer, 0, 1)
        grid.addWidget(label("Реквизиты", muted=True), 1, 0)
        grid.addWidget(self.ed_details, 1, 1)
        grid.addWidget(label("№ КП", muted=True), 2, 0)
        grid.addLayout(hbox(self.ed_number, 16, label("Дата", muted=True), self.ed_date, "stretch", self.tg_pdf), 2, 1)
        grid.setColumnStretch(1, 1)
        c2.body.addLayout(grid)
        root.addWidget(c2)

        # --- 3. Позиции
        c3 = Card("Позиции")
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["№", "Наименование", "Кол-во", "Ед.", "Цена", "Сумма"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(32)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setHighlightSections(False)
        for col, align in ((0, Qt.AlignCenter), (2, Qt.AlignCenter), (3, Qt.AlignCenter),
                           (4, Qt.AlignRight), (5, Qt.AlignRight)):
            self.table.horizontalHeaderItem(col).setTextAlignment(align | Qt.AlignVCenter)
        self.empty = label("Здесь появятся позиции из счёта", muted=True)
        self.empty.setAlignment(Qt.AlignCenter)
        c3.body.addWidget(self.empty)
        c3.body.addWidget(self.table, 1)
        self.table.hide()
        root.addWidget(c3, 1)

        # --- Итог
        self.lbl_total = label("", name="big")
        self.lbl_vat = label("", muted=True)
        totals = QVBoxLayout()
        totals.setSpacing(0)
        totals.addWidget(self.lbl_total)
        totals.addWidget(self.lbl_vat)
        self.btn_make = button("Сформировать КП  →", self.make_kp, primary=True, large=True, width=230)
        self.btn_make.setEnabled(False)
        bar = hbox("stretch", self.btn_make)
        bar.insertLayout(0, totals)
        root.addLayout(bar)
        self.refresh()

    # ------------------------------------------------------------------
    def choose_invoice(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите счёт на оплату", str(Path.home() / "Desktop"),
                                              "Excel (*.xlsx *.xlsm *.xls);;Все файлы (*.*)")
        if path:
            self.load_invoice(path)

    def load_invoice(self, path: str):
        try:
            inv = parse_invoice(path)
        except InvoiceError as e:
            error(self, str(e))
            return
        except Exception as e:  # noqa: BLE001
            error(self, f"Не удалось прочитать счёт:\n{e}")
            return
        self.invoice = inv
        self.drop.title.setText(f"Счёт на оплату № {inv.number}" + (f" от {inv.date:%d.%m.%Y}" if inv.date else ""))
        self.drop.sub.setText(Path(path).name)
        # что брать из счёта — настраивается в «Шаблон КП» → «Из счёта»
        s = self.s
        self.ed_buyer.setText(inv.buyer if s["fill_buyer"] else "")
        self.ed_details.setText(inv.buyer_details if s["fill_buyer_details"] else "")
        # № КП = № счёта; если выключено или в счёте номера нет — свой счётчик
        self.ed_number.setText(inv.number if s["fill_number"] and inv.number else str(s.next_number()))
        d = inv.date if s["fill_date"] and inv.date else date.today()
        self.ed_date.setDate(QDate(d.year, d.month, d.day))

        self.table.setRowCount(len(inv.items))
        for r, it in enumerate(inv.items):
            qty = int(it.qty) if float(it.qty).is_integer() else it.qty
            for col, val, align in ((0, r + 1, Qt.AlignCenter), (1, it.name, Qt.AlignLeft),
                                    (2, qty, Qt.AlignCenter), (3, it.unit, Qt.AlignCenter),
                                    (4, money(it.price), Qt.AlignRight), (5, money(it.total), Qt.AlignRight)):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(align | Qt.AlignVCenter)
                self.table.setItem(r, col, item)
        self.empty.hide()
        self.table.show()
        self.lbl_total.setText(f"{money(inv.total)} KZT")
        vat = f"  ·  в т.ч. НДС {money(inv.vat)}" if inv.vat is not None else ""
        self.lbl_vat.setText(f"Позиций: {len(inv.items)}{vat}")
        self.btn_make.setEnabled(True)

    def make_kp(self):
        if not self.invoice:
            return
        number = self.ed_number.text().strip()
        if not number:
            error(self, "Укажите № КП.")
            return
        qd = self.ed_date.date()
        kp_date = date(qd.year(), qd.month(), qd.day())
        meta = KPMeta(number, kp_date, self.ed_buyer.text().strip(), self.ed_details.text().strip())
        short_buyer = meta.buyer.replace("Товарищество с ограниченной ответственностью", "ТОО")
        name = f"КП № {number} от {kp_date:%d.%m.%Y}" + (f" - {short_buyer}" if short_buyer else "")
        out = Path(self.s["output_dir"]) / f"{safe_filename(name)}.xlsx"
        if out.exists() and not ask(self, f"Файл уже существует:\n{out.name}\n\nЗаменить?"):
            return
        try:
            build_kp(self.invoice, meta, self.s.values, self.s.images(), out, self.s.blocks_dir)
        except PermissionError:
            error(self, f"Не удалось записать файл — возможно, он открыт в Excel:\n{out}")
            return
        except Exception as e:  # noqa: BLE001
            error(self, f"Ошибка при создании КП:\n{e}")
            return
        if number == str(self.s.next_number()):
            self.s.commit_number(int(number))  # номер был из счётчика — сдвигаем счётчик

        if self.tg_pdf.isChecked():
            self.btn_make.setEnabled(False)
            self.btn_make.setText("Сохраняю PDF…")
            run_in_background(lambda: export_pdf(out), lambda pdf, err: self._done(out, pdf, err))
        else:
            self._done(out, None, None)

    def _done(self, xlsx: Path, pdf: Path | None, err: Exception | None):
        self.btn_make.setEnabled(True)
        self.btn_make.setText("Сформировать КП  →")
        if err:
            warn(self, "КП в Excel создано, но PDF сохранить не удалось "
                       f"(нужен установленный Microsoft Excel):\n{err}")
        if self.on_created:
            self.on_created()
        DoneDialog(self, xlsx, pdf).exec()

    def refresh(self):
        self.tg_pdf.set_value(bool(self.s["also_pdf"]))


class DoneDialog(QDialog):
    def __init__(self, parent, xlsx: Path, pdf: Path | None):
        super().__init__(parent)
        self.setWindowTitle("КП готово")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(6)
        lay.addWidget(label("✔  Коммерческое предложение создано", name="success"))
        lay.addWidget(label(xlsx.name, muted=True, wrap=True))
        lay.addSpacing(14)
        row = [button("Открыть в Excel", lambda: open_path(xlsx, self), primary=True)]
        if pdf:
            row.append(button("Открыть PDF", lambda: open_path(pdf, self)))
        row += [button("Папка", lambda: open_path(xlsx.parent, self)), "stretch", button("Закрыть", self.accept)]
        lay.addLayout(hbox(*row))
        self.setMinimumWidth(520)
