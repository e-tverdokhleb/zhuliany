"""Тонкі обгортки над Fusion API: ескізи, видавлювання, атрибути.

Усі координати на вході — міліметри; конвертація лише через zhuliany.units.
"""

import adsk.core
import adsk.fusion

from ..units import mm_to_cm

ATTR_GROUP = "zhuliany"


def point(x_mm, y_mm, z_mm=0.0):
    return adsk.core.Point3D.create(mm_to_cm(x_mm), mm_to_cm(y_mm), mm_to_cm(z_mm))


def value(v):
    """Число (мм) → ValueInput у см; рядок → вираз Fusion (може посилатися на параметри)."""
    if isinstance(v, str):
        return adsk.core.ValueInput.createByString(v)
    return adsk.core.ValueInput.createByReal(mm_to_cm(v))


def new_sketch(comp, name):
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = name
    return sk


def draw_polygon(sk, pts):
    """Замкнений полігон з відрізків. Повертає список ліній."""
    lines = sk.sketchCurves.sketchLines
    sk.isComputeDeferred = True
    out = []
    n = len(pts)
    first = None
    prev_end = None
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        start = prev_end if prev_end is not None else point(x1, y1)
        if i == n - 1 and first is not None:
            ln = lines.addByTwoPoints(start, first)
        else:
            ln = lines.addByTwoPoints(start, point(x2, y2))
        if first is None:
            first = ln.startSketchPoint
        prev_end = ln.endSketchPoint
        out.append(ln)
    sk.isComputeDeferred = False
    return out


def polygon_sketch(comp, name, pts):
    sk = new_sketch(comp, name)
    draw_polygon(sk, pts)
    return sk


def circle_sketch(comp, name, cx, cy, diameter):
    sk = new_sketch(comp, name)
    sk.sketchCurves.sketchCircles.addByCenterRadius(point(cx, cy), mm_to_cm(diameter / 2.0))
    return sk


def single_profile(sk):
    if sk.profiles.count < 1:
        raise RuntimeError("Ескіз '{}' не утворив замкненого контуру".format(sk.name))
    if sk.profiles.count == 1:
        return sk.profiles.item(0)
    # кілька профілів — беремо найбільший за площею
    best, best_area = None, -1.0
    for i in range(sk.profiles.count):
        p = sk.profiles.item(i)
        a = p.areaProperties(adsk.fusion.CalculationAccuracy.LowCalculationAccuracy).area
        if a > best_area:
            best, best_area = p, a
    return best


def extrude(comp, profile, distance, operation, start_offset=None, participants=None, name=None):
    """distance/start_offset: число в мм або рядок-вираз Fusion ('floor_1_height')."""
    feats = comp.features.extrudeFeatures
    inp = feats.createInput(profile, operation)
    inp.setDistanceExtent(False, value(distance))
    if start_offset is not None:
        inp.startExtent = adsk.fusion.OffsetStartDefinition.create(value(start_offset))
    if participants:
        inp.participantBodies = list(participants)
    feat = feats.add(inp)
    if name:
        try:
            feat.name = name   # назва в таймлайні; не критично, якщо Fusion її не прийме
        except Exception:
            pass
    return feat


def extrude_new_body(comp, profile, distance, name, start_offset=None):
    feat = extrude(comp, profile, distance, adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
                   start_offset=start_offset, name=name)
    body = feat.bodies.item(0)
    body.name = name
    return body


def extrude_cut(comp, profile, distance, bodies, name, start_offset=None):
    return extrude(comp, profile, distance, adsk.fusion.FeatureOperations.CutFeatureOperation,
                   start_offset=start_offset, participants=bodies, name=name)


def set_attrs(entity, **kwargs):
    """Записати метадані у Fusion attributes (група 'zhuliany')."""
    for k, v in kwargs.items():
        if v is None:
            continue
        existing = entity.attributes.itemByName(ATTR_GROUP, k)
        if existing:
            existing.value = str(v)
        else:
            entity.attributes.add(ATTR_GROUP, k, str(v))
