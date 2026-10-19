"""User Parameters у Fusion.

Джерело правди — data/house_config.json. Скрипт при кожному запуску переписує
значення параметрів з конфігу. Безпосередньо в геометрію "живими" виразами
підключені лише висотні параметри (floor_1_height, floor_slab_thickness,
ceiling_thickness) — їх можна крутити прямо у Fusion для швидкої прикидки.
Решта параметрів (товщини стін, двері, вікна) — довідкові: план стін
обчислюється в Python, тому їх треба змінювати в JSON і перезапускати скрипт.
"""

from ..units import mm_expr

LIVE = ("floor_1_height", "floor_slab_thickness", "ceiling_thickness")


def sync(design, house, log):
    ups = design.userParameters
    created, updated = 0, 0
    for name, info in house.param_info.items():
        field = house.raw["params"][name]
        if not (isinstance(field, dict) and field.get("fusion")):
            continue
        expr = mm_expr(info.value)
        live = "ЖИВИЙ" if name in LIVE else "довідковий — змінюй у house_config.json"
        comment = "[{}] {}{}".format(info.status or "?", live, "; " + info.source if info.source else "")
        p = ups.itemByName(name)
        if p is None:
            import adsk.core
            ups.add(name, adsk.core.ValueInput.createByString(expr), "mm", comment)
            created += 1
        else:
            if p.expression != expr:
                p.expression = expr
            p.comment = comment
            updated += 1
    log("Параметри: створено {}, оновлено {}".format(created, updated))
