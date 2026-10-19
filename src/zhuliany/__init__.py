"""Zhuliany House — параметрична модель будинку для Autodesk Fusion 360.

Пакет розділено на дві частини:
- чисте ядро (без Fusion): config, expr, geometry2d, openings, validate, units —
  його можна запускати й перевіряти на будь-якому комп'ютері;
- zhuliany.fusion — лише тут викликається Fusion API.
"""

__version__ = "0.2.0"
