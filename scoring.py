from models import Lesson


def count_teacher_windows(teacher_id: int, schedule: list[Lesson]) -> int:
    teacher_days = {}

    # ЭТАП 1. Собираем все занятия преподавателя
    for lesson in schedule:
        if lesson.teacher_id == teacher_id:
            day_key = (lesson.week, lesson.day)

            if day_key not in teacher_days:
                teacher_days[day_key] = set()

            teacher_days[day_key].add(lesson.slot)

    # ЭТАП 2. Подсчитываем окна по каждому дню
    total_windows = 0

    for day_key, slots in teacher_days.items():
        if len(slots) <= 1:
            continue

        min_slot = min(slots)
        max_slot = max(slots)

        total_span = max_slot - min_slot + 1
        occupied_slots = len(slots)

        day_windows = total_span - occupied_slots
        total_windows += day_windows

    return total_windows


def group_load_penalty(schedule: list[Lesson]) -> float:
    group_days = {}
    for lesson in schedule:
        key = (lesson.group_id, lesson.week)
        if key not in group_days:
            group_days[key] = [0] * 5

        group_days[key][lesson.day] += 1

    total_penalty = 0.0

    for key, lessons_per_day in group_days.items():
        total_lessons = sum(lessons_per_day)
        avg_lessons = total_lessons / 5
        for count in lessons_per_day:
            deviation = count - avg_lessons
            total_penalty += deviation**2
    return total_penalty


def teacher_load_penalty(schedule: list[Lesson]) -> float:
    teacher_days = {}
    for lesson in schedule:
        key = (lesson.teacher_id, lesson.week)
        if key not in teacher_days:
            teacher_days[key] = [0] * 5

        teacher_days[key][lesson.day] += 1

    total_penalty = 0.0

    for key, lessons_per_day in teacher_days.items():
        total_lessons = sum(lessons_per_day)

        if total_lessons == 0:
            continue

        avg_lessons = total_lessons / 5

        for count in lessons_per_day:
            deviation = count - avg_lessons
            total_penalty += deviation**2

    return total_penalty


def count_group_windows(group_id, schedule):
    days = {}

    for lesson in schedule:
        if lesson.group_id != group_id:
            continue

        key = (lesson.week, lesson.day)

        if key not in days:
            days[key] = set()

        days[key].add(lesson.slot)

    windows = 0

    for slots in days.values():
        if len(slots) <= 1:
            continue

        windows += max(slots) - min(slots) + 1 - len(slots)

    return windows


def group_late_start_penalty(schedule):
    group_days = {}

    for lesson in schedule:
        key = (lesson.group_id, lesson.week, lesson.day)

        if key not in group_days:
            group_days[key] = []

        group_days[key].append(lesson.slot)

    penalty = 0

    for slots in group_days.values():
        first_slot = min(slots)

        penalty += first_slot - 1

    return penalty


def teacher_single_lesson_penalty(schedule):
    teacher_days = {}

    for lesson in schedule:
        key = (lesson.teacher_id, lesson.week, lesson.day)

        teacher_days[key] = teacher_days.get(key, 0) + 1

    return sum(1 for count in teacher_days.values() if count == 1)


def evaluate_schedule(schedule):
    teacher_ids = {x.teacher_id for x in schedule}
    group_ids = {x.group_id for x in schedule}

    teacher_windows = sum(
        count_teacher_windows(teacher_id, schedule) for teacher_id in teacher_ids
    )

    group_windows = sum(
        count_group_windows(group_id, schedule) for group_id in group_ids
    )

    return (
        10 * teacher_windows
        + 10 * group_windows
        + 4 * group_load_penalty(schedule)
        + 2 * teacher_single_lesson_penalty(schedule)
        + 2 * group_late_start_penalty(schedule)
    )


def score_details(schedule):
    teacher_ids = {x.teacher_id for x in schedule}
    group_ids = {x.group_id for x in schedule}

    return {
        "teacher_windows": 10
        * sum(count_teacher_windows(t, schedule) for t in teacher_ids),
        "group_windows": 10 * sum(count_group_windows(g, schedule) for g in group_ids),
        "group_load": 4 * group_load_penalty(schedule),
        "single_lessons": 2 * teacher_single_lesson_penalty(schedule),
        "late_start": 2 * group_late_start_penalty(schedule),
    }
