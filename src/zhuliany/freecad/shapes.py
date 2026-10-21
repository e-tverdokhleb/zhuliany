"""Перетворення 2D-полігонів плану (мм) на тіла Part. Усі числа йдуть через units.mm_to_freecad."""

import FreeCAD
import Part

from ..units import mm_to_freecad as u


def vec(x, y, z=0.0):
    return FreeCAD.Vector(u(x), u(y), u(z))


def face(pts, z=0.0):
    wire = Part.makePolygon([vec(x, y, z) for x, y in pts] + [vec(pts[0][0], pts[0][1], z)])
    return Part.Face(wire)


def prism(pts, height, z=0.0):
    """Призма з полігону: від z до z + height."""
    return face(pts, z).extrude(FreeCAD.Vector(0, 0, u(height)))


def wire(pts, z=0.0, closed=True):
    p = [vec(x, y, z) for x, y in pts]
    if closed:
        p.append(p[0])
    return Part.makePolygon(p)


def cut_all(solid, tools):
    """Відняти список тіл одним булевим — швидше й надійніше, ніж по одному."""
    tools = [t for t in tools if t is not None and not t.isNull()]
    if not tools:
        return solid
    return solid.cut(tools).removeSplitter()
