"""Fusion 360 script: будує модель будинку з data/house_config.json.

Додай цю папку у Fusion: Utilities → Scripts and Add-Ins → "+" → вибери
fusion_script/ZhulianyHouse. Скрипт сам знаходить src/ і data/ у репозиторії.
"""

import os
import sys
import traceback

import adsk.core

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(REPO, "src")
CONFIG = os.path.join(REPO, "data", "house_config.json")


def _fresh_import():
    """Fusion тримає модулі в пам'яті між запусками — скидаємо їх, щоб підхопити зміни в коді."""
    if SRC not in sys.path:
        sys.path.insert(0, SRC)
    for name in list(sys.modules):
        if name == "zhuliany" or name.startswith("zhuliany."):
            del sys.modules[name]
    from zhuliany.fusion import build
    return build


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        build = _fresh_import()
        build.run(app, CONFIG)
    except Exception:
        if ui:
            ui.messageBox("Помилка скрипта Zhuliany House:\n\n" + traceback.format_exc(), "Zhuliany House")
