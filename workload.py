from models import Requirement, Teacher


def count_teacher_lessons(
    teacher_id: int, requirements: list[Requirement]
) -> dict[str, int]:
    week_a = 0
    week_b = 0
    lessons = {"A": None, "B": None, "total": None}
    for requirement in requirements:
        if requirement.teacher_id == teacher_id:
            week_a += requirement.lessons_week_a
            week_b += requirement.lessons_week_b
    lessons["A"] = week_a
    lessons["B"] = week_b
    lessons["total"] = week_a + week_b

    return lessons


def calculate_annual_load(
    teacher_id: int,
    requirements: list[Requirement],
    week_a_count: int,
    week_b_count: int,
    academic_hours_per_lesson: float,
) -> float:

    if week_a_count < 0 or week_b_count < 0:
        raise ValueError("Количество недель не может быть отрицательным")
    if week_a_count + week_b_count == 0:
        raise ValueError("Должна быть хоть одна учебная неделя")
    if academic_hours_per_lesson <= 0:
        raise ValueError("Колво часов за пару должно быть больше нуля")

    lessons = count_teacher_lessons(teacher_id, requirements)

    annual_lesson = lessons["A"] * week_a_count + lessons["B"] * week_b_count

    return annual_lesson * academic_hours_per_lesson


def validate_teacher_workload(
    teacher: Teacher,
    requirements: list[Requirement],
    week_a_count: int,
    week_b_count: int,
    academic_hours_per_lesson: float | None,
) -> dict:

    # Без подтверждённого коэффициента расчёт невозможен
    if academic_hours_per_lesson is None:
        return {
            "valid": False,
            "status": "unknown",
            "message": "Неизвестно количество тарификационных часов за пару",
        }

    # Используем явно установленный годовой лимит
    if teacher.annual_load_hours is None:
        return {
            "valid": False,
            "status": "unknown",
            "message": "Не установлена годовая нагрузка преподавателя",
        }

    # Рассчитываем количество часов за год
    annual_hours = calculate_annual_load(
        teacher_id=teacher.id,
        requirements=requirements,
        week_a_count=week_a_count,
        week_b_count=week_b_count,
        academic_hours_per_lesson=academic_hours_per_lesson,
    )

    limit = teacher.annual_load_hours
    exceeded_by = max(0.0, annual_hours - limit)

    valid = exceeded_by <= 1e-9

    return {
        "valid": valid,
        "status": "valid" if valid else "exceeded",
        "annual_hours": annual_hours,
        "limit": limit,
        "exceeded_by": exceeded_by,
        "message": (
            "Годовая нагрузка в пределах лимита"
            if valid
            else f"Превышена годовая нагрузка на {exceeded_by:.2f} ч"
        ),
    }


def validate_teacher_capacity(
    teacher: Teacher, requirements: list[Requirement]
) -> list[str]:
    lessons = count_teacher_lessons(teacher.id, requirements)

    available_days = 5 - len(teacher.methodical_days)
    daily_capacity = min(teacher.max_lessons_per_day, 4)
    weekly_capacity = available_days * daily_capacity

    errors = []

    for week in ("A", "B"):
        if lessons[week] > weekly_capacity:
            errors.append(
                f"{teacher.name}: неделя {week}, "
                f"назначено {lessons[week]} пар, "
                f"можно разместить максимум {weekly_capacity}"
            )

    return errors


def validate_group_workload(
    group_ids: set[int], requirements: list[Requirement]
) -> list[str]:
    weekly_load = {group_id: {"A": 0, "B": 0} for group_id in group_ids}

    for requirement in requirements:
        weekly_load[requirement.group_id]["A"] += requirement.lessons_week_a
        weekly_load[requirement.group_id]["B"] += requirement.lessons_week_b

    errors = []

    for group_id, weeks in weekly_load.items():
        for week, count in weeks.items():
            if not 15 <= count <= 20:
                errors.append(
                    f"Группа {group_id}: неделя {week}, "
                    f"назначено {count} пар, требуется от 15 до 20"
                )

    return errors
