#!/usr/bin/env python3
"""Зібрати web/walkthrough.html з шаблону й експортованих даних.

    freecadcmd tools/export_walkthrough.py   # 1) геометрія з FreeCAD → web/model_data.js
    python tools/build_walkthrough.py        # 2) вставити дані в сторінку → web/walkthrough.html
"""
import os

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
web = os.path.join(ROOT, "web")
tpl = open(os.path.join(web, "walkthrough_template.html"), encoding="utf-8").read()
data = open(os.path.join(web, "model_data.js"), encoding="utf-8").read()
marker = "/*__HOUSE_DATA__*/"
assert marker in tpl, "у шаблоні немає маркера даних"
out = os.path.join(web, "walkthrough.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(tpl.replace(marker, data.strip()))
print("OK", out, os.path.getsize(out), "bytes")
