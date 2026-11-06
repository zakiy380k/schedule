from collections import Counter
from time import perf_counter

from constraints import can_place_lesson
from models import Lesson, LessonTask, Teacher


def generate_schedule(
    unassigned_tasks: list[LessonTask],
    schedule: list[Lesson],
    teachers: dict[int, Teacher],
) -> bool:

    # Если все занятия распределены — расписание готово
    if not unassigned_tasks:
        return True

    # Берём первое нераспределённое занятие
    current_task = unassigned_tasks[0]

    # Перебираем учебные дни: Пн–Пт
    for day in range(5):
        # Перебираем пары: 1–4
        for slot in range(1, 5):
            # Создаём занятие с конкретным временем
            new_lesson = Lesson(
                week=current_task.week,
                day=day,
                slot=slot,
                teacher_id=current_task.teacher_id,
                group_id=current_task.group_id,
                subject_id=current_task.subject_id,
            )

            # Проверяем все ограничения
            if not can_place_lesson(new_lesson, schedule, teachers):
                continue

            # Временно добавляем занятие
            schedule.append(new_lesson)

            # Пробуем разместить остальные занятия
            if generate_schedule(unassigned_tasks[1:], schedule, teachers):
                return True

            # Если решение не найдено — отменяем размещение
            schedule.pop()

    # Ни один вариант не подошёл
    return False


def generate_schedule_fast(
    unassigned_tasks: list[LessonTask],
    schedule: list[Lesson],
    teachers: dict[int, Teacher],
    time_limit: float = 20.0,
) -> bool:
    deadline = perf_counter() + time_limit
    initial_length = len(schedule)

    teacher_busy = set()
    group_busy = set()
    teacher_daily = Counter()
    group_daily = Counter()

    tasks = list(unassigned_tasks)
    remaining = Counter((t.week, t.group_id) for t in tasks)

    group_weeks = set(remaining)
    group_weeks.update((l.week, l.group_id) for l in schedule)

    for lesson in schedule:
        teacher_busy.add((lesson.week, lesson.day, lesson.slot, lesson.teacher_id))
        group_busy.add((lesson.week, lesson.day, lesson.slot, lesson.group_id))
        teacher_daily[(lesson.week, lesson.day, lesson.teacher_id)] += 1
        group_daily[(lesson.week, lesson.day, lesson.group_id)] += 1

    def positions(task):
        teacher = teachers.get(task.teacher_id)
        if teacher is None:
            return []

        result = []

        for day in range(5):
            if day in teacher.methodical_days:
                continue

            teacher_key = (task.week, day, task.teacher_id)
            group_key = (task.week, day, task.group_id)

            if teacher_daily[teacher_key] >= teacher.max_lessons_per_day:
                continue

            if group_daily[group_key] >= 4:
                continue

            for slot in range(1, 5):
                if (task.week, day, slot, task.teacher_id) in teacher_busy:
                    continue

                if (task.week, day, slot, task.group_id) in group_busy:
                    continue

                result.append((day, slot))

        # Сначала заполняем дни, где у группы меньше занятий.
        result.sort(
            key=lambda p: (group_daily[(task.week, p[0], task.group_id)], p[1], p[0])
        )
        return result

    def group_can_finish(week, group_id):
        counts = [group_daily[(week, day, group_id)] for day in range(5)]

        needed = sum(max(0, 3 - count) for count in counts)
        free = sum(4 - count for count in counts)
        left = remaining[(week, group_id)]

        return needed <= left <= free

    def search():
        if perf_counter() >= deadline:
            raise TimeoutError(
                f"За {time_limit:g} секунд расписание не найдено. "
                "Это не означает, что решения нет."
            )

        if not tasks:
            return all(
                group_can_finish(week, group_id) for week, group_id in group_weeks
            )

        best_index = None
        best_positions = None
        checked = set()

        # Сначала выбираем занятие с минимумом доступных позиций.
        for index, task in enumerate(tasks):
            if perf_counter() >= deadline:
                raise TimeoutError(
                    f"За {time_limit:g} секунд расписание не найдено. "
                    "Это не означает, что решения нет."
                )

            # У одинаковых преподавателя и группы варианты одинаковые.
            key = (task.week, task.group_id, task.teacher_id)
            if key in checked:
                continue
            checked.add(key)

            options = positions(task)

            if not options:
                return False

            if best_positions is None or len(options) < len(best_positions):
                best_index = index
                best_positions = options

            if len(options) == 1:
                break

        task = tasks.pop(best_index)
        remaining[(task.week, task.group_id)] -= 1

        for day, slot in best_positions:
            teacher_slot = (task.week, day, slot, task.teacher_id)
            group_slot = (task.week, day, slot, task.group_id)
            teacher_day = (task.week, day, task.teacher_id)
            group_day = (task.week, day, task.group_id)

            lesson = Lesson(
                week=task.week,
                day=day,
                slot=slot,
                teacher_id=task.teacher_id,
                group_id=task.group_id,
                subject_id=task.subject_id,
            )

            schedule.append(lesson)
            teacher_busy.add(teacher_slot)
            group_busy.add(group_slot)
            teacher_daily[teacher_day] += 1
            group_daily[group_day] += 1

            if group_can_finish(task.week, task.group_id) and search():
                return True

            schedule.pop()
            teacher_busy.remove(teacher_slot)
            group_busy.remove(group_slot)
            teacher_daily[teacher_day] -= 1
            group_daily[group_day] -= 1

        remaining[(task.week, task.group_id)] += 1
        tasks.insert(best_index, task)
        return False

    if not all(group_can_finish(w, g) for w, g in group_weeks):
        return False

    try:
        return search()
    except TimeoutError:
        del schedule[initial_length:]
        raise
