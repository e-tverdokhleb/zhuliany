"""Двері й вікна: прив'язка до сторони кімнати і визначення товщини стіни.

Отвір задається відносно кімнати:
  room   — кімната, з якої "дивимось" на стіну;
  side   — bottom / right / top / left або chamfer0, chamfer1 (скошена стіна);
  offset — відстань від лівого кінця сторони (bottom, top) або від нижнього
           кінця (left, right); для скосу — від його початку за обходом;
  width, height, sill — розміри (за замовчуванням з параметрів *_default).

Товщину стіни скрипт знаходить сам: від середини отвору пускає промінь назовні
і шукає найближчу кімнату або зовнішній контур. Тому при зміні товщини стін чи
розмірів кімнат отвори автоматично прорізають стіну на всю глибину.
"""

from . import expr as ex
from . import geometry2d as g

OVERSHOOT = 20.0   # мм — наскільки виріз виходить за площини стіни, щоб різ був чистим
DEFAULTS = {
    "door": {"width": "door_width_default", "height": "door_height_default", "sill": 0},
    "window": {"width": None, "height": "window_height_default", "sill": "window_sill_height_default"},
}


class Opening(object):
    def __init__(self, oid):
        self.id = oid
        self.type = None
        self.room = None
        self.side = None
        self.offset = self.width = self.height = self.sill = None
        self.status = None
        self.note = ""
        self.p0 = self.p1 = None      # кінці отвору на площині стіни (з боку кімнати)
        self.normal = None            # назовні від кімнати
        self.wall_thickness = None
        self.leads_to = None          # id сусідньої кімнати або "EXTERIOR"
        self.cut_polygon = []         # прямокутник у плані, який вирізається
        self.problems = []            # (level, text)

    @property
    def z0(self):
        return self.sill

    @property
    def z1(self):
        return self.sill + self.height


def _targets(house, exclude_room):
    t = [(r.id, r.polygon) for r in house.rooms if r.id != exclude_room]
    t.append(("EXTERIOR", house.footprint))
    return t


def resolve(house, items):
    house.openings = []
    seen = set()
    for it in items:
        oid = it.get("id")
        if not oid:
            raise_error("Отвір без id: {}".format(it))
        if oid in seen:
            raise_error("Дубльований id отвору: {}".format(oid))
        seen.add(oid)
        op = Opening(oid)
        op.type = it.get("type")
        if op.type not in DEFAULTS:
            raise_error("{}: type має бути 'door' або 'window'".format(oid))
        op.room = it.get("room")
        if op.room not in house.rooms_by_id:
            raise_error("{}: невідома кімната '{}'".format(oid, op.room))
        room = house.rooms_by_id[op.room]
        op.side = it.get("side")
        if op.side not in room.side_edges:
            raise_error("{}: у кімнати {} немає сторони '{}' (є: {})".format(
                oid, op.room, op.side, ", ".join(sorted(room.side_edges))))
        op.status = it.get("status")
        op.note = it.get("note", "")

        def num(field):
            raw = it.get(field, DEFAULTS[op.type].get(field))
            if raw is None:
                raise_error("{}: бракує поля '{}'".format(oid, field))
            try:
                return ex.evaluate(raw, house._lookup)
            except (KeyError, ex.ExprError) as e:
                raise_error("{}.{}: {}".format(oid, field, e))

        if "offset" not in it:
            raise_error("{}: бракує поля 'offset'".format(oid))
        op.offset, op.width = num("offset"), num("width")
        op.height, op.sill = num("height"), num("sill")
        if op.width <= 0 or op.height <= 0:
            raise_error("{}: ширина й висота мають бути > 0".format(oid))
        _place(house, room, op)
        house.openings.append(op)


def raise_error(msg):
    from .config import ConfigError
    raise ConfigError(msg)


def _place(house, room, op):
    a, b = room.side_edges[op.side]
    side = op.side
    # Початок відліку offset та напрямок уздовж стіни
    if side == "bottom":
        start, direction = (room.x, room.y), (1.0, 0.0)
    elif side == "top":
        start, direction = (room.x, room.top), (1.0, 0.0)
    elif side == "left":
        start, direction = (room.x, room.y), (0.0, 1.0)
    elif side == "right":
        start, direction = (room.right, room.y), (0.0, 1.0)
    else:  # скіс
        start, direction = a, g.unit(g.sub(b, a))

    p0 = g.add(start, g.mul(direction, op.offset))
    p1 = g.add(p0, g.mul(direction, op.width))
    op.p0, op.p1 = p0, p1
    op.normal = g.outward_normal_ccw(a, b)

    # отвір має лежати в межах реального ребра (з урахуванням скосів)
    edge_len = g.length(g.sub(b, a))
    for p, label in ((p0, "початок"), (p1, "кінець")):
        if g.dist_point_segment(p, a, b) > 1.0:
            op.problems.append(("ERROR", "{} ({}) виходить за межі сторони {} кімнати {} (довжина {:.0f} мм)".format(
                op.id, label, side, room.id, edge_len)))

    # товщина стіни — промінь назовні з середини та з обох кінців
    targets = _targets(house, room.id)
    mid = g.mul(g.add(p0, p1), 0.5)
    hits = []
    for p in (mid, g.add(p0, g.mul(direction, 1.0)), g.sub(p1, g.mul(direction, 1.0))):
        t, tag = g.raycast(p, op.normal, targets)
        hits.append((t, tag))
    t_mid, tag_mid = hits[0]
    if t_mid is None:
        op.problems.append(("ERROR", "{}: за стіною нічого не знайдено — перевір сторону '{}'".format(op.id, side)))
        t_mid, tag_mid = house.params.get("exterior_wall_thickness", 400.0), "EXTERIOR"
    op.wall_thickness = t_mid
    op.leads_to = tag_mid
    for t, tag in hits[1:]:
        if t is None or tag != tag_mid or abs(t - t_mid) > 20:
            op.problems.append(("WARNING", "{}: різна товщина стіни/сусід уздовж отвору (середина {:.0f} мм → {}, край {} → {}). "
                                "Можливо, отвір заходить на кут.".format(
                                    op.id, t_mid, tag_mid, "—" if t is None else "{:.0f} мм".format(t), tag)))
            break
    if t_mid > 1000:
        op.problems.append(("WARNING", "{}: стіна товщиною {:.0f} мм — підозріло товста".format(op.id, t_mid)))

    inner = -OVERSHOOT
    outer = t_mid + OVERSHOOT
    op.cut_polygon = [
        g.add(p0, g.mul(op.normal, inner)),
        g.add(p1, g.mul(op.normal, inner)),
        g.add(p1, g.mul(op.normal, outer)),
        g.add(p0, g.mul(op.normal, outer)),
    ]
