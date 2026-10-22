"""Експорт геометрії з FreeCAD-моделі для 3D-прогулянки (web/walkthrough.html).

Запуск:  freecadcmd tools/export_walkthrough.py
Будує модель макросом FreeCAD, тесселює стіни, вікна, димар і пише web/model_data.js
(координати в мм; у браузері переводяться в метри).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.path.join(os.getcwd(), "tools")
REPO = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(REPO, "src"))

import FreeCAD  # noqa: E402
from zhuliany.freecad import build  # noqa: E402

CFG = os.path.join(REPO, "data", "house_config.json")
house, issues, failures = build.run(CFG, show=lambda t: None)
if failures:
    raise SystemExit("Побудова з помилками: {}".format(failures))
doc = FreeCAD.getDocument(build.DOC_NAME)


def mesh(shape, tol=5.0):
    v, f = shape.tessellate(tol)
    return {"v": [round(c) for p in v for c in (p.x, p.y, p.z)], "f": [i for t in f for i in t]}


out = {"meshes": [], "rooms": [], "footprint": [list(map(round, p)) for p in house.footprint],
       "height": house.params["floor_1_height"], "openings": []}
for role, kind in (("Exterior_Walls", "ext"), ("Interior_Walls", "int")):
    out["meshes"].append(dict(kind=kind, **mesh(build.find(doc, role).Shape)))
for op in house.openings:
    obj = build.find(doc, op.id)
    if op.type == "window" and obj is not None:
        out["meshes"].append(dict(kind="window", id=op.id, **mesh(obj.Shape)))
    out["openings"].append({"id": op.id, "type": op.type, "p0": list(map(round, op.p0)),
                            "p1": list(map(round, op.p1)), "status": op.status})
for o in doc.Objects:
    if getattr(o, "IfcType", "") == "Chimney" and build.TAG in o.PropertiesList:
        out["meshes"].append(dict(kind="chimney", **mesh(o.Shape)))
for r in house.rooms:
    out["rooms"].append({"id": r.id, "bti": r.bti_no, "name": r.name, "status": r.name_status,
                         "area": round(r.area_m2, 2), "area_bti": r.bti_area,
                         "poly": [list(map(round, p)) for p in r.polygon]})
for o in house.outlines:
    out.setdefault("outlines", []).append({"id": o["id"], "rect": list(map(round, o["rect"]))})

os.makedirs(os.path.join(REPO, "web"), exist_ok=True)
path = os.path.join(REPO, "web", "model_data.js")
with open(path, "w", encoding="utf-8") as f:
    f.write("window.HOUSE = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n")
print("EXPORTED", path, os.path.getsize(path), "bytes,", len(out["meshes"]), "meshes")
