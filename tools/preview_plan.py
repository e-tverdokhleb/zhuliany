#!/usr/bin/env python3
"""2D-превʼю плану та звіт перевірки — без Fusion 360.

Запуск з кореня репозиторію:
    python tools/preview_plan.py

Створює:
    docs/plan_preview.png      — план першого поверху з конфігу
    docs/validation_report.md  — попередження, товщини стін, площі

Потрібен matplotlib (pip install matplotlib). Сам скрипт Fusion matplotlib не потребує.
"""

import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from zhuliany import config, validate  # noqa: E402


def draw(house, issues, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon, Circle, Rectangle

    bad_rooms = set()
    for i in issues:
        if i.level == "ERROR" or i.code in ("area", "thin_int", "thin_ext"):
            bad_rooms.add(i.text.split()[0].rstrip(":"))

    fig, ax = plt.subplots(figsize=(11, 12), dpi=130)
    ax.add_patch(Polygon(house.footprint, closed=True, facecolor="#9a9a9a", edgecolor="#333", lw=1.2))
    for r in house.rooms:
        fc = "#fff4e0" if r.id in bad_rooms else "#ffffff"
        ax.add_patch(Polygon(r.polygon, closed=True, facecolor=fc, edgecolor="#555", lw=0.6))
        cx = sum(p[0] for p in r.polygon) / len(r.polygon)
        cy = sum(p[1] for p in r.polygon) / len(r.polygon)
        label = "{}  (БТІ {})\n{}\n{:.2f} м²".format(r.id, r.bti_no, r.name, r.area_m2)
        if r.bti_area:
            label += " / БТІ {:.1f}".format(r.bti_area)
        ax.text(cx, cy, label, ha="center", va="center", fontsize=6.3, wrap=True)
    for op in house.openings:
        col = "#3d7bd9" if op.type == "window" else "#a0522d"
        ax.add_patch(Polygon(op.cut_polygon, closed=True, facecolor=col, edgecolor="none", alpha=0.9))
        mx = sum(p[0] for p in op.cut_polygon) / 4
        my = sum(p[1] for p in op.cut_polygon) / 4
        ax.text(mx, my, op.id, fontsize=5, color="white", ha="center", va="center", weight="bold")
    for c in house.chimneys:
        ax.add_patch(Circle((c["x"], c["y"]), c["diameter"] / 2, facecolor="#c0392b", edgecolor="black", lw=0.6))
        ax.text(c["x"], c["y"] - c["diameter"], "димар", fontsize=5.5, ha="center", va="top", color="#c0392b")
    for o in house.outlines:
        x, y, w, l = o["rect"]
        ax.add_patch(Rectangle((x, y), w, l, fill=False, ls="--", lw=0.8, edgecolor="#2e8b57"))
        ax.text(x + w / 2, y + l / 2, o["id"].replace("_", " "), fontsize=5.5, ha="center", va="center", color="#2e8b57")

    xs = [p[0] for p in house.footprint]
    ys = [p[1] for p in house.footprint]
    ax.set_xlim(min(xs) - 600, max(xs) + 600)
    ax.set_ylim(min(ys) - 2000, max(ys) + 2000)
    ax.set_aspect("equal")
    ax.grid(True, lw=0.3, alpha=0.5)
    ax.set_xlabel("X, мм (вправо по аркушу БТІ)")
    ax.set_ylabel("Y, мм (вгору по аркушу БТІ)")
    c = validate.summary(issues)
    ax.set_title("{} — поверх I з конфігу (сіре = стіни)\nERROR: {}  WARNING: {}   помаранчеві кімнати мають зауваження".format(
        house.name, c.get("ERROR", 0), c.get("WARNING", 0)), fontsize=10)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def report(house, issues, out_md):
    L = []
    c = validate.summary(issues)
    L.append("# Звіт перевірки моделі")
    L.append("")
    L.append("Згенеровано `tools/preview_plan.py` з `data/house_config.json`. Не редагуй вручну.")
    L.append("")
    L.append("**ERROR: {} · WARNING: {} · INFO: {}**".format(c.get("ERROR", 0), c.get("WARNING", 0), c.get("INFO", 0)))
    L.append("")
    for level in ("ERROR", "WARNING", "INFO"):
        items = [i for i in issues if i.level == level and i.code != "approx"]
        if items:
            L.append("## {}".format(level))
            L.append("")
            for i in items:
                L.append("- " + i.text)
            L.append("")
    approx = [i for i in issues if i.code == "approx"]
    if approx:
        L.append("## Неточні значення ({})".format(len(approx)))
        L.append("")
        for i in approx:
            L.append("- " + i.text.replace("WARNING: ", ""))
        L.append("")
    L.append("## Кімнати")
    L.append("")
    L.append("| ID | БТІ № | Назва | x | y | w | l | Площа модель | Площа БТІ |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in house.rooms:
        L.append("| {} | {} | {} | {:.0f} | {:.0f} | {:.0f} | {:.0f} | {:.2f} | {} |".format(
            r.id, r.bti_no, r.name, r.x, r.y, r.w, r.l, r.area_m2, r.bti_area if r.bti_area else "—"))
    L.append("")
    L.append("## Товщини стін (обчислені)")
    L.append("")
    L.append("| Кімната | Сторона | За стіною | Товщина, мм |")
    L.append("|---|---|---|---|")
    for rid, side, tag, t in validate.wall_table(house):
        L.append("| {} | {} | {} | {} |".format(rid, side, tag or "—", "—" if t is None else "{:.0f}".format(t)))
    L.append("")
    L.append("## Отвори")
    L.append("")
    L.append("| ID | Тип | Кімната/сторона | offset | ширина | висота | підвіконня | стіна, мм | куди веде |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for op in house.openings:
        L.append("| {} | {} | {} / {} | {:.0f} | {:.0f} | {:.0f} | {:.0f} | {:.0f} | {} |".format(
            op.id, "двері" if op.type == "door" else "вікно", op.room, op.side, op.offset, op.width,
            op.height, op.sill, op.wall_thickness, op.leads_to))
    L.append("")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main():
    house = config.load()
    issues = validate.run(house)
    docs = os.path.join(ROOT, "docs")
    os.makedirs(docs, exist_ok=True)
    report(house, issues, os.path.join(docs, "validation_report.md"))
    try:
        draw(house, issues, os.path.join(docs, "plan_preview.png"))
    except ImportError:
        print("matplotlib не встановлено — превʼю не створено (pip install matplotlib)")
    for i in issues:
        if i.level != "INFO":
            print(i)
    print(validate.summary(issues))
    return 1 if any(i.level == "ERROR" for i in issues) else 0


if __name__ == "__main__":
    sys.exit(main())
