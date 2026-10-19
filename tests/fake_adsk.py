"""Мінімальна підробка adsk.core / adsk.fusion для smoke-тесту поза Fusion.

Перевіряє лише, що наш код викликає API без Python-помилок (опечатки,
неправильні аргументи, порядок дій). Реальну геометрію перевіряє тільки Fusion.
"""

import sys
import types


class _Coll(object):
    def __init__(self, items=None):
        self._items = list(items or [])

    @property
    def count(self):
        return len(self._items)

    def item(self, i):
        return self._items[i]


class Attributes(object):
    def __init__(self):
        self.d = {}

    def itemByName(self, g, n):
        return self.d.get((g, n))

    def add(self, g, n, v):
        a = types.SimpleNamespace(value=v)
        self.d[(g, n)] = a
        return a


class Entity(object):
    def __init__(self, name=""):
        self.name = name
        self.attributes = Attributes()
        self.isLightBulbOn = True


class SketchLines(object):
    def __init__(self, sk):
        self.sk = sk

    def addByTwoPoints(self, a, b):
        ln = Entity("line")
        ln.startSketchPoint = a
        ln.endSketchPoint = b
        self.sk.n_curves += 1
        return ln


class SketchCircles(object):
    def __init__(self, sk):
        self.sk = sk

    def addByCenterRadius(self, c, r):
        assert r > 0
        self.sk.n_curves += 1
        return Entity("circle")


class Sketch(Entity):
    def __init__(self):
        Entity.__init__(self)
        self.n_curves = 0
        self.isComputeDeferred = False
        self.sketchCurves = types.SimpleNamespace(sketchLines=SketchLines(self), sketchCircles=SketchCircles(self))

    @property
    def profiles(self):
        return _Coll([Entity("profile")] if self.n_curves else [])


class ExtrudeInput(object):
    def __init__(self, profile, op):
        self.profile, self.op = profile, op
        self.participantBodies = []
        self.startExtent = None
        self.distance = None

    def setDistanceExtent(self, sym, dist):
        self.distance = dist


class ExtrudeFeatures(object):
    def __init__(self, log):
        self.log = log

    def createInput(self, profile, op):
        return ExtrudeInput(profile, op)

    def add(self, inp):
        assert inp.distance is not None
        if inp.op == "cut":
            assert inp.participantBodies, "cut without bodies"
        feat = Entity("feat")
        feat.bodies = _Coll([Entity("body")])
        self.log.append((inp.op, inp.distance))
        return feat


class Component(Entity):
    def __init__(self, design):
        Entity.__init__(self)
        self.design = design
        self.occurrences = Occurrences(design)
        self.xYConstructionPlane = object()
        self.sketches = types.SimpleNamespace(add=self._add_sketch)
        self.features = types.SimpleNamespace(extrudeFeatures=ExtrudeFeatures(design.ops))

    def _add_sketch(self, plane):
        sk = Sketch()
        self.design.sketches.append(sk)
        return sk


class Occurrences(_Coll):
    def __init__(self, design):
        _Coll.__init__(self)
        self.design = design

    def addNewComponent(self, m):
        occ = types.SimpleNamespace(component=Component(self.design))
        occs = self
        occ.deleteMe = lambda: occs._items.remove(occ)
        self._items.append(occ)
        return occ


class UserParameters(_Coll):
    def itemByName(self, n):
        for p in self._items:
            if p.name == n:
                return p
        return None

    def add(self, name, vi, units, comment):
        p = types.SimpleNamespace(name=name, expression=vi.v, comment=comment)
        self._items.append(p)
        return p


class Design(object):
    def __init__(self):
        self.ops = []
        self.sketches = []
        self.designType = "parametric"
        self.rootComponent = Component(self)
        self.userParameters = UserParameters()


class VI(object):
    def __init__(self, v):
        self.v = v


def install():
    design = Design()
    messages = []
    app = types.SimpleNamespace(
        activeProduct=design,
        userInterface=types.SimpleNamespace(messageBox=lambda *a: messages.append(a)),
        log=lambda m: None,
        documents=None,
    )
    core = types.ModuleType("adsk.core")
    core.Point3D = types.SimpleNamespace(create=lambda x, y, z: (x, y, z))
    core.ValueInput = types.SimpleNamespace(createByString=VI, createByReal=VI)
    core.Matrix3D = types.SimpleNamespace(create=lambda: None)
    core.Application = types.SimpleNamespace(get=lambda: app)
    core.DocumentTypes = types.SimpleNamespace(FusionDesignDocumentType=1)
    fusion = types.ModuleType("adsk.fusion")
    fusion.Design = types.SimpleNamespace(cast=lambda x: x)
    fusion.DesignTypes = types.SimpleNamespace(ParametricDesignType="parametric")
    fusion.FeatureOperations = types.SimpleNamespace(NewBodyFeatureOperation="new", CutFeatureOperation="cut")
    fusion.OffsetStartDefinition = types.SimpleNamespace(create=lambda v: ("offset", v))
    fusion.CalculationAccuracy = types.SimpleNamespace(LowCalculationAccuracy=0)
    adsk = types.ModuleType("adsk")
    adsk.core, adsk.fusion = core, fusion
    sys.modules["adsk"], sys.modules["adsk.core"], sys.modules["adsk.fusion"] = adsk, core, fusion
    return app, design, messages
