# Claude Code instructions — Zhuliany House

Ти працюєш над параметричною моделлю приватного будинку у Autodesk Fusion 360.

## Головна мета
Створити підтримувану параметричну модель, яку можна перебудовувати після уточнення вимірів.

## Критичні правила
1. Не вигадуй відсутні геометричні дані.
2. Кожне приблизне значення має статус `APPROX`, `UNKNOWN` або `TODO`.
3. Джерело правди для геометрії — `data/house_config.json`.
4. Не дублюй однакові розміри в різних місцях коду.
5. Конвертацію одиниць Fusion API роби централізовано.
6. Не створюй один гігантський Python-файл.
7. Після кожного помітного етапу оновлюй `docs/model_status.md`.

Перед реалізацією Phase 1 прочитай `prompts/phase1_parametric_shell.md`.

## Як перевіряти зміни
- `python tools/preview_plan.py` — 2D-превʼю `docs/plan_preview.png` і звіт `docs/validation_report.md`.
- `python tests/test_model.py` — тести ядра і smoke-тест коду Fusion на підробленому API.
- `freecadcmd tests/freecad_headless.py` — макрос FreeCAD у справжньому FreeCAD 1.x без інтерфейсу
  (будує двічі, звіряє об'єм прорізів і площі кімнат).
- Плани БТІ та їх розшифровка — `data/plans/bti_notes.md`.

## Дві програми, одне ядро
Ядро `src/zhuliany/` (config, geometry2d, openings, validate) не залежить від CAD.
Адаптери: `src/zhuliany/fusion/` (Fusion 360) і `src/zhuliany/freecad/` (FreeCAD BIM).
Нова фіча геометрії — спершу в ядро, потім в обидва адаптери. Основна програма користувача — FreeCAD.

