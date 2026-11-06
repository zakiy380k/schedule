from dataclasses import dataclass


@dataclass
class Teacher:
    id: int
    name: str
    methodical_days: set[int]
    max_lessons_per_day: int = 4
    employment_rate: float = 1.0
    annual_load_hours: float | None = None


@dataclass
class Lesson:
    week: str
    day: int
    slot: int
    teacher_id: int
    group_id: int
    subject_id: int


@dataclass
class Requirement:
    group_id: int
    subject_id: int
    teacher_id: int
    lessons_week_a: int
    lessons_week_b: int


@dataclass
class LessonTask:
    week: str
    group_id: int
    subject_id: int
    teacher_id: int
