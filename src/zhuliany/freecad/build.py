"""Побудова моделі у FreeCAD (верстак BIM) з data/house_config.json.

Що створюється (дерево документа):

    Ділянка (Site)
    └─ Будинок (Building)
       └─ Поверх I (Building Storey)
          ├─ Зовнішні стіни, Внутрішні стіни       — BIM Wall
          ├─ D01…D16, W01…W12                       — BIM Window/Door, самі прорізають стіни
          ├─ R01…R12                                — BIM Space: назва й площа кімнати
          ├─ Підлога, Перекриття                    — BIM Slab
          ├─ Chimney_Main                           — BIM Structure
          └─ Контури (ґанки, піч)                   — лінії
    План поверху I                                  — 2D-розріз на висоті 1 м, лежить поруч з моделлю

Повторний запуск видаляє лише об'єкти, які створив цей макрос (у них є властивість
ZhulianyGenerated), і будує їх заново. Свої об'єкти в документі можна додавати — їх не чіпаємо.
"""

import os
import time

import FreeCAD
import Part

from .. import config, validate
from .. import geometry2d as g
from ..units import mm_to_freecad as u
from . import shapes

DOC_NAME = "ZhulianyHouse"
TAG = "ZhulianyGenerated"
CUT_OVERSHOOT = 20.0         # мм — виріз виходить за площини стіни, щоб різ був чистим
PLAN_CUT_HEIGHT = 1000.0     # мм — висота горизонтального розрізу для 2D-плану
PLAN_GAP = 3000.0            # мм — відступ 2D-плану праворуч від будинку
WINDOW_FRAME = 50.0          # мм — ширина рами у пресеті вікна/дверей


def _import_bim():
    """Arch — старе ім'я модуля BIM; у FreeCAD 1.x він досі так імпортується."""
    import Arch
    import Draft
    return Arch, Draft


class Builder(object):
    def __init__(self, house, log):
        self.house = house
        self.log = log
        self.failures = []
        self.Arch, self.Draft = _import_bim()

    # ------------------------------------------------------------------
    def run(self, doc):
        self.doc = doc
        self.clear()
        self.level_objects = []
        self.walls()
        self.openings()
        self.spaces()
        self.slabs()
        self.chimneys()
        self.outlines()
        self.hierarchy()
        doc.recompute()
        self._safe("2D-план", self.plan_view)
        doc.recompute()
        self.check_shapes()
        return self.failures

    def _safe(self, what, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # окремий збій не зупиняє всю побудову
            self.failures.append("{}: {}".format(what, e))
            self.log("ПОМИЛКА {}: {}".format(what, e))
            return None

    def _tag(self, obj, **props):
        """Позначити об'єкт як згенерований і записати метадані у властивості (група 'Zhuliany')."""
        if TAG not in obj.PropertiesList:
            obj.addProperty("App::PropertyBool", TAG, "Zhuliany", "Створено макросом ZhulianyHouse")
        setattr(obj, TAG, True)
        for k, v in props.items():
            if v is None:
                continue
            if k not in obj.PropertiesList:
                obj.addProperty("App::PropertyString", k, "Zhuliany", "")
            setattr(obj, k, str(v))
        return obj

    def _feature(self, name, shape, visible=False):
        """Звичайний Part::Feature з готовим тілом — основа для BIM-об'єктів."""
        f = self.doc.addObject("Part::Feature", name)
        f.Shape = shape
        self._tag(f, zh_role=name)
        if FreeCAD.GuiUp and not visible:
            f.ViewObject.Visibility = False
        return f

    # ------------------------------------------------------------------
    def clear(self):
        gen = [o for o in self.doc.Objects if TAG in o.PropertiesList and getattr(o, TAG)]
        # спершу відв'язуємо вікна від стін, інакше FreeCAD при видаленні стіни лається на вікна
        for o in gen:
            if hasattr(o, "Hosts") and o.Hosts:
                o.Hosts = []
        # видаляємо в зворотному порядку створення: спершу контейнери й вікна, потім їхні основи
        names = [o.Name for o in reversed(gen)]
        for _ in range(3):
            for name in list(names):
                obj = self.doc.getObject(name)
                if obj is None:
                    names.remove(name)
                    continue
                try:
                    self.doc.removeObject(name)
                    names.remove(name)
                except Exception:
                    pass
        if names:
            self.log("Не вдалося видалити старі об'єкти: " + ", ".join(names))
        self.doc.recompute()

    # ------------------------------------------------------------------
    def walls(self):
        h = self.house.params["floor_1_height"]
        fp = shapes.prism(self.house.footprint, h)
        env = shapes.prism(self.house.envelope, h)
        rooms = [shapes.prism(r.polygon, h + 2 * CUT_OVERSHOOT, -CUT_OVERSHOOT) for r in self.house.rooms]

        ext = shapes.cut_all(fp, [env] + rooms)
        inner = shapes.cut_all(env, rooms)

        self.ext_wall = self.Arch.makeWall(self._feature("Ext_walls_base", ext), name="Exterior_Walls")
        self.ext_wall.Label = "Зовнішні стіни"
        self._tag(self.ext_wall, zh_role="Exterior_Walls", repair_tag="UNKNOWN")
        self.int_wall = self.Arch.makeWall(self._feature("Int_walls_base", inner), name="Interior_Walls")
        self.int_wall.Label = "Внутрішні стіни"
        self._tag(self.int_wall, zh_role="Interior_Walls", repair_tag="UNKNOWN")
        if FreeCAD.GuiUp:
            self.int_wall.ViewObject.ShapeColor = (0.85, 0.85, 0.82)
        self.level_objects += [self.ext_wall, self.int_wall]
        self.log("Стіни: зовнішні {:.2f} м³, внутрішні {:.2f} м³".format(ext.Volume / 1e9, inner.Volume / 1e9))

    # ------------------------------------------------------------------
    def openings(self):
        for op in self.house.openings:
            hosts = []
            if self._ring_overlap(op.cut_polygon) > 100:
                hosts.append(self.ext_wall)
            if self._inner_overlap(op.cut_polygon) > 100:
                hosts.append(self.int_wall)
            if not hosts:
                self.failures.append("{}: не знайдено стіни для прорізу".format(op.id))
                continue
            win = self._safe("отвір " + op.id, self._window, op, hosts)
            if win is not None:
                self.level_objects.append(win)
        self.log("Отвори: {}".format(len(self.house.openings)))

    def _window(self, op, hosts):
        """BIM-вікно або двері з пресету. Стоїть у середній площині стіни і прорізає хости наскрізь."""
        Arch = self.Arch
        d = g.unit(g.sub(op.p1, op.p0))                 # уздовж стіни
        n = op.normal                                   # назовні від кімнати
        mid = g.add(op.p0, g.mul(n, op.wall_thickness / 2.0))   # середина стіни, лівий край отвору
        # Пресет малюється в площині XY вікна, а продавлюється вздовж його Z.
        # Тож: X вікна = уздовж стіни, Y вікна = вгору, Z вікна = нормаль стіни.
        x_axis = FreeCAD.Vector(d[0], d[1], 0)
        y_axis = FreeCAD.Vector(0, 0, 1)
        z_axis = x_axis.cross(y_axis)
        m = FreeCAD.Matrix(x_axis.x, y_axis.x, z_axis.x, 0,
                           x_axis.y, y_axis.y, z_axis.y, 0,
                           x_axis.z, y_axis.z, z_axis.z, 0)
        rot = FreeCAD.Placement(m).Rotation
        pl = FreeCAD.Placement(shapes.vec(mid[0], mid[1], op.sill), rot)

        frame = min(WINDOW_FRAME, op.width / 4.0, op.height / 4.0)
        if op.type == "door":
            win = Arch.makeWindowPreset("Simple door", width=u(op.width), height=u(op.height),
                                        h1=u(frame), h2=u(frame), h3=u(frame), w1=u(frame * 2), w2=u(frame),
                                        o1=0, o2=u(frame), placement=pl)
        else:
            win = Arch.makeWindowPreset("Open 1-pane", width=u(op.width), height=u(op.height),
                                        h1=u(frame), h2=u(frame), h3=u(frame), w1=u(frame * 2), w2=u(frame),
                                        o1=0, o2=u(frame), placement=pl)
        win.Label = "{} {}".format(op.id, op.note) if op.note else op.id
        win.Hosts = hosts
        # FreeCAD продавлює отвір симетрично: на HoleDepth в обидва боки від площини вікна.
        # Вікно стоїть у середині стіни, тож половина товщини + запас прорізає її наскрізь і не далі.
        win.HoleDepth = u(op.wall_thickness / 2.0 + CUT_OVERSHOOT)
        self._tag(win, zh_role=op.id, opening_id=op.id, room=op.room, side=op.side, status=op.status, leads_to=op.leads_to,
                  width_mm="{:.0f}".format(op.width), height_mm="{:.0f}".format(op.height),
                  sill_mm="{:.0f}".format(op.sill))
        # базовий ескіз пресету теж позначаємо, щоб повторний запуск його прибрав
        if getattr(win, "Base", None) is not None:
            self._tag(win.Base)
        return win

    def _ring_overlap(self, poly):
        in_fp = abs(g.polygon_area(g.clip_convex(self.house.footprint, poly)))
        in_env = abs(g.polygon_area(g.clip_convex(self.house.envelope, poly)))
        return in_fp - in_env

    def _inner_overlap(self, poly):
        a = abs(g.polygon_area(g.clip_convex(self.house.envelope, poly)))
        for r in self.house.rooms:
            a -= g.overlap_area(r.polygon, poly)
        return a

    # ------------------------------------------------------------------
    def spaces(self):
        default_h = self.house.params["floor_1_height"]
        for r in self.house.rooms:
            def make(r=r):
                solid = shapes.prism(r.polygon, r.h or default_h)
                sp = self.Arch.makeSpace(self._feature("Space_base_" + r.id, solid), name=r.id)
                sp.Label = "{} {}".format(r.id, r.name)
                self._tag(sp, zh_role=r.id, room_id=r.id, bti_no=r.bti_no, room_name=r.name, name_status=r.name_status,
                          area_bti=r.bti_area, area_model="{:.2f}".format(r.area_m2))
                for m in self.house.repair_marks:
                    if m.get("room") == r.id:
                        self._tag(sp, **{"repair_" + str(m.get("side", "room")): m.get("tag", "UNKNOWN")})
                if FreeCAD.GuiUp:
                    vo = sp.ViewObject
                    for prop, val in (("Text", [r.name, "$area"]), ("FontSize", u(180)),
                                      ("DisplayMode", "Wireframe")):
                        if hasattr(vo, prop):
                            try:
                                setattr(vo, prop, val)
                            except Exception:
                                pass
                self.level_objects.append(sp)
            self._safe("кімната " + r.id, make)
        self.log("Кімнати: {}".format(len(self.house.rooms)))

    def slabs(self):
        p = self.house.params
        fp = self.house.footprint

        def floor():
            s = self.Arch.makeStructure(self._feature("Floor_base", shapes.prism(fp, p["floor_slab_thickness"],
                                                                                 -p["floor_slab_thickness"])),
                                        name="Floor_Slab")
            s.IfcType = "Slab"
            s.Label = "Підлога (товщина UNKNOWN)"
            self._tag(s, status="UNKNOWN")
            self.level_objects.append(s)

        def ceiling():
            s = self.Arch.makeStructure(self._feature("Ceiling_base", shapes.prism(fp, p["ceiling_thickness"],
                                                                                   p["floor_1_height"])),
                                        name="Ceiling")
            s.IfcType = "Slab"
            s.Label = "Перекриття (товщина UNKNOWN)"
            self._tag(s, status="UNKNOWN")
            if FreeCAD.GuiUp:
                s.ViewObject.Visibility = False   # сховано, щоб згори було видно кімнати
            self.level_objects.append(s)

        self._safe("підлога", floor)
        self._safe("перекриття", ceiling)

    def chimneys(self):
        for ch in self.house.chimneys:
            def make(ch=ch):
                cyl = Part.makeCylinder(u(ch["diameter"] / 2.0), u(ch["height"]), shapes.vec(ch["x"], ch["y"], 0))
                s = self.Arch.makeStructure(self._feature("Chimney_base_" + ch["id"], cyl), name=ch["id"])
                s.IfcType = "Chimney"
                s.Label = "{} (положення UNKNOWN)".format(ch["id"])
                self._tag(s, room=ch.get("room"), diameter_mm=ch["diameter"], status="UNKNOWN")
                if FreeCAD.GuiUp:
                    s.ViewObject.ShapeColor = (0.6, 0.25, 0.2)
                self.level_objects.append(s)
            self._safe("димар " + ch["id"], make)

    def outlines(self):
        for o in self.house.outlines:
            def make(o=o):
                x, y, w, l = o["rect"]
                obj = self.doc.addObject("Part::Feature", o["id"])
                obj.Shape = shapes.wire([(x, y), (x + w, y), (x + w, y + l), (x, y + l)])
                obj.Label = o["id"].replace("_", " ")
                self._tag(obj, status=o["status"], note=o["note"])
                if FreeCAD.GuiUp:
                    obj.ViewObject.LineColor = (0.18, 0.55, 0.34)
                    obj.ViewObject.DrawStyle = "Dashed"
                self.level_objects.append(obj)
            self._safe("контур " + o["id"], make)

    # ------------------------------------------------------------------
    def hierarchy(self):
        Arch = self.Arch
        self.level = Arch.makeFloor(self.level_objects, name="Floor_1")
        self.level.Label = "Поверх I"
        self.building = Arch.makeBuilding([self.level], name="Building")
        self.building.Label = "Будинок Потоцького 65"
        self.site = Arch.makeSite([self.building], name="Site")
        self.site.Label = "Ділянка"
        for o in (self.level, self.building, self.site):
            self._tag(o)

    def plan_view(self):
        """Горизонтальний розріз на висоті 1 м → 2D-план, покладений праворуч від будинку."""
        Arch, Draft = self.Arch, self.Draft
        sec = Arch.makeSectionPlane([self.level])
        sec.Label = "Розріз плану (1 м)"
        sec.Placement = FreeCAD.Placement(shapes.vec(0, 0, PLAN_CUT_HEIGHT), FreeCAD.Rotation())
        self._tag(sec)
        view = Draft.make_shape2dview(sec)
        view.Label = "План поверху I"
        self._tag(view, zh_role="Plan_Floor_1")
        xs = [p[0] for p in self.house.footprint]
        view.Placement = FreeCAD.Placement(shapes.vec(max(xs) - min(xs) + PLAN_GAP, 0, 0), FreeCAD.Rotation())
        if hasattr(view, "InPlace"):
            view.InPlace = False
        self._tag(view)
        if FreeCAD.GuiUp:
            sec.ViewObject.Visibility = False

    def check_shapes(self):
        for obj in [self.ext_wall, self.int_wall]:
            if obj.Shape.isNull() or not obj.Shape.isValid():
                self.failures.append("{}: некоректне тіло після прорізів".format(obj.Label))


# ----------------------------------------------------------------------
def find(doc, role):
    """Знайти згенерований об'єкт за роллю (внутрішні імена FreeCAD призначає сам: Wall001, Window003…)."""
    for o in doc.Objects:
        if "zh_role" in o.PropertiesList and o.zh_role == role:
            return o
    return None


def get_document():
    doc = FreeCAD.listDocuments().get(DOC_NAME)
    if doc is None:
        doc = FreeCAD.newDocument(DOC_NAME)
    if FreeCAD.GuiUp:
        import FreeCADGui
        FreeCADGui.getDocument(doc.Name)
        FreeCAD.setActiveDocument(doc.Name)
    return doc


def run(config_path, log=None, show=None):
    """Повертає (house, issues, failures). show(text) — показати підсумок користувачу."""
    lines = []

    def _log(msg):
        lines.append(msg)
        FreeCAD.Console.PrintMessage(msg + "\n")
        if log:
            log(msg)

    house = config.load(config_path)
    issues = validate.run(house)
    for i in issues:
        lines.append(str(i))
    errors = [i for i in issues if i.level == "ERROR"]
    if errors:
        text = "Конфіг має помилки, модель не будую:\n\n" + "\n".join(str(e) for e in errors[:15])
        _write_log(config_path, lines)
        (show or _log)(text)
        return house, issues, ["config errors"]

    t0 = time.time()
    doc = get_document()
    failures = Builder(house, _log).run(doc)
    dt = time.time() - t0
    _write_log(config_path, lines)

    if FreeCAD.GuiUp:
        import FreeCADGui
        try:
            FreeCADGui.activeDocument().activeView().viewIsometric()
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    warn = [i for i in issues if i.level == "WARNING"]
    approx = [i for i in warn if i.code == "approx"]
    other = [i for i in warn if i.code != "approx"]
    text = "Модель перебудовано за {:.1f} с.\n\nКімнат: {}, отворів: {}.\nНеточних значень: {}.\n".format(
        dt, len(house.rooms), len(house.openings), len(approx))
    if other:
        text += "\nЗауваження ({}):\n".format(len(other)) + "\n".join("• " + i.text for i in other[:10])
    if failures:
        text += "\n\nНе вдалося побудувати ({}):\n".format(len(failures)) + "\n".join("• " + f for f in failures[:10])
    text += "\n\nПовний журнал: build_log.txt у корені репозиторію."
    (show or _log)(text)
    return house, issues, failures


def _write_log(config_path, lines):
    try:
        repo = os.path.normpath(os.path.join(os.path.dirname(config_path), ".."))
        with open(os.path.join(repo, "build_log.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception:
        pass
