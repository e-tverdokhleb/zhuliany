"""Перевірка обчисленої моделі. Не змінює дані — лише повідомляє.

Рівні:
  ERROR   — модель побудується неправильно (накладання кімнат, отвір поза стіною);
  WARNING — підозріло або неточно (приблизні значення, розбіжність площ, тонка стіна);
  INFO    — довідка.
"""

from . import geometry2d as g
from .config import NON_EXACT

MIN_INTERIOR_WALL = 80.0     # мм — тонше вже підозріло навіть для перегородки
MIN_EXTERIOR_WALL = 300.0    # мм
AREA_TOLERANCE = 0.05        # 5 %


class Issue(object):
    def __init__(self, level, code, text):
        self.level, self.code, self.text = level, code, text

    def __str__(self):
        return "{}: {}".format(self.level, self.text)


def run(house):
    issues = []
    add = lambda lvl, code, txt: issues.append(Issue(lvl, code, txt))

    # 1. неточні значення
    for v in house.values:
        if v.status in NON_EXACT:
            add("WARNING", "approx", "{} = {:.0f} мм має статус {}{}".format(
                v.key, v.value, v.status, " ({})".format(v.source) if v.source else ""))
        elif v.status is None and not isinstance(v.raw, str):
            add("WARNING", "nostatus", "{} = {:.0f} мм без статусу точності".format(v.key, v.value))

    # 2. кімнати всередині внутрішнього контуру
    for r in house.rooms:
        outside = [p for p in r.polygon if not g.point_in_polygon(p, house.footprint)]
        if outside:
            add("ERROR", "outside", "{} виходить за зовнішній контур будинку".format(r.id))

    # 3. накладання кімнат
    rooms = house.rooms
    for i in range(len(rooms)):
        for j in range(i + 1, len(rooms)):
            a = g.overlap_area(rooms[i].polygon, rooms[j].polygon)
            if a > 1000:   # > 0.001 м²
                add("ERROR", "overlap", "{} і {} накладаються на {:.3f} м²".format(rooms[i].id, rooms[j].id, a / 1e6))

    # 4. площі проти БТІ
    for r in rooms:
        if r.bti_area:
            diff = (r.area_m2 - r.bti_area) / r.bti_area
            if abs(diff) > AREA_TOLERANCE:
                add("WARNING", "area", "{}: площа в моделі {:.2f} м², за БТІ {:.1f} м² ({:+.0f} %)".format(
                    r.id, r.area_m2, r.bti_area, diff * 100))

    # 5. товщини стін навколо кожної кімнати
    for r in rooms:
        for side, (a, b) in sorted(r.side_edges.items()):
            t, tag = wall_behind(house, r, a, b)
            if t is None:
                add("ERROR", "wall", "{} / {}: за стіною нічого не знайдено".format(r.id, side))
            elif tag == "EXTERIOR" and t < MIN_EXTERIOR_WALL:
                add("WARNING", "thin_ext", "{} / {}: зовнішня стіна лише {:.0f} мм".format(r.id, side, t))
            elif tag != "EXTERIOR" and t < MIN_INTERIOR_WALL:
                add("WARNING", "thin_int", "{} / {}: стіна до {} лише {:.0f} мм".format(r.id, side, tag, t))

    # 6. отвори
    for op in house.openings:
        for lvl, txt in op.problems:
            add(lvl, "opening", txt)

    # 7. димарі
    for c in house.chimneys:
        room = house.rooms_by_id.get(c.get("room"))
        if room and not g.point_in_polygon((c["x"], c["y"]), room.polygon):
            add("ERROR", "chimney", "{} стоїть поза кімнатою {}".format(c["id"], room.id))

    # 8. назви кімнат
    for r in rooms:
        if r.name_status in NON_EXACT:
            add("INFO", "name", "{} (БТІ №{}): назва '{}' — {}".format(r.id, r.bti_no, r.name, r.name_status))
    return issues


def wall_behind(house, room, a, b):
    """Товщина стіни за серединою ребра кімнати та що за нею."""
    mid = g.mul(g.add(a, b), 0.5)
    n = g.outward_normal_ccw(a, b)
    targets = [(r.id, r.polygon) for r in house.rooms if r.id != room.id]
    targets.append(("EXTERIOR", house.footprint))
    return g.raycast(mid, n, targets)


def wall_table(house):
    """Таблиця: кімната, сторона, що за стіною, товщина."""
    rows = []
    for r in house.rooms:
        for side in ("bottom", "right", "top", "left") + tuple(s for s in sorted(r.side_edges) if s.startswith("chamfer")):
            if side not in r.side_edges:
                continue
            a, b = r.side_edges[side]
            t, tag = wall_behind(house, r, a, b)
            rows.append((r.id, side, tag, t))
    return rows


def summary(issues):
    counts = {}
    for i in issues:
        counts[i.level] = counts.get(i.level, 0) + 1
    return counts
