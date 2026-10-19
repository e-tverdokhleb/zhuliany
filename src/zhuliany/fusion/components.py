"""Дерево компонентів моделі та повна перебудова."""

import adsk.core
import adsk.fusion

# Структура: батько -> діти. Порожні компоненти — заготовки для наступних фаз.
TREE = [
    ("Ground_Floor", ["Exterior_Walls", "Interior_Walls", "Floor_Slab", "Ceiling", "Rooms", "Doors", "Windows"]),
    ("Chimneys", ["Chimney_Main"]),
    ("Roof", []),
    ("Heating", []),
    ("Water_Pipes", []),
    ("Boiler", []),
    ("Technical_Elements", []),
    ("Exterior", []),
]


def active_design(app):
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
    if design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
    return design


def find_occurrence(parent_comp, name):
    occs = parent_comp.occurrences
    for i in range(occs.count):
        occ = occs.item(i)
        if occ.component.name == name:
            return occ
    return None


def new_component(parent_comp, name):
    occ = parent_comp.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    occ.component.name = name
    return occ.component


def rebuild_tree(design, root_name):
    """Видалити попередню версію моделі й створити порожнє дерево компонентів.

    Повертає dict: ім'я компонента -> Component.
    Усе, що лежить ПОЗА компонентом root_name, не чіпається.
    """
    root = design.rootComponent
    old = find_occurrence(root, root_name)
    if old is not None:
        old.deleteMe()
    house = new_component(root, root_name)
    comps = {root_name: house}
    for parent, children in TREE:
        pc = new_component(house, parent)
        comps[parent] = pc
        for child in children:
            comps[child] = new_component(pc, child)
    return comps
