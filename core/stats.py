"""Статистика сформированных КП в Google Таблице.

Программа отправляет строку о каждом КП на веб-приложение Google Apps Script, привязанное
к таблице владельца (код скрипта — APPS_SCRIPT ниже). Скрипт раскладывает строки по листам
сотрудников и обновляет лист «Сводка».

- Ссылка на веб-приложение и секретный ключ хранятся в настройках (переносятся .pbsettings),
  имя сотрудника — только на этом компьютере (state.json).
- Если сети нет, записи копятся в очереди (data/stats_queue.json) и уходят позже.
- У каждой записи свой id: повторная отправка не создаёт дублей.
"""
from __future__ import annotations

import getpass
import json
import os
import re
import secrets
import socket
import threading
import urllib.parse
import urllib.request
import uuid
from datetime import datetime

from core.settings_store import Settings
from version import __version__

TIMEOUT = 20
_lock = threading.Lock()


class StatsError(Exception):
    pass


def new_token() -> str:
    return secrets.token_urlsafe(24)


def default_employee() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return os.environ.get("USERNAME", "")


def employee(s: Settings) -> str:
    return (s.get_state("employee_name") or "").strip()


def enabled(s: Settings) -> bool:
    return bool(s["stats_enabled"] and s["stats_url"].strip() and s["stats_token"].strip())


# ---------------------------------------------------------------- очередь
def _queue_file(s: Settings):
    return s.dir / "stats_queue.json"


def _load_queue(s: Settings) -> list[dict]:
    try:
        q = json.loads(_queue_file(s).read_text(encoding="utf-8"))
        return q if isinstance(q, list) else []
    except (OSError, ValueError):
        return []


def _save_queue(s: Settings, q: list[dict]):
    _queue_file(s).write_text(json.dumps(q, ensure_ascii=False), encoding="utf-8")


def queued(s: Settings) -> int:
    return len(_load_queue(s))


def record(s: Settings, kp_number: str, buyer: str, total: float, items: int):
    """Поставить в очередь запись о сформированном КП (отправка — flush())."""
    row = {
        "id": uuid.uuid4().hex,
        "time": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "employee": employee(s) or default_employee(),
        "computer": socket.gethostname(),
        "kp": str(kp_number),
        "buyer": buyer,
        "total": round(float(total), 2),
        "items": int(items),
        "version": __version__,
        "company": s["company_name"],
    }
    with _lock:
        q = _load_queue(s)
        q.append(row)
        _save_queue(s, q[-5000:])  # не даём очереди расти бесконечно


# ---------------------------------------------------------------- связь с Google
def _post(url: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    # Apps Script отвечает переадресацией на googleusercontent.com — urllib сам переходит по ней GET-запросом
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 — адрес задан владельцем
        return json.loads(r.read().decode("utf-8"))


def ping(url: str, token: str) -> str:
    """Проверить соединение: вернёт название таблицы или бросит StatsError с понятным текстом."""
    if not url.strip().startswith("https://script.google.com/"):
        raise StatsError("Ссылка должна начинаться с https://script.google.com/ — это адрес веб-приложения скрипта.")
    try:
        q = urllib.parse.urlencode({"ping": "1", "token": token})
        with urllib.request.urlopen(f"{url.strip()}?{q}", timeout=TIMEOUT) as r:  # noqa: S310
            body = r.read().decode("utf-8")
    except Exception as e:  # noqa: BLE001
        raise StatsError(f"Нет связи с Google:\n{e}") from e
    try:
        res = json.loads(body)
    except ValueError as e:
        raise StatsError("Google ответил не так, как ожидалось. Проверьте, что веб-приложение опубликовано "
                         "с доступом «Все» (Anyone).") from e
    if not res.get("ok"):
        raise StatsError(res.get("error") or "Скрипт отклонил запрос.")
    return res.get("sheet", "")


def flush(s: Settings) -> tuple[int, str | None]:
    """Отправить очередь. Возвращает (сколько отправлено, ошибка или None)."""
    if not enabled(s):
        return 0, None
    with _lock:
        q = _load_queue(s)
    if not q:
        return 0, None
    sent = 0
    for i in range(0, len(q), 50):
        batch = q[i:i + 50]
        try:
            res = _post(s["stats_url"].strip(), {"token": s["stats_token"].strip(), "rows": batch})
        except Exception as e:  # noqa: BLE001
            return sent, f"Нет связи с Google: {e}"
        if not res.get("ok"):
            return sent, res.get("error") or "Скрипт отклонил запрос."
        done = {r["id"] for r in batch}
        with _lock:
            _save_queue(s, [r for r in _load_queue(s) if r["id"] not in done])
        sent += len(batch)
    return sent, None


def flush_in_background(s: Settings, on_done=None):
    def run():
        res = flush(s)
        if on_done:
            on_done(*res)
    threading.Thread(target=run, daemon=True).start()


# ---------------------------------------------------------------- код скрипта для таблицы
APPS_SCRIPT = r"""/**
 * Помощник Бухгалтера — статистика КП.
 * Вставьте этот код в редактор скриптов таблицы (Расширения → Apps Script),
 * сохраните и опубликуйте: Развернуть → Новое развертывание → Веб-приложение,
 * «Выполнять как: Я», «У кого есть доступ: Все».
 */
const TOKEN = "__TOKEN__";           // секретный ключ — такой же, как в программе
const SHEET_ID = "__SHEET_ID__";     // код таблицы (из её адреса); в режиме веб-приложения «текущей» таблицы нет

function ss_() {
  return SHEET_ID ? SpreadsheetApp.openById(SHEET_ID) : SpreadsheetApp.getActive();
}
const SUMMARY = "Сводка";
const HEADERS = ["Дата и время", "№ КП", "Покупатель", "Сумма, ₸", "Позиций", "Компьютер", "Версия", "id"];

function doGet(e) {
  const p = (e && e.parameter) || {};
  if (p.token !== TOKEN) return json_({ ok: false, error: "Неверный ключ." });
  return json_({ ok: true, sheet: ss_().getName() });
}

function doPost(e) {
  let data;
  try { data = JSON.parse(e.postData.contents); } catch (err) { return json_({ ok: false, error: "Неверный запрос." }); }
  if (data.token !== TOKEN) return json_({ ok: false, error: "Неверный ключ." });
  const rows = Array.isArray(data.rows) ? data.rows.slice(0, 200) : [];
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const ss = ss_();
    let saved = 0;
    rows.forEach(function (r) {
      const sh = employeeSheet_(ss, String(r.employee || "Без имени"));
      const id = String(r.id || "");
      if (id && sh.getRange("H:H").createTextFinder(id).matchEntireCell(true).findNext()) return; // уже есть
      sh.appendRow([String(r.time || ""), String(r.kp || ""), String(r.buyer || ""), Number(r.total) || 0,
                    Number(r.items) || 0, String(r.computer || ""), String(r.version || ""), id]);
      saved++;
    });
    if (saved) rebuildSummary_(ss);
    return json_({ ok: true, saved: saved });
  } finally {
    lock.releaseLock();
  }
}

function employeeSheet_(ss, name) {
  const title = name.replace(/[\[\]\*\?\/\\:]/g, " ").trim().slice(0, 90) || "Без имени";
  let sh = ss.getSheetByName(title);
  if (sh) return sh;
  sh = ss.insertSheet(title);
  sh.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]).setFontWeight("bold")
    .setBackground("#284F0D").setFontColor("#FFFFFF");
  sh.setFrozenRows(1);
  sh.getRange("A:B").setNumberFormat("@");   // дата и № КП — как текст, без автопреобразования
  sh.getRange("D:D").setNumberFormat("#,##0.00");
  sh.setColumnWidth(1, 150); sh.setColumnWidth(2, 90); sh.setColumnWidth(3, 340);
  sh.setColumnWidth(4, 120); sh.setColumnWidth(5, 80); sh.setColumnWidth(6, 140);
  sh.hideColumns(8);
  return sh;
}

function rebuildSummary_(ss) {
  let sum = ss.getSheetByName(SUMMARY);
  if (!sum) { sum = ss.insertSheet(SUMMARY, 0); }
  sum.clear();
  const now = new Date();
  const ym = Utilities.formatDate(now, Session.getScriptTimeZone(), "MM.yyyy");
  const people = [];
  let totalCount = 0, totalSum = 0, monthCount = 0, monthSum = 0;
  ss.getSheets().forEach(function (sh) {
    if (sh.getName() === SUMMARY || sh.getLastRow() < 2) return;
    const vals = sh.getRange(2, 1, sh.getLastRow() - 1, 4).getValues();
    let c = 0, s = 0, mc = 0, ms = 0, last = "";
    vals.forEach(function (v) {
      const amount = Number(v[3]) || 0;
      const when = v[0] instanceof Date
        ? Utilities.formatDate(v[0], Session.getScriptTimeZone(), "dd.MM.yyyy HH:mm:ss") : String(v[0]);
      c++; s += amount; last = when;
      if (when.slice(3, 10) === ym) { mc++; ms += amount; }
    });
    people.push([sh.getName(), c, s, mc, ms, last]);
    totalCount += c; totalSum += s; monthCount += mc; monthSum += ms;
  });
  people.sort(function (a, b) { return b[1] - a[1]; });

  sum.getRange("A1").setValue("Статистика коммерческих предложений").setFontSize(16).setFontWeight("bold");
  sum.getRange("A2").setValue("Обновлено: " + Utilities.formatDate(now, Session.getScriptTimeZone(), "dd.MM.yyyy HH:mm"))
    .setFontColor("#6B7280");
  sum.getRange("A4:B7").setValues([
    ["Всего КП", totalCount], ["Общая сумма КП, ₸", totalSum],
    ["КП в этом месяце", monthCount], ["Сумма в этом месяце, ₸", monthSum]]);
  sum.getRange("A4:A7").setFontWeight("bold");
  sum.getRange("B5").setNumberFormat("#,##0.00"); sum.getRange("B7").setNumberFormat("#,##0.00");
  const head = [["Сотрудник", "КП всего", "Сумма всего, ₸", "КП в этом месяце", "Сумма в этом месяце, ₸", "Последнее КП"]];
  sum.getRange(9, 1, 1, 6).setValues(head).setFontWeight("bold").setBackground("#284F0D").setFontColor("#FFFFFF");
  if (people.length) {
    sum.getRange(10, 1, people.length, 6).setValues(people);
    sum.getRange(10, 3, people.length, 1).setNumberFormat("#,##0.00");
    sum.getRange(10, 5, people.length, 1).setNumberFormat("#,##0.00");
  }
  sum.setColumnWidth(1, 220); sum.setColumnWidths(2, 4, 150); sum.setColumnWidth(6, 170);
  // пустой лист, который Google создаёт в новой таблице, больше не нужен
  ["Лист1", "Sheet1"].forEach(function (n) {
    const extra = ss.getSheetByName(n);
    if (extra && extra.getLastRow() === 0 && ss.getSheets().length > 1) ss.deleteSheet(extra);
  });
  sum.setFrozenRows(0);
  ss.setActiveSheet(sum); ss.moveActiveSheet(1);
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
"""


def sheet_id(url_or_id: str) -> str:
    """Код таблицы из её адреса (https://docs.google.com/spreadsheets/d/<код>/edit…) или сам код."""
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]{20,})", url_or_id or "")
    if m:
        return m.group(1)
    t = (url_or_id or "").strip()
    return t if re.fullmatch(r"[A-Za-z0-9_-]{20,}", t) else ""


def apps_script_code(token: str, sheet: str = "") -> str:
    return APPS_SCRIPT.replace("__TOKEN__", token).replace("__SHEET_ID__", sheet_id(sheet))
