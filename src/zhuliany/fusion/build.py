"""Побудова моделі у Fusion 360 з data/house_config.json.

Кожен запуск: читає конфіг → перевіряє → видаляє попередню версію компонента
Zhuliany_House → будує все заново. Тому змінюй розміри в JSON і просто
перезапускай скрипт.
"""

import os
import time

import adsk.core
import adsk.fusion

from .. import config, validate
from .. import geometry2d as g
from . import components, helpers as h, parameters

ROOM_FLOOR_MM = 5.0          # товщина "плитки" кімнати в компоненті Rooms (для виділення й міток)
GLASS_MM = 20.0
CUT_OVERSHOOT = "floor_1_height + 20 mm"
MIN_OVERLAP_MM2 = 100.0


class Builder(object):
    def __init__(self, app, house, log):
        self.app = app
        self.house = house
        self.log = log
        self.failures = []

    # ------------------------------------------------------------------
    def run(self):
        design = components.active_design(self.app)
        parameters.sync(design, self.house, self.log)
        self.c = components.rebuild_tree(design, self.house.name)
        self.walls()
        self.rooms()
        self.openings()
        self.slabs()
        self.chimneys()
        self.outlines()
        h.set_attrs(self.c[self.house.name], source="data/house_config.json",
                    built=time.strftime("%Y-%m-%d %H:%M"))
        return self.failures

    def _safe(self, what, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # окремий збій не зупиняє всю побудову
            self.failures.append("{}: {}".format(what, e))
            self.log("ПОМИЛКА {}: {}".format(what, e))
            return None

    # ------------------------------------------------------------------
    def walls(self):
        house = self.house
        ce, ci = self.c["Exterior_Walls"], self.c["Interior_Walls"]

        sk = h.polygon_sketch(ce, "Footprint", house.footprint)
        self.ext_body = h.extrude_new_body(ce, h.single_profile(sk), "floor_1_height", "Exterior_Walls")
        sk = h.polygon_sketch(ce, "Envelope_cut", house.envelope)
        h.extrude_cut(ce, h.single_profile(sk), CUT_OVERSHOOT, [self.ext_body], "Envelope_cut", start_offset=-10)

        sk = h.polygon_sketch(ci, "Envelope", house.envelope)
        self.int_body = h.extrude_new_body(ci, h.single_profile(sk), "floor_1_height", "Interior_Walls")

        for r in house.rooms:
            # усі кімнати вирізаються з внутрішнього масиву
            self._safe("виріз {} у внутрішніх стінах".format(r.id), self._cut, ci, "Int_room_" + r.id,
                       r.polygon, [self.int_body])
            # із зовнішніх стін — лише якщо кімната в них заходить
            if self._ring_overlap(r.polygon) > MIN_OVERLAP_MM2:
                self._safe("виріз {} у зовнішніх стінах".format(r.id), self._cut, ce, "Ext_room_" + r.id,
                           r.polygon, [self.ext_body])
        h.set_attrs(self.ext_body, kind="exterior_walls", repair_tag="UNKNOWN")
        h.set_attrs(self.int_body, kind="interior_walls", repair_tag="UNKNOWN")
        self.log("Стіни: готово")

    def _cut(self, comp, name, pts, bodies, start=-10, distance=CUT_OVERSHOOT):
        sk = h.polygon_sketch(comp, name, pts)
        return h.extrude_cut(comp, h.single_profile(sk), distance, bodies, name, start_offset=start)

    def _ring_overlap(self, poly):
        """Площа перетину полігону з кільцем зовнішніх стін (footprint мінус envelope)."""
        in_fp = abs(g.polygon_area(g.clip_convex(self.house.footprint, poly)))
        in_env = abs(g.polygon_area(g.clip_convex(self.house.envelope, poly)))
        return in_fp - in_env

    def _interior_overlap(self, poly):
        """Площа перетину з масивом внутрішніх стін (envelope мінус кімнати)."""
        a = abs(g.polygon_area(g.clip_convex(self.house.envelope, poly)))
        for r in self.house.rooms:
            a -= g.overlap_area(r.polygon, poly)
        return a

    # ------------------------------------------------------------------
    def rooms(self):
        comp = self.c["Rooms"]
        for r in self.house.rooms:
            def make(r=r):
                sk = h.polygon_sketch(comp, "Room_" + r.id, r.polygon)
                body = h.extrude_new_body(comp, h.single_profile(sk), ROOM_FLOOR_MM, "{} {}".format(r.id, r.name))
                h.set_attrs(body, kind="room", room_id=r.id, bti_no=r.bti_no, name=r.name,
                            name_status=r.name_status, area_m2="{:.2f}".format(r.area_m2),
                            bti_area=r.bti_area, height_mm=r.h)
                for m in self.house.repair_marks:
                    if m.get("room") == r.id:
                        h.set_attrs(body, **{"repair_{}".format(m.get("side", "room")): m.get("tag", "UNKNOWN")})
            self._safe("кімната " + r.id, make)
        self.log("Кімнати: {}".format(len(self.house.rooms)))

    # ------------------------------------------------------------------
    def openings(self):
        ce, ci = self.c["Exterior_Walls"], self.c["Interior_Walls"]
        doors_sk = h.new_sketch(self.c["Doors"], "Door_positions")
        cw = self.c["Windows"]
        for op in self.house.openings:
            poly = op.cut_polygon
            if self._ring_overlap(poly) > MIN_OVERLAP_MM2:
                self._safe("отвір {} (зовн.)".format(op.id), self._cut, ce, "Ext_cut_" + op.id, poly, [self.ext_body],
                           start=op.z0, distance=op.height)
            if self._interior_overlap(poly) > MIN_OVERLAP_MM2:
                self._safe("отвір {} (внутр.)".format(op.id), self._cut, ci, "Int_cut_" + op.id, poly, [self.int_body],
                           start=op.z0, distance=op.height)
            if op.type == "door":
                ln = doors_sk.sketchCurves.sketchLines.addByTwoPoints(h.point(*op.p0), h.point(*op.p1))
                h.set_attrs(ln, opening_id=op.id, status=op.status, leads_to=op.leads_to)
            else:
                self._safe("скло " + op.id, self._glass, cw, op)
        self.log("Отвори: {}".format(len(self.house.openings)))

    def _glass(self, comp, op):
        mid_off = op.wall_thickness / 2.0
        a = g.add(op.p0, g.mul(op.normal, mid_off - GLASS_MM / 2))
        b = g.add(op.p1, g.mul(op.normal, mid_off - GLASS_MM / 2))
        c = g.add(op.p1, g.mul(op.normal, mid_off + GLASS_MM / 2))
        d = g.add(op.p0, g.mul(op.normal, mid_off + GLASS_MM / 2))
        sk = h.polygon_sketch(comp, "Glass_" + op.id, [a, b, c, d])
        body = h.extrude_new_body(comp, h.single_profile(sk), op.height, "Glass_" + op.id, start_offset=op.z0)
        h.set_attrs(body, kind="window", opening_id=op.id, room=op.room, status=op.status,
                    width_mm=op.width, height_mm=op.height, sill_mm=op.sill)

    # ------------------------------------------------------------------
    def slabs(self):
        fp = self.house.footprint
        cf, cc = self.c["Floor_Slab"], self.c["Ceiling"]

        def floor():
            sk = h.polygon_sketch(cf, "Floor_Slab", fp)
            body = h.extrude_new_body(cf, h.single_profile(sk), "-floor_slab_thickness", "Floor_Slab")
            h.set_attrs(body, kind="floor_slab", status="UNKNOWN")

        def ceiling():
            sk = h.polygon_sketch(cc, "Ceiling", fp)
            body = h.extrude_new_body(cc, h.single_profile(sk), "ceiling_thickness", "Ceiling",
                                      start_offset="floor_1_height")
            h.set_attrs(body, kind="ceiling", status="UNKNOWN")
            body.isLightBulbOn = False   # стелю сховано, щоб було видно кімнати згори

        self._safe("підлога", floor)
        self._safe("стеля", ceiling)

    def chimneys(self):
        for ch in self.house.chimneys:
            comp = self.c.get(ch["id"])
            if comp is None:
                comp = components.new_component(self.c["Chimneys"], ch["id"])

            def make(ch=ch, comp=comp):
                sk = h.circle_sketch(comp, ch["id"], ch["x"], ch["y"], ch["diameter"])
                body = h.extrude_new_body(comp, h.single_profile(sk), ch["height"], ch["id"])
                h.set_attrs(body, kind="chimney", room=ch.get("room"), diameter_mm=ch["diameter"])
            self._safe("димар " + ch["id"], make)

    def outlines(self):
        for o in self.house.outlines:
            comp = self.c.get(o["component"]) or self.c["Technical_Elements"]
            x, y, w, l = o["rect"]

            def make(o=o, comp=comp, x=x, y=y, w=w, l=l):
                sk = h.polygon_sketch(comp, o["id"], [(x, y), (x + w, y), (x + w, y + l), (x, y + l)])
                h.set_attrs(sk, status=o["status"], note=o["note"])
            self._safe("контур " + o["id"], make)


# ----------------------------------------------------------------------
def run(app, config_path):
    ui = app.userInterface
    lines = []

    def log(msg):
        lines.append(msg)
        try:
            app.log(msg)
        except Exception:
            pass

    house = config.load(config_path)
    issues = validate.run(house)
    for i in issues:
        log(str(i))
    errors = [i for i in issues if i.level == "ERROR"]
    if errors:
        ui.messageBox("Конфіг має помилки, модель не будую:\n\n" + "\n".join(str(e) for e in errors[:15]),
                      "Zhuliany House")
        _write_log(config_path, lines)
        return

    t0 = time.time()
    failures = Builder(app, house, log).run()
    dt = time.time() - t0
    _write_log(config_path, lines)

    warn = [i for i in issues if i.level == "WARNING"]
    approx = [i for i in warn if i.code == "approx"]
    other = [i for i in warn if i.code != "approx"]
    msg = "Модель перебудовано за {:.1f} с.\n\nКімнат: {}, отворів: {}.\nНеточних значень: {}.\n".format(
        dt, len(house.rooms), len(house.openings), len(approx))
    if other:
        msg += "\nЗауваження ({}):\n".format(len(other)) + "\n".join("• " + i.text for i in other[:10])
    if failures:
        msg += "\n\nНе вдалося побудувати ({}):\n".format(len(failures)) + "\n".join("• " + f for f in failures[:10])
    msg += "\n\nПовний журнал: build_log.txt у корені репозиторію."
    ui.messageBox(msg, "Zhuliany House")


def _write_log(config_path, lines):
    try:
        repo = os.path.normpath(os.path.join(os.path.dirname(config_path), ".."))
        with open(os.path.join(repo, "build_log.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception:
        pass
