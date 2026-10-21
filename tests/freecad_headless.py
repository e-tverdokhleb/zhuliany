"""Перевірка FreeCAD-макроса в справжньому FreeCAD без інтерфейсу.

Запуск (потрібен FreeCAD 1.x):
    freecadcmd tests/freecad_headless.py            # Linux / conda
    /Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd tests/freecad_headless.py   # macOS

Будує модель двічі (перевірка повторного запуску), перевіряє, що стіни коректні,
усі отвори прорізали стіни, кімнати мають правильні площі, і зберігає
docs/ZhulianyHouse.FCStd для перегляду.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd() + "/tests"
REPO = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(REPO, "src"))

import FreeCAD  # noqa: E402

from zhuliany.freecad import build  # noqa: E402

CFG = os.path.join(REPO, "data", "house_config.json")
problems = []


def check(cond, msg):
    if not cond:
        problems.append(msg)
        print("FAIL:", msg)


for attempt in (1, 2):
    house, issues, failures = build.run(CFG, show=lambda t: None)
    check(not failures, "запуск {}: {}".format(attempt, failures))

doc = FreeCAD.getDocument(build.DOC_NAME)
gen = [o for o in doc.Objects if build.TAG in o.PropertiesList]

# повторний запуск не дублює об'єкти
walls = [o for o in gen if getattr(getattr(o, "Proxy", None), "Type", "") == "Wall"]
check(len(walls) == 2, "очікувалось 2 стіни після двох запусків, є {}".format([o.Name for o in walls]))
check(len(gen) == len(set(o.Name for o in gen)), "дублікати")

ext = build.find(doc, "Exterior_Walls")
inn = build.find(doc, "Interior_Walls")
for w in (ext, inn):
    check(w is not None and w.Shape.isValid() and w.Shape.Volume > 0, "стіна {} некоректна".format(w and w.Name))

# отвори прорізали стіни: об'єм стін менший за об'єм базових тіл
for w, base_name in ((ext, "Ext_walls_base"), (inn, "Int_walls_base")):
    base = build.find(doc, base_name)
    cut = base.Shape.Volume - w.Shape.Volume
    print("{}: вирізано отворами {:.3f} м³".format(w.Label, cut / 1e9))
    check(cut > 0.05e9, "{}: отвори майже нічого не вирізали ({:.3f} м³)".format(w.Label, cut / 1e9))

# очікуваний об'єм вирізу ≈ сума (ширина × висота × товщина) по отворах
expected = sum(op.width * op.height * op.wall_thickness for op in house.openings)
actual = sum(build.find(doc, b).Shape.Volume - w.Shape.Volume
             for w, b in ((ext, "Ext_walls_base"), (inn, "Int_walls_base")))
print("отвори: очікувано {:.3f} м³, вирізано {:.3f} м³".format(expected / 1e9, actual / 1e9))
check(abs(actual - expected) / expected < 0.08, "об'єм прорізів відрізняється від очікуваного більш ніж на 8 %")

# кожне вікно/двері має хост
windows = [o for o in gen if hasattr(o, "Hosts") and hasattr(o, "HoleDepth")]
check(len(windows) == len(house.openings), "вікон/дверей {} з {}".format(len(windows), len(house.openings)))

# площі кімнат
for r in house.rooms:
    sp = build.find(doc, r.id)
    check(sp is not None, "немає простору {}".format(r.id))
    if sp is not None and hasattr(sp, "Area"):
        a = float(sp.Area.getValueAs("m^2")) if hasattr(sp.Area, "getValueAs") else float(sp.Area) / 1e6
        check(abs(a - r.area_m2) < 0.05, "{}: площа простору {:.2f} ≠ {:.2f}".format(r.id, a, r.area_m2))

plan = build.find(doc, "Plan_Floor_1")
check(plan is not None and not plan.Shape.isNull() and len(plan.Shape.Edges) > 50,
      "2D-план порожній ({} ребер)".format(len(plan.Shape.Edges) if plan else "—"))

out = os.path.join(REPO, "docs", "ZhulianyHouse.FCStd")
doc.saveAs(out)
print("Збережено", out)
print("ПРОБЛЕМ:", len(problems))
if problems:
    sys.exit(1)
