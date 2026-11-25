#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_card.py: что нужно карточке персонажа HS2 (например, Main.png).

Карточка = PNG + данные в конце. Sideloader хранит там GUID модов, чьи ассеты использует
персонаж (причёска, одежда, текстуры), а другие плагины пишут свои блоки (ExtendedSave).
Скрипт:
  1) находит GUID модов и сопоставляет их с zipmods.csv (его делает scan_mohs2.py);
  2) показывает, какие плагины записали данные в карточку (com.*, moreAccessories и т.п.);
  3) сообщает, пуст ли список ресурсов Sideloader (тогда персонаж на ассетах самой игры).

Запуск:
    python tools/mohs2/audit_card.py "<путь>\\Main.png" <путь>\\zipmods.csv
    python tools/mohs2/audit_card.py "<путь>\\Main.png" <путь>\\zipmods.csv --out main_deps

Где карточка: в Mod Organizer новые файлы игры попадают в MO\\overwrite\\UserData\\chara\\female\\.
Результат: <out>.md (отчёт) и <out>.csv (таблица модов). Только стандартная библиотека.
"""
import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict

RUN = re.compile(rb"[\x20-\x7e]{4,}")
PLUGIN_ID = re.compile(rb"(?:com|org|net)\.[A-Za-z0-9_.\-]{4,}")
PNG_SIG = b"\x89PNG\r\n\x1a\n"
UAR = b"com.bepis.sideloader.universalautoresolver"


def human(n):
    n = float(n)
    for u in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024:
            return f"{n:.0f} {u}" if u == "Б" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} ТБ"


def load_guids(path):
    by_guid = defaultdict(list)
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            g = (row.get("guid") or "").strip()
            if len(g) >= 4:
                by_guid[g].append(row)
    return by_guid


def split_card(data):
    """Возвращает (данные после картинки, есть ли PNG-сигнатура)."""
    if not data.startswith(PNG_SIG):
        return data, False
    iend = data.rfind(b"IEND")
    return (data[iend + 8:] if iend >= 0 else data), True


def find_hits(payload, by_guid):
    """Токены ASCII; перед строкой msgpack стоит служебный байт, поэтому пробуем срезать 0-2 символа по краям."""
    found = Counter()
    for m in RUN.finditer(payload):
        tok = m.group(0).decode("ascii", "ignore")
        seen = set()
        for a in range(3):
            for b in range(3):
                s = tok[a:len(tok) - b] if b else tok[a:]
                if len(s) >= 4 and s in by_guid and s not in seen:
                    seen.add(s)
                    found[s] += 1
    return found


def plugin_ids(payload):
    """Идентификаторы плагинов, записавших свои данные (com.bepis..., com.fairbair...)."""
    ids = Counter(m.group(0).decode("ascii", "ignore") for m in PLUGIN_ID.finditer(payload))
    if b"moreAccessories" in payload:
        ids["moreAccessories (MoreAccessories)"] += 1
    return ids


def uar_state(payload):
    """'empty' - блок Sideloader есть, ресурсов нет; 'filled' - есть ресурсы; 'absent' - блока нет."""
    i = payload.find(UAR)
    if i < 0:
        return "absent"
    seg = payload[i + len(UAR): i + len(UAR) + 40]
    return "empty" if b"\xa4info\x90" in seg else "filled"


def build_report(card_name, tail, rows, ids, uar):
    L = [f"# Зависимости карточки {card_name}", ""]
    L.append(f"Данные после картинки: {human(tail)}. Модов найдено по GUID: {len(rows)}.")
    if uar == "empty":
        L += ["", "Блок Sideloader в карточке есть, но список ресурсов пуст: персонаж собран из ассетов "
              "самой игры, ни один мод (.zipmod) ему не нужен."]
    elif uar == "absent":
        L += ["", "Блока Sideloader в карточке нет: персонаж без модовых ассетов либо карточка нестандартная."]
    if rows:
        authors = Counter(r["author"] or "(нет автора)" for r in rows)
        L += ["", "## Авторы (условия использования нужно проверить)"]
        L += [f"- {au}: {c} мод." for au, c in authors.most_common()]
        L += ["", "## Моды"]
        for r in rows:
            L.append(f"- [{r['author'] or '?'}] {r['name'] or r['guid']}  (guid: {r['guid']}, "
                     f"{human(r['size'] or 0)})  {r['path']}")
    if ids:
        L += ["", "## Плагины, записавшие данные в карточку (ExtendedSave)",
              "Это не ассеты, а настройки (физика, аксессуары и т.п.), но сами плагины нужны для точной загрузки."]
        L += [f"- {k}" for k in sorted(ids)]
    L += ["", "Ассеты самой игры (стандартные лицо, тело, волосы) GUID не имеют. Они принадлежат Illusion: "
          "см. docs/05_LICENSES_AND_SAFETY.md."]
    return L


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Аудит зависимостей карточки персонажа HS2")
    ap.add_argument("card", help="путь к карточке .png")
    ap.add_argument("zipmods", help="zipmods.csv из scan_mohs2.py")
    ap.add_argument("--out", default="main_deps", help="имя выходных файлов без расширения")
    a = ap.parse_args()

    if not os.path.isfile(a.card):
        print(f"Карточка не найдена: {a.card}")
        sys.exit(1)
    if not os.path.isfile(a.zipmods):
        print(f"zipmods.csv не найден: {a.zipmods}\nЕго создаёт tools/mohs2/scan_mohs2.py (папка MOHS2_scan).")
        sys.exit(1)
    data = open(a.card, "rb").read()
    payload, is_png = split_card(data)
    if not is_png:
        print("Это не PNG. Нужна именно карточка персонажа (.png).")
        sys.exit(1)

    by_guid = load_guids(a.zipmods)
    hits = find_hits(payload, by_guid)
    rows = []
    for g, cnt in hits.items():
        for r in by_guid[g]:
            rows.append({"guid": g, "mentions": cnt, "author": r.get("author", ""), "name": r.get("name", ""),
                         "version": r.get("version", ""), "size": r.get("size", ""), "path": r.get("path", "")})
    rows.sort(key=lambda r: (r["author"].lower(), r["name"].lower()))

    with open(a.out + ".csv", "w", encoding="utf-8-sig", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=["guid", "mentions", "author", "name", "version", "size", "path"])
        wr.writeheader()
        wr.writerows(rows)
    report = build_report(os.path.basename(a.card), len(payload), rows, plugin_ids(payload), uar_state(payload))
    with open(a.out + ".md", "w", encoding="utf-8-sig") as fh:
        fh.write("\n".join(report) + "\n")
    print(f"Модов найдено: {len(rows)}. Отчёт: {a.out}.md и {a.out}.csv")


if __name__ == "__main__":
    main()
