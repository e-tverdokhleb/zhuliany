"""Читання data/house_config.json і перетворення його на обчислену модель.

Кожне числове поле в конфігу може бути:
  - числом:                    3410
  - виразом:                   "R02.right + bearing_wall_thickness"
  - об'єктом зі статусом:      {"value": 3410, "status": "BTI", "source": "..."}

Вирази можуть посилатися на параметри (params) і на кімнати:
  Rxx.x, Rxx.y, Rxx.w, Rxx.l, Rxx.right, Rxx.top, Rxx.cx, Rxx.cy
Порядок у файлі не важливий — залежності розв'язуються автоматично.
"""

import json
import os

from . import expr as ex
from . import geometry2d as g

ROOM_FIELDS = ("x", "y", "w", "l")
ROOM_DERIVED = {
    "right": ("x", "w"),
    "top": ("y", "l"),
    "cx": ("x", "w"),
    "cy": ("y", "l"),
}
NON_EXACT = ("APPROX", "UNKNOWN", "TODO")
KNOWN_STATUSES = ("BTI", "CALC", "DERIVED", "MEASURED") + NON_EXACT
CORNERS = ("bottom_left", "bottom_right", "top_right", "top_left")
SIDES = ("bottom", "right", "top", "left")


class ConfigError(Exception):
    pass


class Value(object):
    """Обчислене значення разом з походженням."""

    def __init__(self, key, raw, status=None, source=None):
        self.key = key
        self.raw = raw
        self.status = status
        self.source = source
        self.value = None

    def __repr__(self):
        return "<{} = {} [{}]>".format(self.key, self.value, self.status)


def _split(key, field, default_status=None):
    """Розібрати поле конфігу на (raw, status, source)."""
    if isinstance(field, dict):
        if "value" not in field:
            raise ConfigError("{}: у полі немає 'value'".format(key))
        status = field.get("status", default_status)
        if status is not None and status not in KNOWN_STATUSES:
            raise ConfigError("{}: невідомий статус '{}'. Дозволено: {}".format(
                key, status, ", ".join(KNOWN_STATUSES)))
        return field["value"], status, field.get("source")
    return field, default_status, None


class House(object):
    """Повністю обчислена модель будинку (мм)."""

    def __init__(self):
        self.name = None
        self.params = {}          # name -> float
        self.param_info = {}      # name -> Value
        self.values = []          # усі Value — для звіту про точність
        self.footprint = []       # [(x, y)]
        self.footprint_status = None
        self.envelope = []        # внутрішній контур зовнішніх стін
        self.rooms = []           # список Room
        self.rooms_by_id = {}
        self.openings = []        # заповнює openings.resolve
        self.chimneys = []
        self.outlines = []
        self.repair_tags = []
        self.repair_marks = []
        self.raw = None


class Room(object):
    def __init__(self, rid):
        self.id = rid
        self.bti_no = None
        self.bti_area = None
        self.name = ""
        self.name_status = None
        self.x = self.y = self.w = self.l = None
        self.h = None
        self.chamfers = []        # [(corner, dx, dy)]
        self.polygon = []
        self.side_edges = {}      # "bottom"/"right"/"top"/"left"/"chamfer0" -> (a, b) у напрямку обходу

    @property
    def right(self):
        return self.x + self.w

    @property
    def top(self):
        return self.y + self.l

    @property
    def area_m2(self):
        return abs(g.polygon_area(self.polygon)) / 1e6

    def __repr__(self):
        return "<Room {} x={:.0f} y={:.0f} w={:.0f} l={:.0f}>".format(self.id, self.x, self.y, self.w, self.l)


def default_config_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "data", "house_config.json"))


def load(path=None):
    path = path or default_config_path()
    if not os.path.exists(path):
        raise ConfigError("Не знайдено конфіг: {}".format(path))
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except ValueError as e:
            raise ConfigError("Помилка JSON у {}: {}".format(path, e))
    return build(data)


def _require(obj, key, where):
    if key not in obj:
        raise ConfigError("{}: бракує обов'язкового поля '{}'".format(where, key))
    return obj[key]


def build(data):
    house = House()
    house.raw = data
    house.name = data.get("project", {}).get("name", "House")
    slots = {}   # key -> Value

    def slot(key, field, default_status=None):
        raw, status, source = _split(key, field, default_status)
        v = Value(key, raw, status, source)
        if key in slots:
            raise ConfigError("Дубльований ключ: {}".format(key))
        slots[key] = v
        return v

    # --- параметри
    params = _require(data, "params", "конфіг")
    for name, field in params.items():
        if "." in name or not name.replace("_", "").isalnum():
            raise ConfigError("Некоректне ім'я параметра: '{}'".format(name))
        slot(name, field)

    # --- кімнати
    rooms_raw = _require(data, "rooms", "конфіг")
    room_ids = set()
    for r in rooms_raw:
        rid = _require(r, "id", "кімната")
        if rid in room_ids:
            raise ConfigError("Дубльований id кімнати: {}".format(rid))
        if rid in params:
            raise ConfigError("id кімнати '{}' збігається з ім'ям параметра".format(rid))
        room_ids.add(rid)
        for f in ROOM_FIELDS:
            slot("{}.{}".format(rid, f), _require(r, f, "кімната " + rid))
        if "h" in r:
            slot("{}.h".format(rid), r["h"])
        for i, ch in enumerate(r.get("chamfers", [])):
            corner = _require(ch, "corner", "{} chamfer {}".format(rid, i))
            if corner not in CORNERS:
                raise ConfigError("{}: невідомий кут скосу '{}'".format(rid, corner))
            st, src = ch.get("status"), ch.get("source")
            slot("{}.chamfer{}.dx".format(rid, i), {"value": _require(ch, "dx", rid), "status": st, "source": src})
            slot("{}.chamfer{}.dy".format(rid, i), {"value": _require(ch, "dy", rid), "status": st, "source": src})

    # --- димарі
    for c in data.get("chimneys", []):
        cid = _require(c, "id", "димар")
        for f in ("x", "y", "diameter", "height"):
            slot("{}.{}".format(cid, f), _require(c, f, "димар " + cid))

    # --- обчислення
    def lookup(name):
        if name in slots:
            v = slots[name]
            if v.value is None:
                raise ex.Unresolved(name)
            return v.value
        if "." in name:
            rid, attr = name.split(".", 1)
            if rid in room_ids and attr in ROOM_DERIVED:
                a, b = ROOM_DERIVED[attr]
                va, vb = lookup(rid + "." + a), lookup(rid + "." + b)
                return va + vb if attr in ("right", "top") else va + vb / 2.0
        raise KeyError(name)

    pending = list(slots.values())
    while pending:
        progressed = False
        still = []
        for v in pending:
            try:
                v.value = ex.evaluate(v.raw, lookup)
                progressed = True
            except ex.Unresolved:
                still.append(v)
            except KeyError as e:
                raise ConfigError("{}: невідоме ім'я {} у виразі '{}'".format(v.key, e, v.raw))
            except ex.ExprError as e:
                raise ConfigError("{}: {}".format(v.key, e))
            except ZeroDivisionError:
                raise ConfigError("{}: ділення на нуль у '{}'".format(v.key, v.raw))
        if not progressed:
            raise ConfigError("Циклічні залежності між: " + ", ".join(v.key for v in still))
        pending = still

    house.values = list(slots.values())
    for name in params:
        house.params[name] = slots[name].value
        house.param_info[name] = slots[name]

    # --- контур
    fp = _require(data, "footprint", "конфіг")
    pts = []
    for i, (px, py) in enumerate(_require(fp, "points", "footprint")):
        pts.append((ex.evaluate(px, lookup), ex.evaluate(py, lookup)))
    if len(pts) < 3:
        raise ConfigError("footprint: потрібно щонайменше 3 точки")
    house.footprint = g.ensure_ccw(pts)
    house.footprint_status = fp.get("status")
    t_ext = house.params.get("exterior_wall_thickness")
    if t_ext is None:
        raise ConfigError("Бракує параметра exterior_wall_thickness")
    house.envelope = g.offset_polygon(house.footprint, t_ext)

    # --- кімнати як полігони
    for r in rooms_raw:
        rid = r["id"]
        room = Room(rid)
        room.bti_no = r.get("bti_no")
        room.bti_area = r.get("bti_area")
        room.name = r.get("name", rid)
        room.name_status = r.get("name_status")
        room.x, room.y = slots[rid + ".x"].value, slots[rid + ".y"].value
        room.w, room.l = slots[rid + ".w"].value, slots[rid + ".l"].value
        if room.w <= 0 or room.l <= 0:
            raise ConfigError("{}: ширина/довжина мають бути > 0 (w={}, l={})".format(rid, room.w, room.l))
        if rid + ".h" in slots:
            room.h = slots[rid + ".h"].value
        for i, ch in enumerate(r.get("chamfers", [])):
            dx = slots["{}.chamfer{}.dx".format(rid, i)].value
            dy = slots["{}.chamfer{}.dy".format(rid, i)].value
            if not (0 < dx < room.w and 0 < dy < room.l):
                raise ConfigError("{}: скіс {} ({}×{}) не вміщується в кімнату".format(rid, i, dx, dy))
            room.chamfers.append((ch["corner"], dx, dy))
        _build_room_polygon(room)
        house.rooms.append(room)
        house.rooms_by_id[rid] = room

    # --- димарі
    for c in data.get("chimneys", []):
        cid = c["id"]
        house.chimneys.append({
            "id": cid,
            "room": c.get("room"),
            "x": slots[cid + ".x"].value,
            "y": slots[cid + ".y"].value,
            "diameter": slots[cid + ".diameter"].value,
            "height": slots[cid + ".height"].value,
        })

    # --- контури без об'єму
    for o in data.get("outlines", {}).get("items", []):
        rx, ry, rw, rl = [ex.evaluate(v, lookup) for v in _require(o, "rect", o.get("id", "outline"))]
        house.outlines.append({
            "id": o["id"], "component": o.get("component", "Technical_Elements"),
            "rect": (rx, ry, rw, rl), "status": o.get("status"), "note": o.get("note", ""),
        })

    house.repair_tags = list(data.get("repair_tags", []))
    house.repair_marks = list(data.get("repair_marks", []))
    house._lookup = lookup

    from . import openings
    openings.resolve(house, data.get("openings", {}).get("items", []))
    return house


def _build_room_polygon(room):
    """Прямокутник кімнати з можливими скосами кутів. Обхід проти годинникової стрілки."""
    x0, y0, x1, y1 = room.x, room.y, room.right, room.top
    corners = {"bottom_left": (x0, y0), "bottom_right": (x1, y0), "top_right": (x1, y1), "top_left": (x0, y1)}
    ch = {c: (dx, dy) for c, dx, dy in room.chamfers}
    pts = []
    labels = []   # мітка ребра, яке ПОЧИНАЄТЬСЯ в цій точці
    # для кожного кута: точка "до" кута і точка "після" (у напрямку обходу)
    order = [("bottom_left", "bottom"), ("bottom_right", "right"), ("top_right", "top"), ("top_left", "left")]
    chamfer_index = {c: i for i, (c, _, _) in enumerate(room.chamfers)}
    for corner, next_side in order:
        cx, cy = corners[corner]
        if corner in ch:
            dx, dy = ch[corner]
            if corner == "bottom_left":
                before, after = (x0, y0 + dy), (x0 + dx, y0)
            elif corner == "bottom_right":
                before, after = (x1 - dx, y0), (x1, y0 + dy)
            elif corner == "top_right":
                before, after = (x1, y1 - dy), (x1 - dx, y1)
            else:
                before, after = (x0 + dx, y1), (x0, y1 - dy)
            pts.append(before)
            labels.append("chamfer{}".format(chamfer_index[corner]))
            pts.append(after)
            labels.append(next_side)
        else:
            pts.append((cx, cy))
            labels.append(next_side)
    room.polygon = pts
    room.side_edges = {}
    n = len(pts)
    for i in range(n):
        room.side_edges[labels[i]] = (pts[i], pts[(i + 1) % n])
