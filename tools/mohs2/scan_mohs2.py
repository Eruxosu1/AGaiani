#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_mohs2.py: инвентаризация папки MOHS2 (сборка Honey Select 2 с модами).

Ничего не меняет и не распаковывает: только читает имена, размеры и (для .zipmod/.zip)
оглавление архива и manifest.xml. Только стандартная библиотека Python 3.8+.

Запуск:
    python scan_mohs2.py
    python scan_mohs2.py "E:\\uTorria\\Downloads\\MOHS2" --out "E:\\uTorria\\Downloads\\MOHS2_scan"

Результат (папка --out, по умолчанию рядом со скриптом: MOHS2_scan):
    tree.txt      дерево папок (большие папки свёрнуты в «… ещё N файлов: .ext×N»)
    summary.md    сводка: что где лежит, плагины, моды, лицензии, находки по ключевым словам
    files.csv     полный список файлов (путь, размер, дата)
    zipmods.csv   список .zipmod/.zip с данными из manifest.xml (имя, автор, версия, guid)

Дальше пришлите summary.md и tree.txt (если больше нескольких МБ, заархивируйте в zip).
"""
import argparse
import csv
import os
import re
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime

DEFAULT_ROOT = r"E:\uTorria\Downloads\MOHS2"
sys.setrecursionlimit(10000)


# ----------------------------------------------------------------- утилиты
def human(n):
    n = float(n)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} ТБ"


def lp(p):
    """Длинные пути Windows (>260 символов): префикс \\\\?\\."""
    if os.name == "nt":
        p = os.path.abspath(p)
        if not p.startswith("\\\\?\\"):
            if p.startswith("\\\\"):
                return "\\\\?\\UNC\\" + p[2:]
            return "\\\\?\\" + p
    return p


def ext_of(name):
    return os.path.splitext(name)[1].lower() or "(без расширения)"


def top_exts(counter, n=6):
    return ", ".join(f"{e}x{c}" for e, c in counter.most_common(n)) or "пусто"


def is_dir(entry):
    try:
        return entry.is_dir(follow_symlinks=False)
    except OSError:
        return False


# ------------------------------------------------------------------ сканер
class Node:
    __slots__ = ("name", "is_dir", "size", "n_files", "n_dirs", "children", "exts", "err")

    def __init__(self, name, is_dir_, size=0):
        self.name = name
        self.is_dir = is_dir_
        self.size = size
        self.n_files = 0 if is_dir_ else 1
        self.n_dirs = 0
        self.children = []
        self.exts = Counter()
        self.err = None


class Scan:
    def __init__(self):
        self.files = []  # (относительный путь через /, размер, mtime)
        self.errors = []
        self.t0 = time.time()


def scan_dir(path, rel, S):
    node = Node(os.path.basename(path.rstrip("\\/")) or path, True)
    try:
        with os.scandir(lp(path)) as it:
            entries = list(it)
    except OSError as e:
        node.err = f"{type(e).__name__}: {e}"
        S.errors.append((rel or ".", node.err))
        return node
    entries.sort(key=lambda e: (not is_dir(e), e.name.lower()))
    for e in entries:
        r = f"{rel}/{e.name}" if rel else e.name
        try:
            if is_dir(e):
                ch = scan_dir(e.path, r, S)
                node.n_dirs += 1 + ch.n_dirs
                node.exts.update(ch.exts)
            else:
                st = e.stat(follow_symlinks=False)
                ch = Node(e.name, False, st.st_size)
                node.exts[ext_of(e.name)] += 1
                S.files.append((r, st.st_size, st.st_mtime))
                if len(S.files) % 5000 == 0:
                    print(f"  ... {len(S.files)} файлов, {time.time() - S.t0:.0f} с", flush=True)
        except OSError as err:
            S.errors.append((r, f"{type(err).__name__}: {err}"))
            continue
        node.children.append(ch)
        node.size += ch.size
        node.n_files += ch.n_files
    return node


# ------------------------------------------------------------ дерево (текст)
def render(node, out, prefix, depth, a):
    dirs = [c for c in node.children if c.is_dir]
    files = [c for c in node.children if not c.is_dir]
    items = [("d", d) for d in dirs[: a.max_dirs]]
    if len(dirs) > a.max_dirs:
        items.append(("rd", dirs[a.max_dirs:]))
    items += [("f", f) for f in files[: a.max_files]]
    if len(files) > a.max_files:
        items.append(("rf", files[a.max_files:]))
    for i, (kind, obj) in enumerate(items):
        last = i == len(items) - 1
        br = "└── " if last else "├── "
        nxt = prefix + ("    " if last else "│   ")
        if kind == "d":
            info = f"[{obj.n_files} файл., {human(obj.size)}]"
            if obj.err:
                info += f"  !! {obj.err}"
            out.append(f"{prefix}{br}{obj.name}/  {info}")
            if obj.children and depth + 1 >= a.depth:
                out.append(f"{nxt}└── … глубже {a.depth} уровней: {obj.n_dirs} папок, {top_exts(obj.exts)}")
            else:
                render(obj, out, nxt, depth + 1, a)
        elif kind == "f":
            out.append(f"{prefix}{br}{obj.name}  ({human(obj.size)})")
        elif kind == "rd":
            out.append(
                f"{prefix}{br}… ещё {len(obj)} папок ({sum(x.n_files for x in obj)} файл., "
                f"{human(sum(x.size for x in obj))})"
            )
        else:
            cnt = Counter(ext_of(x.name) for x in obj)
            out.append(f"{prefix}{br}… ещё {len(obj)} файлов ({human(sum(x.size for x in obj))}): {top_exts(cnt)}")


# ------------------------------------------------------------- анализ файлов
TEXT_EXT = {".dll", ".zipmod", ".zip", ".exe", ".py", ".lua", ".cs", ".bat", ".ps1", ".json",
            ".cfg", ".ini", ".xml", ".txt", ".md", ".yaml", ".yml", ".toml"}
CATS = [
    ("Экспорт и форматы (FBX, glTF, VRM, OBJ, Blender)",
     r"export|fbx|gltf|glb|vrm|collada|blender|(?<![a-z])obj(?![a-z])"),
    ("Мимика, морфы, губы, эмоции",
     r"blendshape|morph|expression|lip[ _-]?sync|mouth|emotion|facial"),
    ("Анимация, позы, таймлайн, кости",
     r"timeline|hspe|kkpe|pose|animation|(?<![a-z])ik(?![a-z])|dynamicbone|mocap|(?<![a-z])bvh(?![a-z])|skeleton|bone"),
    ("Внешнее управление (сеть, API, скрипты, VMC/OSC)",
     r"websocket|socket|http|remote|(?<![a-z])api(?![a-z])|python|(?<![a-z])lua(?![a-z])|script|"
     r"(?<![a-z])(vmc|osc)(?![a-z])|livelink|facetrack|openseeface|(?<![a-z])rpc(?![a-z])"),
    ("Захват картинки, прозрачный фон",
     r"screenshot|capture|transparent|alpha|chroma|spout|(?<![a-z])ndi(?![a-z])|(?<![a-z])obs(?![a-z])"),
]
CATS = [(t, re.compile(p, re.I)) for t, p in CATS]
DOC_RE = re.compile(r"licen[sc]e|readme|read[ _-]?me|terms|eula|copyright|credits|manual|"
                    r"лиценз|условия|правила|инструкц", re.I)
DOC_EXT = {".txt", ".md", ".pdf", ".html", ".htm", ".rtf", ".doc", ".docx"}


def read_archive(path):
    row = {"entries": 0, "name": "", "version": "", "author": "", "guid": "", "game": "",
           "desc": "", "top": "", "err": ""}
    keymap = {"name": "name", "version": "version", "author": "author", "guid": "guid",
              "game": "game", "description": "desc"}
    try:
        with zipfile.ZipFile(lp(path)) as z:
            names = z.namelist()
            row["entries"] = len(names)
            tops = Counter(n.split("/")[0] for n in names if n)
            row["top"] = ", ".join(f"{k}x{v}" for k, v in tops.most_common(4))
            man = [n for n in names if n.lower().endswith("manifest.xml")]
            if man:
                root = ET.fromstring(z.read(man[0])[:300_000])
                for el in root.iter():
                    tag = el.tag.split("}")[-1].lower()
                    if tag in keymap and el.text and not row[keymap[tag]]:
                        row[keymap[tag]] = " ".join(el.text.split())[:200]
    except (zipfile.BadZipFile, OSError, ET.ParseError, KeyError, RuntimeError, NotImplementedError) as e:
        row["err"] = type(e).__name__
    return row


def capped(lines, cap, title_note=""):
    if len(lines) <= cap:
        return lines
    return lines[:cap] + [f"… ещё {len(lines) - cap}{title_note}"]


def build_summary(root_path, root, S, zips, a):
    L = []
    w = L.append
    total = sum(f[1] for f in S.files)
    w(f"# Сводка по {root_path}")
    w(f"\nСканирование: {datetime.now():%Y-%m-%d %H:%M}, {time.time() - S.t0:.0f} с. "
      f"Файлов: {len(S.files)}, папок: {root.n_dirs}, размер: {human(total)}.")
    if S.errors:
        w(f"Ошибки доступа: {len(S.errors)} (первые: " + "; ".join(f"{p}: {m}" for p, m in S.errors[:5]) + ")")

    # корень
    w("\n## 1. Корень папки")
    for c in root.children:
        if c.is_dir:
            w(f"- {c.name}/  [{c.n_files} файл., {human(c.size)}]  {top_exts(c.exts, 4)}")
        else:
            w(f"- {c.name}  ({human(c.size)})")

    # крупные папки до 2 уровня
    w("\n## 2. Самые тяжёлые папки (до 2 уровней)")
    rows = []
    for c1 in root.children:
        if c1.is_dir:
            rows.append((c1.size, c1.name, c1))
            for c2 in c1.children:
                if c2.is_dir:
                    rows.append((c2.size, f"{c1.name}/{c2.name}", c2))
    for size, name, n in sorted(rows, key=lambda r: -r[0])[:50]:
        w(f"- {name}/  {human(size)}, {n.n_files} файл., {top_exts(n.exts, 4)}")

    # расширения
    w("\n## 3. Типы файлов (по объёму)")
    by_ext = Counter()
    cnt_ext = Counter()
    for rel, size, _ in S.files:
        e = ext_of(rel)
        by_ext[e] += size
        cnt_ext[e] += 1
    for e, size in by_ext.most_common(40):
        w(f"- {e}: {cnt_ext[e]} файл., {human(size)}")

    # крупнейшие файлы
    w("\n## 4. 40 самых больших файлов")
    for rel, size, _ in sorted(S.files, key=lambda f: -f[1])[:40]:
        w(f"- {rel}  ({human(size)})")

    # плагины
    plugins = [f for f in S.files if f[0].lower().endswith(".dll") and "bepinex/plugins" in f[0].lower()]
    w(f"\n## 5. Плагины BepInEx ({len(plugins)} .dll в BepInEx/plugins)")
    bep = any(c.is_dir and c.name.lower() == "bepinex" for c in root.children)
    w("BepInEx в корне: " + ("да" if bep else "НЕТ"))
    for rel, size, _ in capped(sorted(plugins), 600):
        w(f"- {rel}  ({human(size)})") if isinstance(rel, str) else w(f"- {rel}")

    # моды
    mods = [z for z in zips if z["path"].lower().endswith(".zipmod")]
    w(f"\n## 6. Моды .zipmod ({len(mods)})")
    if mods:
        authors = Counter(z["author"] or "(нет автора)" for z in mods)
        games = Counter(z["game"] or "(не указано)" for z in mods)
        w("Авторы (топ 15): " + ", ".join(f"{k} x{v}" for k, v in authors.most_common(15)))
        w("Игра в manifest: " + ", ".join(f"{k} x{v}" for k, v in games.most_common(6)))
        w("Полный список с guid: zipmods.csv")

    # находки
    w("\n## 7. Находки по ключевым словам в именах файлов и манифестах")
    cand = [f[0] for f in S.files if os.path.splitext(f[0])[1].lower() in TEXT_EXT]
    mod_text = [(z["path"], f"{z['name']} {z['desc']} {z['guid']}") for z in zips]
    for title, rx in CATS:
        hits = [p for p in cand if rx.search(os.path.basename(p))]
        hits += [f"{p}  (manifest: {t[:90]})" for p, t in mod_text
                 if rx.search(t) and not rx.search(os.path.basename(p))]
        w(f"\n### {title}: {len(hits)}")
        for h in capped(hits, 120):
            w(f"- {h}")

    # лицензии / readme
    docs = [f for f in S.files if os.path.splitext(f[0])[1].lower() in DOC_EXT
            and DOC_RE.search(os.path.basename(f[0]))]
    w(f"\n## 8. Лицензии, readme, условия ({len(docs)})")
    w("Эти файлы нужно прочитать до использования чего-либо из сборки в публичном проекте.")
    for rel, size, _ in capped(sorted(docs), 300):
        w(f"- {rel}  ({human(size)})") if isinstance(rel, str) else w(f"- {rel}")

    # персонажи, сцены
    w("\n## 9. Пользовательские данные")
    ud = {
        "карточки персонажей (UserData/chara/*.png)":
            sum(1 for f in S.files if re.search(r"(^|/)userdata/chara/.*\.png$", f[0], re.I)),
        "сцены Studio (UserData/Studio/*.png)":
            sum(1 for f in S.files if re.search(r"(^|/)userdata/studio/.*\.png$", f[0], re.I)),
        "файлы в UserData": sum(1 for f in S.files if re.search(r"(^|/)userdata/", f[0], re.I)),
        "файлы в abdata": sum(1 for f in S.files if re.search(r"(^|/)abdata/", f[0], re.I)),
    }
    for k, v in ud.items():
        w(f"- {k}: {v}")
    return L


# --------------------------------------------------------------------- main
def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Инвентаризация папки MOHS2")
    ap.add_argument("root", nargs="?", default=DEFAULT_ROOT, help="папка для сканирования")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "MOHS2_scan"))
    ap.add_argument("--depth", type=int, default=6, help="глубина дерева в tree.txt")
    ap.add_argument("--max-files", type=int, default=40, help="файлов на папку в дереве")
    ap.add_argument("--max-dirs", type=int, default=80, help="подпапок на папку в дереве")
    ap.add_argument("--no-csv", action="store_true", help="не писать files.csv")
    ap.add_argument("--no-zips", action="store_true", help="не читать архивы .zipmod/.zip")
    a = ap.parse_args()

    root_path = os.path.abspath(a.root)
    if not os.path.isdir(lp(root_path)):
        print(f"Папка не найдена: {root_path}")
        sys.exit(1)
    os.makedirs(a.out, exist_ok=True)

    print(f"Сканирую {root_path} ...", flush=True)
    S = Scan()
    root = scan_dir(root_path, "", S)
    print(f"Готово: {len(S.files)} файлов, {root.n_dirs} папок, {human(root.size)}", flush=True)

    zips = []
    if not a.no_zips:
        arch = [f for f in S.files if f[0].lower().endswith((".zipmod", ".zip"))]
        print(f"Читаю архивы: {len(arch)} ...", flush=True)
        for i, (rel, size, _) in enumerate(arch, 1):
            row = read_archive(os.path.join(root_path, rel.replace("/", os.sep)))
            row["path"] = rel
            row["size"] = size
            zips.append(row)
            if i % 1000 == 0:
                print(f"  ... {i}/{len(arch)}", flush=True)

    tree = [f"{root_path}/  [{root.n_files} файл., {human(root.size)}]"]
    render(root, tree, "", 0, a)
    with open(os.path.join(a.out, "tree.txt"), "w", encoding="utf-8-sig") as fh:
        fh.write("\n".join(tree) + "\n")

    with open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8-sig") as fh:
        fh.write("\n".join(build_summary(root_path, root, S, zips, a)) + "\n")

    if not a.no_csv:
        with open(os.path.join(a.out, "files.csv"), "w", encoding="utf-8-sig", newline="") as fh:
            wr = csv.writer(fh)
            wr.writerow(["path", "size", "modified"])
            for rel, size, mt in S.files:
                wr.writerow([rel, size, datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M")])

    if zips:
        with open(os.path.join(a.out, "zipmods.csv"), "w", encoding="utf-8-sig", newline="") as fh:
            wr = csv.writer(fh)
            cols = ["path", "size", "entries", "name", "version", "author", "guid", "game", "desc", "top", "err"]
            wr.writerow(cols)
            for z in zips:
                wr.writerow([z.get(c, "") for c in cols])

    print(f"\nГотово. Файлы в папке: {a.out}")
    for n in ("tree.txt", "summary.md", "files.csv", "zipmods.csv"):
        p = os.path.join(a.out, n)
        if os.path.exists(p):
            print(f"  {n}  ({human(os.path.getsize(p))})")
    print("Пришлите summary.md и tree.txt.")


if __name__ == "__main__":
    main()
