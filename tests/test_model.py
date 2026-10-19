"""Тести без Fusion:  python -m pytest tests   або   python tests/test_model.py"""

import copy
import json
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from zhuliany import config, validate  # noqa: E402

CFG = os.path.join(ROOT, "data", "house_config.json")


def raw():
    with open(CFG, encoding="utf-8") as f:
        return json.load(f)


def test_config_has_no_errors():
    house = config.load(CFG)
    errors = [i for i in validate.run(house) if i.level == "ERROR"]
    assert not errors, "\n".join(map(str, errors))


def test_bottom_facade_closes():
    """Кімнати нижнього ряду + стіни мають дати рівно 3.81 + 7.11 м з БТІ."""
    house = config.load(CFG)
    r12 = house.rooms_by_id["R12"]
    r02 = house.rooms_by_id["R02"]
    assert abs(r02.right - 3810) < 1          # 0.40 + 3.41
    assert abs(r12.right + house.params["exterior_wall_thickness"] - 10920) < 1


def test_changing_room_moves_neighbours():
    """Критерій успіху: змінюєш один розмір — сусідні кімнати зсуваються самі."""
    data = raw()
    for r in data["rooms"]:
        if r["id"] == "R07":
            r["l"]["value"] = 2700          # +90 мм
    house = config.build(copy.deepcopy(data))
    base = config.load(CFG)
    assert abs(house.rooms_by_id["R08"].y - base.rooms_by_id["R08"].y - 90) < 1e-6
    assert abs(house.rooms_by_id["R06"].l - base.rooms_by_id["R06"].l - 90) < 1e-6


def test_wall_thickness_param_propagates():
    data = raw()
    data["params"]["interior_wall_thickness"]["value"] = 150
    house = config.build(data)
    r03, r04 = house.rooms_by_id["R03"], house.rooms_by_id["R04"]
    assert abs(r04.y - r03.top - 150) < 1e-6


def test_bad_reference_is_clear_error():
    data = raw()
    data["rooms"][0]["x"]["value"] = "R99.right + 10"
    try:
        config.build(data)
    except config.ConfigError as e:
        assert "R99.right" in str(e)
    else:
        raise AssertionError("очікувалась ConfigError")


def test_cycle_detected():
    data = raw()
    for r in data["rooms"]:
        if r["id"] == "R02":
            r["x"]["value"] = "R01.x - 10"
    try:
        config.build(data)
    except config.ConfigError as e:
        assert "Циклічні" in str(e)
    else:
        raise AssertionError("очікувалась ConfigError")


def test_openings_find_walls():
    house = config.load(CFG)
    for op in house.openings:
        assert op.wall_thickness and 100 < op.wall_thickness < 700, (op.id, op.wall_thickness)
    d01 = [o for o in house.openings if o.id == "D01"][0]
    assert d01.leads_to == "EXTERIOR"


def test_fusion_build_smoke():
    import fake_adsk
    app, design, messages = fake_adsk.install()
    for m in list(sys.modules):
        if m.startswith("zhuliany.fusion"):
            del sys.modules[m]
    from zhuliany.fusion import build
    build.run(app, CFG)
    assert messages, "немає підсумкового повідомлення"
    text = messages[-1][0]
    assert "Не вдалося" not in text, text
    assert design.userParameters.itemByName("floor_1_height") is not None
    cuts = [o for o in design.ops if o[0] == "cut"]
    assert len(cuts) > 30
    # другий запуск не повинен дублювати модель
    build.run(app, CFG)
    assert design.rootComponent.occurrences.count == 1


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
