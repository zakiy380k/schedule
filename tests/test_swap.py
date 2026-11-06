from constraints import can_place_lesson
from models import Lesson, Teacher
from optimizer import optimize_schedule, swap_lessons


def test_swap():
    teachers = {i: Teacher(i, str(i), set(), 4) for i in (1, 2, 3)}
    schedule = [Lesson("A", d, s, s, 1, s) for d in range(5) for s in (1, 2, 3)]
    result = swap_lessons(schedule, 0, 1, teachers)
    assert result is not None
    for i, lesson in enumerate(result):
        assert can_place_lesson(lesson, result[:i] + result[i + 1 :], teachers)


def test_no_improvement():
    assert optimize_schedule([], {}, max_iterations=2) == []


def test_optimizer_accepts_improvement():
    from scoring import evaluate_schedule

    teachers = {i: Teacher(i, str(i), set(), 4) for i in (1, 2, 3)}
    schedule = [
        Lesson("A", day, slot, teacher, 1, teacher)
        for day in range(5)
        for slot, teacher in ((1, 1), (2, 2), (4, 3))
    ]
    result = optimize_schedule(schedule, teachers, max_iterations=1, max_swap_checks=0)
    assert evaluate_schedule(result) < evaluate_schedule(schedule)
    assert schedule[2].slot == 4
