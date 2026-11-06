from models import Lesson, LessonTask, Requirement, Teacher


def is_teacher_available(teacher: Teacher, day: int) -> bool:
    if day in teacher.methodical_days:
        return False
    return True


def has_teacher_conflict(new_lesson: Lesson, schedule: list[Lesson]) -> bool:
    for lesson in schedule:
        if (
            lesson.week == new_lesson.week
            and lesson.day == new_lesson.day
            and lesson.slot == new_lesson.slot
            and lesson.teacher_id == new_lesson.teacher_id
        ):
            return True
    return False


def has_group_conflict(new_lesson: Lesson, schedule: list[Lesson]) -> bool:
    for lesson in schedule:
        if (
            lesson.week == new_lesson.week
            and lesson.day == new_lesson.day
            and lesson.slot == new_lesson.slot
            and lesson.group_id == new_lesson.group_id
        ):
            return True
    return False


def can_place_lesson(
    new_lesson: Lesson, schedule: list[Lesson], teachers: dict[int, Teacher]
) -> bool:
    # Проверяем существование преподавателя
    teacher = teachers.get(new_lesson.teacher_id)

    if teacher is None:
        return False

    # Проверяем допустимость времени
    if new_lesson.week not in ("A", "B"):
        return False

    if not 0 <= new_lesson.day <= 4:
        return False

    if not 1 <= new_lesson.slot <= 4:
        return False

    # Проверяем методический день
    if not is_teacher_available(teacher, new_lesson.day):
        return False

    # Проверяем конфликты
    if has_teacher_conflict(new_lesson, schedule):
        return False

    if has_group_conflict(new_lesson, schedule):
        return False

    # Считаем количество пар преподавателя за этот день
    daily_lessons = sum(
        1
        for lesson in schedule
        if lesson.teacher_id == new_lesson.teacher_id
        and lesson.week == new_lesson.week
        and lesson.day == new_lesson.day
    )

    if daily_lessons >= teacher.max_lessons_per_day:
        return False

    return True


def expand_requirements(requirements: list[Requirement]) -> list[LessonTask]:
    tasks = []

    for requirement in requirements:
        for _ in range(requirement.lessons_week_a):
            tasks.append(
                LessonTask(
                    week="A",
                    group_id=requirement.group_id,
                    subject_id=requirement.subject_id,
                    teacher_id=requirement.teacher_id,
                )
            )

        for _ in range(requirement.lessons_week_b):
            tasks.append(
                LessonTask(
                    week="B",
                    group_id=requirement.group_id,
                    subject_id=requirement.subject_id,
                    teacher_id=requirement.teacher_id,
                )
            )

    return tasks
