"""Generate an offline HTML timetable from the synthetic dataset.
Usage: python view_schedule.py --groups 5 --optimize
"""

import argparse
import html
from collections import Counter
from pathlib import Path

from constraints import can_place_lesson, expand_requirements
from data_loader import load_dataset
from generator import generate_schedule
from optimizer import optimize_schedule
from scoring import count_teacher_windows, evaluate_schedule

parser = argparse.ArgumentParser()
parser.add_argument("--groups", type=int, default=3)
parser.add_argument("--optimize", action="store_true")
parser.add_argument("--output", default="schedule_preview.html")
args = parser.parse_args()
if not 1 <= args.groups <= 20:
    parser.error("--groups must be between 1 and 20")

groups, subjects, teachers, metadata, requirements = load_dataset("data", args.groups)
tasks = expand_requirements(requirements)
schedule = []
if not generate_schedule(tasks, schedule, teachers):
    raise RuntimeError("Could not generate a schedule")
if args.optimize:
    schedule = optimize_schedule(schedule, teachers)
expected = Counter((x.week, x.group_id, x.subject_id, x.teacher_id) for x in tasks)
actual = Counter((x.week, x.group_id, x.subject_id, x.teacher_id) for x in schedule)
assert expected == actual, "Lost or duplicated lessons"
for i, lesson in enumerate(schedule):
    assert can_place_lesson(lesson, schedule[:i] + schedule[i + 1 :], teachers), lesson

subject_names = {int(s["id"]): s["name"] for s in subjects}
group_names = {int(g["id"]): g["name"] for g in groups}
days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница"]
parts = [
    '<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
    """<title>Расписание колледжа — тест</title><style>
:root{font-family:system-ui,Arial,sans-serif;color:#14233b;background:#f4f6fa}body{max-width:1200px;margin:24px auto;padding:0 16px}h1{margin-bottom:4px}p{color:#526072}.toolbar{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0}select{padding:10px;border:1px solid #c7d0dc;border-radius:8px;background:white;min-width:220px}table{width:100%;border-collapse:separate;border-spacing:5px;table-layout:fixed}th{background:#e4eaf3;padding:12px;border-radius:8px}td{vertical-align:top;background:#fff;border:1px solid #e3e8f0;border-radius:8px;padding:10px;height:82px}.lesson{font-weight:650;font-size:14px}.meta{margin-top:6px;color:#526072;font-size:12px}.empty{color:#b3bdcc}.panel{display:none}.panel.active{display:block}.metric{font-weight:650} @media(max-width:650px){table{min-width:780px}.scroll{overflow:auto}}
</style></head><body>""",
    "<h1>Тестовое расписание колледжа</h1>",
    "<p>Данные учебных планов и нагрузок синтетические. Таблица — результат фактического запуска генератора, а не утверждённое расписание колледжа.</p>",
    f'<p class="metric">Групп: {len(groups)} · Преподавателей: {len(teachers)} · Занятий за цикл: {len(schedule)} · Штраф: {evaluate_schedule(schedule):.2f} · Окон преподавателей: {sum(count_teacher_windows(tid, schedule) for tid in teachers)}</p>',
    '<div class="toolbar"><select id="kind"><option value="group">По группам</option><option value="teacher">По преподавателям</option></select><select id="person"></select><select id="week"><option value="A">Неделя A (числитель)</option><option value="B">Неделя B (знаменатель)</option></select></div>',
]


def cell(lesson, kind):
    subject = html.escape(subject_names.get(lesson.subject_id, str(lesson.subject_id)))
    other = (
        teachers[lesson.teacher_id].name
        if kind == "group"
        else group_names.get(lesson.group_id, str(lesson.group_id))
    )
    return f'<div class="lesson">{subject}</div><div class="meta">{html.escape(other)}</div>'


for kind, people in [
    ("group", group_names),
    ("teacher", {i: t.name for i, t in teachers.items()}),
]:
    for person_id, person_name in people.items():
        for week in ("A", "B"):
            parts.append(
                f'<section class="panel" data-kind="{kind}" data-person="{person_id}" data-week="{week}"><h2>{html.escape(person_name)} — неделя {week}</h2><div class="scroll"><table><thead><tr><th>Пара</th>'
            )
            parts.extend(f"<th>{day}</th>" for day in days)
            parts.append("</tr></thead><tbody>")
            for slot in range(1, 5):
                parts.append(f"<tr><th>{slot}</th>")
                for day in range(5):
                    matched = [
                        l
                        for l in schedule
                        if l.week == week
                        and l.day == day
                        and l.slot == slot
                        and (l.group_id if kind == "group" else l.teacher_id)
                        == person_id
                    ]
                    parts.append(
                        "<td>"
                        + (
                            "".join(cell(l, kind) for l in matched)
                            if matched
                            else '<span class="empty">—</span>'
                        )
                        + "</td>"
                    )
                parts.append("</tr>")
            parts.append("</tbody></table></div></section>")

parts.append(
    "<script>const people="
    + __import__("json").dumps(
        {"group": group_names, "teacher": {i: t.name for i, t in teachers.items()}},
        ensure_ascii=False,
    )
    + ';const kind=document.querySelector("#kind"),person=document.querySelector("#person"),week=document.querySelector("#week");function refreshPeople(){person.innerHTML="";Object.entries(people[kind.value]).forEach(([id,name])=>{const o=document.createElement("option");o.value=id;o.textContent=name;person.append(o)});refresh()}function refresh(){document.querySelectorAll(".panel").forEach(p=>p.classList.toggle("active",p.dataset.kind===kind.value&&p.dataset.person===person.value&&p.dataset.week===week.value))}kind.addEventListener("change",refreshPeople);person.addEventListener("change",refresh);week.addEventListener("change",refresh);refreshPeople();</script></body></html>'
)
output = Path(args.output)
output.write_text("".join(parts), encoding="utf-8")
print(
    f"Created {output.resolve()} | lessons={len(schedule)} | score={evaluate_schedule(schedule):.2f}"
)
