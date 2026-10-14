"""Страница «Новое КП»: счёт -> данные КП -> файл."""
from __future__ import annotations

import threading
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from core.invoice_parser import Invoice, InvoiceError, parse_invoice
from core.kp_builder import KPMeta, build_kp, export_pdf, safe_filename
from core.settings_store import APP_NAME, Settings
from ui import theme as T
from ui.widgets import Card, Dialog, open_path, page_header, primary_button, secondary_button


def money(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


class NewKPPage(ctk.CTkFrame):
    def __init__(self, master, settings: Settings, on_created=None):
        super().__init__(master, fg_color="transparent")
        self.s = settings
        self.on_created = on_created
        self.invoice: Invoice | None = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        page_header(self, "Новое коммерческое предложение",
                    "Выберите счёт на оплату — данные перенесутся в КП автоматически").grid(
            row=0, column=0, sticky="ew", pady=(0, 16))

        # --- 1. Счёт
        c1 = Card(self)
        c1.grid(row=1, column=0, sticky="ew")
        c1.columnconfigure(1, weight=1)
        primary_button(c1, "📄  Выбрать счёт на оплату", self.choose_invoice, width=240, height=44).grid(
            row=0, column=0, padx=20, pady=16)
        info = ctk.CTkFrame(c1, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", padx=(0, 20))
        self.lbl_invoice = ctk.CTkLabel(info, text="Счёт не выбран", font=T.font(14, "bold"),
                                        text_color=T.TEXT, anchor="w")
        self.lbl_invoice.pack(anchor="w")
        self.lbl_file = ctk.CTkLabel(info, text="Файл Excel (.xlsx / .xls), выгруженный из 1С",
                                     font=T.font(12), text_color=T.MUTED, anchor="w")
        self.lbl_file.pack(anchor="w")

        # --- 2. Данные КП
        c2 = Card(self, "Данные КП")
        c2.grid(row=2, column=0, sticky="ew", pady=12)
        form = ctk.CTkFrame(c2, fg_color="transparent")
        form.grid(row=c2.body_row, column=0, sticky="ew", padx=20, pady=(8, 16))
        form.columnconfigure(1, weight=1)
        self.var_buyer = ctk.StringVar()
        self.var_details = ctk.StringVar()
        self.var_number = ctk.StringVar()
        self.var_date = ctk.StringVar(value=date.today().strftime("%d.%m.%Y"))
        self.var_pdf = ctk.BooleanVar(value=bool(self.s["also_pdf"]))

        def label(text, r, c=0):
            ctk.CTkLabel(form, text=text, font=T.font(13), text_color=T.MUTED, anchor="w").grid(
                row=r, column=c, sticky="w", padx=(0, 12), pady=4)

        label("Кому", 0)
        ctk.CTkEntry(form, textvariable=self.var_buyer, height=34, font=T.font(13)).grid(
            row=0, column=1, columnspan=5, sticky="ew", pady=4)
        label("Реквизиты", 1)
        ctk.CTkEntry(form, textvariable=self.var_details, height=34, font=T.font(13)).grid(
            row=1, column=1, columnspan=5, sticky="ew", pady=4)
        label("№ КП", 2)
        row = ctk.CTkFrame(form, fg_color="transparent")
        row.grid(row=2, column=1, columnspan=5, sticky="ew", pady=4)
        ctk.CTkEntry(row, textvariable=self.var_number, width=90, height=34, font=T.font(13)).pack(side="left")
        ctk.CTkLabel(row, text="Дата", font=T.font(13), text_color=T.MUTED).pack(side="left", padx=(24, 12))
        ctk.CTkEntry(row, textvariable=self.var_date, width=120, height=34, font=T.font(13)).pack(side="left")
        ctk.CTkSwitch(row, text="Сохранить также в PDF", variable=self.var_pdf, font=T.font(13),
                      progress_color=T.BRAND).pack(side="right")

        # --- 3. Позиции
        c3 = Card(self, "Позиции")
        c3.grid(row=3, column=0, sticky="nsew")
        c3.rowconfigure(c3.body_row, weight=1)
        holder = ctk.CTkFrame(c3, fg_color="transparent")
        holder.grid(row=c3.body_row, column=0, sticky="nsew", padx=20, pady=(8, 16))
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        cols = ("no", "name", "qty", "unit", "price", "total")
        self.tree = ttk.Treeview(holder, columns=cols, show="headings", style="KP.Treeview", height=6)
        for c, title, w, anchor in [("no", "№", 40, "center"), ("name", "Наименование", 380, "w"),
                                    ("qty", "Кол-во", 70, "center"), ("unit", "Ед.", 50, "center"),
                                    ("price", "Цена", 110, "e"), ("total", "Сумма", 120, "e")]:
            self.tree.heading(c, text=title, anchor=anchor)
            self.tree.column(c, width=w, minwidth=w if c != "name" else 150, anchor=anchor, stretch=(c == "name"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ctk.CTkScrollbar(holder, command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        self.empty = ctk.CTkLabel(holder, text="Здесь появятся позиции из счёта", font=T.font(13),
                                  text_color=T.MUTED)
        self.empty.place(relx=0.5, rely=0.55, anchor="center")

        # --- Итог
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        totals = ctk.CTkFrame(bar, fg_color="transparent")
        totals.pack(side="left")
        self.lbl_total = ctk.CTkLabel(totals, text="", font=T.font(20, "bold"), text_color=T.TEXT, anchor="w")
        self.lbl_total.pack(anchor="w")
        self.lbl_vat = ctk.CTkLabel(totals, text="", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.lbl_vat.pack(anchor="w")
        self.btn_make = primary_button(bar, "Сформировать КП  →", self.make_kp, width=230, height=48,
                                       state="disabled")
        self.btn_make.pack(side="right")

    # ------------------------------------------------------------------
    def choose_invoice(self):
        path = filedialog.askopenfilename(
            title="Выберите счёт на оплату",
            filetypes=[("Excel", "*.xlsx *.xlsm *.xls"), ("Все файлы", "*.*")],
            initialdir=str(Path.home() / "Desktop"),
        )
        if path:
            self.load_invoice(path)

    def load_invoice(self, path: str):
        try:
            inv = parse_invoice(path)
        except InvoiceError as e:
            messagebox.showerror(APP_NAME, str(e))
            return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP_NAME, f"Не удалось прочитать счёт:\n{e}")
            return
        self.invoice = inv
        self.lbl_invoice.configure(text=f"Счёт на оплату № {inv.number}"
                                        + (f" от {inv.date:%d.%m.%Y}" if inv.date else ""))
        self.lbl_file.configure(text=Path(path).name)
        # что брать из счёта — настраивается в «Шаблон КП» → «Из счёта»
        s = self.s
        self.var_buyer.set(inv.buyer if s["fill_buyer"] else "")
        self.var_details.set(inv.buyer_details if s["fill_buyer_details"] else "")
        # № КП = № счёта; если выключено или в счёте номера нет — свой счётчик
        self.var_number.set(inv.number if s["fill_number"] and inv.number else str(s.next_number()))
        kp_date = inv.date if s["fill_date"] and inv.date else date.today()
        self.var_date.set(kp_date.strftime("%d.%m.%Y"))
        self.tree.delete(*self.tree.get_children())
        for i, it in enumerate(inv.items, 1):
            qty = int(it.qty) if float(it.qty).is_integer() else it.qty
            self.tree.insert("", "end", values=(i, it.name, qty, it.unit, money(it.price), money(it.total)))
        self.empty.place_forget()
        self.lbl_total.configure(text=f"{money(inv.total)} KZT")
        vat = f"  ·  в т.ч. НДС {money(inv.vat)}" if inv.vat is not None else ""
        self.lbl_vat.configure(text=f"Позиций: {len(inv.items)}{vat}")
        self.btn_make.configure(state="normal")

    def make_kp(self):
        if not self.invoice:
            return
        number = self.var_number.get().strip()
        try:
            kp_date = datetime.strptime(self.var_date.get().strip(), "%d.%m.%Y").date()
        except ValueError:
            messagebox.showerror(APP_NAME, "Проверьте дату КП (ДД.ММ.ГГГГ).")
            return
        if not number:
            messagebox.showerror(APP_NAME, "Укажите № КП.")
            return
        meta = KPMeta(number, kp_date, self.var_buyer.get().strip(), self.var_details.get().strip())
        short_buyer = meta.buyer.replace("Товарищество с ограниченной ответственностью", "ТОО")
        name = f"КП № {number} от {kp_date:%d.%m.%Y}" + (f" - {short_buyer}" if short_buyer else "")
        out = Path(self.s["output_dir"]) / f"{safe_filename(name)}.xlsx"
        if out.exists() and not messagebox.askyesno(APP_NAME, f"Файл уже существует:\n{out.name}\n\nЗаменить?"):
            return
        try:
            build_kp(self.invoice, meta, self.s.values, self.s.images(), out)
        except PermissionError:
            messagebox.showerror(APP_NAME, f"Не удалось записать файл — возможно, он открыт в Excel:\n{out}")
            return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP_NAME, f"Ошибка при создании КП:\n{e}")
            return
        if number == str(self.s.next_number()):
            self.s.commit_number(int(number))  # номер был из счётчика — сдвигаем счётчик

        if self.var_pdf.get():
            self.btn_make.configure(state="disabled", text="Сохраняю PDF…")
            threading.Thread(target=self._pdf_worker, args=(out,), daemon=True).start()
        else:
            self._done(out, None, None)

    def _pdf_worker(self, xlsx: Path):
        try:
            pdf, err = export_pdf(xlsx), None
        except Exception as e:  # noqa: BLE001
            pdf, err = None, e
        self.after(0, self._done, xlsx, pdf, err)

    def _done(self, xlsx: Path, pdf: Path | None, err: Exception | None):
        self.btn_make.configure(state="normal", text="Сформировать КП  →")
        if err:
            messagebox.showwarning(APP_NAME, "КП в Excel создано, но PDF сохранить не удалось "
                                             f"(нужен установленный Microsoft Excel):\n{err}")
        if self.on_created:
            self.on_created()
        DoneDialog(self, xlsx, pdf)

    def refresh(self):
        self.var_pdf.set(bool(self.s["also_pdf"]))


class DoneDialog(Dialog):
    def __init__(self, master, xlsx: Path, pdf: Path | None):
        super().__init__(master, "КП готово", 520, 210)
        ctk.CTkLabel(self, text="✔  Коммерческое предложение создано", font=T.font(17, "bold"),
                     text_color=T.BRAND_BRIGHT).pack(anchor="w", padx=24, pady=(24, 2))
        ctk.CTkLabel(self, text=xlsx.name, font=T.font(12), text_color=T.MUTED, wraplength=470,
                     justify="left").pack(anchor="w", padx=24)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=24)
        primary_button(row, "Открыть в Excel", lambda: open_path(xlsx), width=150, height=38).pack(side="left")
        if pdf:
            secondary_button(row, "Открыть PDF", lambda: open_path(pdf), width=120).pack(side="left", padx=8)
        secondary_button(row, "Папка", lambda: open_path(xlsx.parent), width=80).pack(side="left")
        secondary_button(row, "Закрыть", self.destroy, width=90).pack(side="right")
