"""Єдине місце конвертації одиниць.

Усі дані проєкту зберігаються в міліметрах. Fusion API всередині працює в
сантиметрах, тож кожне число, яке йде у Fusion, проходить через mm_to_cm().
Ніде більше в коді не повинно бути "/ 10" чи "* 0.1".
"""

MM_PER_CM = 10.0


def mm_to_cm(value_mm):
    """Міліметри → внутрішні одиниці Fusion (см)."""
    return float(value_mm) / MM_PER_CM


def cm_to_mm(value_cm):
    """Внутрішні одиниці Fusion (см) → міліметри."""
    return float(value_cm) * MM_PER_CM


def mm_expr(value_mm):
    """Рядок для ValueInput.createByString / userParameters, напр. '400 mm'."""
    return "{:g} mm".format(float(value_mm))


def mm_to_freecad(value_mm):
    """Міліметри → внутрішні одиниці FreeCAD. FreeCAD усередині вже працює в мм, тож це тотожність,
    але всі числа для FreeCAD однаково йдуть через цю функцію — щоб конвертація лишалась в одному місці."""
    return float(value_mm)


def m2(area_mm2):
    """мм² → м²."""
    return float(area_mm2) / 1e6
