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


def _hybrid_intent():
    """DesignIntentTypes.HybridDesignIntentType або None, якщо Fusion старий і intent ще не існує."""
    types_ = getattr(adsk.fusion, "DesignIntentTypes", None)
    return getattr(types_, "HybridDesignIntentType", None) if types_ else None


def _is_hybrid(design):
    hybrid = _hybrid_intent()
    if hybrid is None:
        return True
    return getattr(design, "designIntent", hybrid) == hybrid


def _is_empty(design):
    root = design.rootComponent
    return root.occurrences.count == 0 and root.bRepBodies.count == 0 and root.sketches.count == 0


def _new_hybrid_design(app):
    # Documents.add завжди створює Hybrid-документ (див. Fusion API: DocumentCreation Sample)
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    return adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))


def active_design(app, log=None):
    """Дизайн, у якому можна створювати компоненти.

    Модель складається з багатьох компонентів, тому потрібен Hybrid-документ.
    Part-документ (одна компонента) і Assembly (лише зовнішні компоненти) не підходять:
    порожній документ перемикаємо на Hybrid, інакше відкриваємо новий.
    """
    log = log or (lambda m: None)
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        design = _new_hybrid_design(app)
        log("Створено новий Hybrid-документ")
    elif not _is_hybrid(design):
        switched = False
        if _is_empty(design):
            try:
                design.designIntent = _hybrid_intent()
                switched = _is_hybrid(design)
            except Exception:
                switched = False
        if switched:
            log("Порожній документ перемкнено на Hybrid")
        else:
            design = _new_hybrid_design(app)
            log("Поточний документ — Part або Assembly; модель будується в новому Hybrid-документі")
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
