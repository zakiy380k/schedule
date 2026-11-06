from collections import Counter

from constraints import can_place_lesson
from models import Lesson, Requirement


def validate_schedule(
    schedule: list[Lesson], requirements: list[Requirement], teachers: dict
) -> list[str]:

    errors = []

    # 1. Проверяем каждое занятие на ограничения
    for index, lesson in enumerate(schedule):
        remaining = schedule[:index] + schedule[index + 1 :]

        if not can_place_lesson(lesson, remaining, teachers):
            errors.append(
                f"Недопустимое занятие: "
                f"неделя {lesson.week}, день {lesson.day}, "
                f"пара {lesson.slot}, группа {lesson.group_id}, "
                f"преподаватель {lesson.teacher_id}"
            )

    # 2. Считаем фактические занятия
    actual = Counter(
        (lesson.group_id, lesson.subject_id, lesson.teacher_id, lesson.week)
        for lesson in schedule
    )

    # 3. Считаем занятия по учебному плану
    expected = Counter()

    for requirement in requirements:
        key = (requirement.group_id, requirement.subject_id, requirement.teacher_id)

        expected[(*key, "A")] += requirement.lessons_week_a
        expected[(*key, "B")] += requirement.lessons_week_b

    # 4. Проверяем совпадение нагрузки
    for key in expected.keys() | actual.keys():
        planned = expected[key]
        placed = actual[key]

        if planned != placed:
            errors.append(
                f"Несоответствие нагрузки {key}: "
                f"требуется {planned}, размещено {placed}"
            )
    group_daily_load = Counter(
        (lesson.group_id, lesson.week, lesson.day) for lesson in schedule
    )

    group_ids = {r.group_id for r in requirements}

    for group_id in group_ids:
        for week in ("A", "B"):
            for day in range(5):
                count = group_daily_load[(group_id, week, day)]

                if not 3 <= count <= 4:
                    errors.append(
                        f"Группа {group_id}: неделя {week}, "
                        f"день {day + 1}, пар {count}, "
                        f"требуется от 3 до 4"
                    )
    return errors
