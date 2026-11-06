import random
from dataclasses import replace
from time import perf_counter

from constraints import can_place_lesson
from models import Lesson, Teacher
from scoring import evaluate_schedule


def swap_lessons(schedule, index_a, index_b, teachers):
    if index_a == index_b:
        return None

    lesson_a = schedule[index_a]
    lesson_b = schedule[index_b]
    if lesson_a.week != lesson_b.week:
        return None
    new_a = replace(lesson_a, week=lesson_b.week, day=lesson_b.day, slot=lesson_b.slot)

    new_b = replace(lesson_b, week=lesson_a.week, day=lesson_a.day, slot=lesson_a.slot)

    remaining = [
        lesson for i, lesson in enumerate(schedule) if i not in (index_a, index_b)
    ]

    if not can_place_lesson(new_a, remaining, teachers):
        return None
    remaining.append(new_a)

    if not can_place_lesson(new_b, remaining, teachers):
        return None
    result = schedule.copy()
    result[index_a] = new_a
    result[index_b] = new_b

    affected_groups = {
        (lesson_a.week, lesson_a.group_id),
        (lesson_b.week, lesson_b.group_id),
    }

    for week, group_id in affected_groups:
        daily_load = [0] * 5

        for lesson in result:
            if lesson.week == week and lesson.group_id == group_id:
                daily_load[lesson.day] += 1

        if any(count < 3 or count > 4 for count in daily_load):
            return None

    return result


def optimize_schedule(
    schedule: list[Lesson],
    teachers: dict[int, Teacher],
    max_iterations: int = 10,
    max_swap_checks: int = 500,
) -> list[Lesson]:

    # Копируем расписание, не изменяя исходное
    best_schedule = schedule.copy()
    best_score = evaluate_schedule(best_schedule)
    rng = random.Random(42)
    total_evaluations = 0
    evaluation_seconds = 0.0

    def measured_score(candidate):
        nonlocal total_evaluations, evaluation_seconds

        started = perf_counter()
        result = evaluate_schedule(candidate)

        evaluation_seconds += perf_counter() - started
        total_evaluations += 1

        return result

    for iteration in range(max_iterations):
        # Лучшее найденное изменение за текущую итерацию
        candidate_schedule = None
        candidate_score = best_score

        # Перебираем каждое занятие
        for index, lesson in enumerate(best_schedule):
            source_day_count = sum(
                1
                for item in best_schedule
                if item.group_id == lesson.group_id
                and item.week == lesson.week
                and item.day == lesson.day
            )
            # Убираем текущее занятие,
            # чтобы оно не конфликтовало само с собой
            remaining_schedule = best_schedule[:index] + best_schedule[index + 1 :]

            # Пробуем все дни и номера пар
            for day in range(5):
                for slot in range(1, 5):
                    # Пропускаем текущее положение
                    if lesson.day == day and lesson.slot == slot:
                        continue
                    if day != lesson.day and source_day_count <= 3:
                        continue
                    # Создаём новое занятие
                    moved_lesson = Lesson(
                        week=lesson.week,
                        day=day,
                        slot=slot,
                        teacher_id=lesson.teacher_id,
                        group_id=lesson.group_id,
                        subject_id=lesson.subject_id,
                    )

                    # Проверяем ограничения
                    if not can_place_lesson(moved_lesson, remaining_schedule, teachers):
                        continue

                    # Создаём вариант расписания с переносом
                    new_schedule = best_schedule.copy()
                    new_schedule[index] = moved_lesson

                    # Оцениваем качество
                    new_score = measured_score(new_schedule)
                    # Запоминаем лучшее изменение
                    if new_score < candidate_score - 1e-9:
                        candidate_score = new_score
                        candidate_schedule = new_schedule

        # SWAP: случайные обмены занятий
        lesson_count = len(best_schedule)

        if lesson_count >= 2:
            for _ in range(max_swap_checks):
                i, j = rng.sample(range(lesson_count), 2)

                lesson_a = best_schedule[i]
                lesson_b = best_schedule[j]

                # Между неделями обмен запрещён
                if lesson_a.week != lesson_b.week:
                    continue

                # Одинаковые позиции не обмениваем
                if lesson_a.day == lesson_b.day and lesson_a.slot == lesson_b.slot:
                    continue

                candidate = swap_lessons(best_schedule, i, j, teachers)

                if candidate is None:
                    continue

                new_score = measured_score(candidate)

                if new_score < candidate_score - 1e-9:
                    candidate_score = new_score
                    candidate_schedule = candidate

        # Если улучшений нет — останавливаем поиск
        if candidate_schedule is None:
            print(
                f"Итерация {iteration + 1}: улучшений среди проверенных вариантов нет"
            )
            break

        best_schedule = candidate_schedule
        best_score = candidate_score
        print(f"Итерация {iteration + 1}: штраф {best_score:.2f}")

    print(f"Проверено кандидатов: {total_evaluations}")
    print(f"Время расчёта штрафов: {evaluation_seconds:.3f} сек.")
    print(f"Итоговый штраф: {best_score:.2f}")
    return best_schedule
