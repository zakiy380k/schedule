"""Build a feasible timetable with CP-SAT; improve convenience in optimizer.py.

The public call retains the previous contract: mutate schedule only on success,
return False for proven infeasibility, raise TimeoutError for an unfinished search.
"""
from collections import Counter, defaultdict, deque
import logging
import math
from time import perf_counter

from ortools.sat.python import cp_model

from constraints import can_place_lesson
from models import Lesson, LessonTask, Teacher

logger = logging.getLogger(__name__)


def generate_schedule_fast(
    unassigned_tasks: list[LessonTask],
    schedule: list[Lesson],
    teachers: dict[int, Teacher],
    time_limit: float = 20.0,
) -> bool:
    """Place all remaining tasks, preserving existing lessons and A/B counts.

    Equal tasks share placement variables rather than being permuted as separate
    recursion levels. One solver worker keeps CPU and memory use controlled.
    Annual-hour validation remains the responsibility of workload.py / the API.
    """
    if not math.isfinite(time_limit) or time_limit <= 0:
        raise ValueError("Лимит поиска должен быть положительным конечным числом")
    started = perf_counter()
    deadline = started + time_limit
    tasks = list(unassigned_tasks)
    original = list(schedule)
    demands = Counter((t.week, t.group_id, t.teacher_id, t.subject_id) for t in tasks)
    group_week = Counter()
    teacher_week = Counter()
    teacher_busy = set()
    group_busy = set()
    fixed_teacher_day = Counter()
    fixed_group_day = Counter()

    for item in [*tasks, *original]:
        if item.week not in ("A", "B"):
            raise ValueError("Неделя должна быть A или B")
        teacher = teachers.get(item.teacher_id)
        if teacher is None:
            raise ValueError(f"Преподаватель {item.teacher_id} не найден")
        if not 1 <= teacher.max_lessons_per_day <= 4:
            raise ValueError(f"Некорректный дневной максимум: {teacher.name}")
        if any(day not in range(5) for day in teacher.methodical_days):
            raise ValueError(f"Некорректный методический день: {teacher.name}")
        group_week[item.week, item.group_id] += 1
        teacher_week[item.week, item.teacher_id] += 1

    for index, lesson in enumerate(original):
        if not can_place_lesson(lesson, original[:index] + original[index + 1:], teachers):
            raise ValueError("Уже закреплённые занятия нарушают ограничения")
        teacher_busy.add((lesson.week, lesson.day, lesson.slot, lesson.teacher_id))
        group_busy.add((lesson.week, lesson.day, lesson.slot, lesson.group_id))
        fixed_teacher_day[lesson.week, lesson.day, lesson.teacher_id] += 1
        fixed_group_day[lesson.week, lesson.day, lesson.group_id] += 1

    # Necessary conditions; no expensive search for obvious overloads.
    if any(not 15 <= count <= 20 for count in group_week.values()):
        return False
    for (_, teacher_id), count in teacher_week.items():
        teacher = teachers[teacher_id]
        if count > (5 - len(teacher.methodical_days)) * teacher.max_lessons_per_day:
            return False
    if not tasks:
        return all(3 <= fixed_group_day[week, day, group] <= 4
                   for week, group in group_week for day in range(5))

    if not original:
        return _generate_by_days(tasks, schedule, teachers, demands, group_week, deadline, time_limit)

    model = cp_model.CpModel()
    teacher_slots = defaultdict(list)
    group_slots = defaultdict(list)
    teacher_days = defaultdict(list)
    group_days = defaultdict(list)
    placements = []

    for (week, group, teacher_id, subject), count in sorted(demands.items()):
        if perf_counter() >= deadline:
            raise TimeoutError("Истёк лимит подготовки модели расписания; решение не проверено.")
        teacher = teachers[teacher_id]
        options = []
        for day in range(5):
            if day in teacher.methodical_days:
                continue
            for slot in range(1, 5):
                if (week, day, slot, teacher_id) in teacher_busy:
                    continue
                if (week, day, slot, group) in group_busy:
                    continue
                var = model.new_bool_var(f"{week}_{group}_{teacher_id}_{subject}_{day}_{slot}")
                options.append(var)
                placements.append((var, week, day, slot, teacher_id, group, subject))
                teacher_slots[week, day, slot, teacher_id].append(var)
                group_slots[week, day, slot, group].append(var)
                teacher_days[week, day, teacher_id].append(var)
                group_days[week, day, group].append(var)
        if len(options) < count:
            return False
        model.add(sum(options) == count)

    for options in teacher_slots.values():
        model.add_at_most_one(options)
    for options in group_slots.values():
        model.add_at_most_one(options)
    for (week, day, teacher_id), options in teacher_days.items():
        available = teachers[teacher_id].max_lessons_per_day - fixed_teacher_day[week, day, teacher_id]
        model.add(sum(options) <= available)
    for week, group in sorted(group_week):
        for day in range(5):
            total = sum(group_days[week, day, group]) + fixed_group_day[week, day, group]
            model.add(total >= 3)
            model.add(total <= 4)

    remaining_seconds = deadline - perf_counter()
    if remaining_seconds <= 0:
        raise TimeoutError("Истёк лимит подготовки модели расписания; решение не проверено.")
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = remaining_seconds
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    status = solver.solve(model)
    logger.info("CP-SAT status=%s tasks=%s variables=%s seconds=%.3f",
                solver.status_name(status), len(tasks), len(placements), perf_counter() - started)
    if status == cp_model.INFEASIBLE:
        return False
    if status == cp_model.MODEL_INVALID:
        raise RuntimeError(f"Некорректная модель CP-SAT: {model.validate()}")
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise TimeoutError(
            f"CP-SAT не завершил поиск за {time_limit:g} секунд. "
            "Невозможность расписания не доказана; проверьте нагрузку и ограничения."
        )

    added = [Lesson(week, day, slot, teacher_id, group, subject)
             for var, week, day, slot, teacher_id, group, subject in placements
             if solver.value(var)]
    # Publish a complete result atomically; failures never leave partial lessons.
    schedule.extend(added)
    return True


def generate_schedule(unassigned_tasks, schedule, teachers):
    """Compatibility entry point for old console tools."""
    return generate_schedule_fast(unassigned_tasks, schedule, teachers)


def _generate_by_days(tasks, schedule, teachers, demands, group_week, deadline, time_limit):
    """First assign days, then edge-color each teacher/group bipartite graph.

    A bipartite multigraph of maximum degree four admits a four-edge coloring.
    Thus every feasible day assignment can be converted to conflict-free slots.
    This decomposition is valid because there are no per-slot availabilities,
    rooms, or fixed lessons in this branch. Fixed lessons use the full model.
    """
    model = cp_model.CpModel()
    counts = Counter()
    subjects = defaultdict(deque)
    for (week, group, teacher, subject), count in sorted(demands.items()):
        counts[week, group, teacher] += count
        subjects[week, group, teacher].extend([subject] * count)
    group_days = defaultdict(list)
    teacher_days = defaultdict(list)
    variables = []
    for (week, group, teacher_id), count in sorted(counts.items()):
        options = []
        for day in range(5):
            if day in teachers[teacher_id].methodical_days:
                continue
            var = model.new_int_var(0, min(count, teachers[teacher_id].max_lessons_per_day),
                                    f"{week}_{group}_{teacher_id}_{day}")
            options.append(var)
            variables.append((var, week, day, teacher_id, group))
            group_days[week, day, group].append(var)
            teacher_days[week, day, teacher_id].append(var)
        model.add(sum(options) == count)
    for week, group in sorted(group_week):
        for day in range(5):
            total = sum(group_days[week, day, group])
            model.add(total >= 3)
            model.add(total <= 4)
    for (_, _, teacher_id), options in teacher_days.items():
        model.add(sum(options) <= teachers[teacher_id].max_lessons_per_day)
    remaining = deadline - perf_counter()
    if remaining <= 0:
        raise TimeoutError("Истёк лимит подготовки модели расписания")
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = remaining
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    status = solver.solve(model)
    if status == cp_model.INFEASIBLE:
        return False
    if status == cp_model.MODEL_INVALID:
        raise RuntimeError(f"Некорректная модель: {model.validate()}")
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise TimeoutError(f"Не найдено решение за {time_limit:g} секунд; невозможность не доказана")
    days = defaultdict(Counter)
    for var, week, day, teacher, group in variables:
        amount = solver.value(var)
        if amount:
            days[week, day][teacher, group] += amount
    added = []
    for (week, day), edges in sorted(days.items()):
        if perf_counter() >= deadline:
            raise TimeoutError("Истёк лимит составления расписания; частичный результат не сохранён")
        coloring = _color_day(edges)
        # A valid coloring is already available. A short optional refinement
        # improves gaps without risking loss of that feasible timetable.
        budget = min(0.2, max(0.0, deadline - perf_counter() - 0.05))
        if budget > 0.01:
            coloring = _refine_day(edges, coloring, budget)
        for teacher, group, slot in coloring:
            subject = subjects[week, group, teacher].popleft()
            added.append(Lesson(week, day, slot, teacher, group, subject))
    if len(added) != len(tasks) or any(subjects.values()):
        raise RuntimeError("Ошибка сохранения нагрузки при назначении слотов")
    schedule.extend(added)
    logger.info("CP-SAT/day-coloring tasks=%s day_variables=%s", len(tasks), len(variables))
    return True


def _color_day(real_edges):
    """Four perfect matchings of a padded 4-regular bipartite multigraph.

    A vertex on the left is a teacher, on the right a group. Each real edge is
    one lesson. Dummy edges fill missing degrees and are discarded afterwards.
    Using maximum matchings without regularization would not suffice: an early
    arbitrary matching could leave degree four with only three slots remaining.
    """
    people = sorted({t for t, _ in real_edges})
    groups = sorted({g for _, g in real_edges})
    n = max(len(people), len(groups))
    if not n:
        return []
    teacher_index = {t: i for i, t in enumerate(people)}
    group_index = {g: i for i, g in enumerate(groups)}
    real = Counter({(teacher_index[t], group_index[g]): count
                    for (t, g), count in real_edges.items()})
    edges = real.copy()
    left_degree = Counter()
    right_degree = Counter()
    for (left, right), count in edges.items():
        left_degree[left] += count
        right_degree[right] += count
    if any(v > 4 for v in [*left_degree.values(), *right_degree.values()]):
        raise RuntimeError("Дневная нагрузка превышает четыре слота")
    right = 0
    for left in range(n):
        while left_degree[left] < 4:
            while right_degree[right] == 4:
                right += 1
            amount = min(4 - left_degree[left], 4 - right_degree[right])
            edges[left, right] += amount
            left_degree[left] += amount
            right_degree[right] += amount
    result = []
    for slot in range(1, 5):
        matched = {}
        def augment(left, seen):
            neighbors = sorted((r for (l, r), c in edges.items() if l == left and c),
                               key=lambda r: (not real[left, r], r))
            for right in neighbors:
                if right in seen:
                    continue
                seen.add(right)
                if right not in matched or augment(matched[right], seen):
                    matched[right] = left
                    return True
            return False
        for left in range(n):
            if not augment(left, set()):
                raise RuntimeError("Не найдено совершенное паросочетание")
        for right, left in matched.items():
            edges[left, right] -= 1
            if real[left, right]:
                real[left, right] -= 1
                result.append((people[left], groups[right], slot))
    if any(real.values()):
        raise RuntimeError("Не все занятия получили номер пары")
    return result


def _refine_day(edges, initial, seconds):
    """Improve only slot placement with the graph solution as a safe fallback."""
    model = cp_model.CpModel()
    slots = {}
    by_teacher = defaultdict(list)
    by_group = defaultdict(list)
    hints = set(initial)
    for (teacher, group), count in sorted(edges.items()):
        options = []
        for slot in range(1, 5):
            var = model.new_bool_var(f"s_{teacher}_{group}_{slot}")
            slots[teacher, group, slot] = var
            options.append(var)
            by_teacher[teacher, slot].append(var)
            by_group[group, slot].append(var)
            model.add_hint(var, int((teacher, group, slot) in hints))
        model.add(sum(options) == count)
    penalties = []
    for kind, index in (("teacher", by_teacher), ("group", by_group)):
        people = sorted({person for person, _ in index})
        for person in people:
            occupied = []
            for slot in range(1, 5):
                occ = model.new_bool_var(f"{kind}_{person}_{slot}")
                model.add(sum(index[person, slot]) == occ)
                occupied.append(occ)
            for slot in (1, 2):
                before = model.new_bool_var(f"before_{kind}_{person}_{slot}")
                after = model.new_bool_var(f"after_{kind}_{person}_{slot}")
                hole = model.new_bool_var(f"hole_{kind}_{person}_{slot}")
                model.add_max_equality(before, occupied[:slot])
                model.add_max_equality(after, occupied[slot+1:])
                model.add(hole >= before + after - occupied[slot] - 1)
                penalties.append(10 * hole)
            if kind == "group":
                penalties.append(2 * (1 - occupied[0]))
    model.minimize(sum(penalties))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = 1
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return initial
    result = [(t, g, s) for (t, g, s), var in slots.items() if solver.value(var)]
    def quality(coloring):
        result = 0
        for position in (0, 1):
            people = defaultdict(set)
            for teacher, group, slot in coloring:
                people[(teacher, group)[position]].add(slot)
            for values in people.values():
                result += 10 * (max(values) - min(values) + 1 - len(values))
                if position == 1:
                    result += 2 * (min(values) - 1)
        return result
    return result if quality(result) < quality(initial) else initial

