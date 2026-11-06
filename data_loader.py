"""Read simulated college test data. Use with models.py in the same directory."""

import csv
from pathlib import Path

from models import Requirement, Teacher

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


def load_csv(filename: str) -> list[dict]:
    if filename in ("groups.csv", "subjects.csv", "requirements.csv"):
        from repository import dataset

        return dataset(filename[:-4])
    file_path = DATA_DIR / filename

    with file_path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def load_dataset(data_dir="data", group_limit=None):
    directory = Path(data_dir)
    groups = read_rows(directory / "groups.csv")
    if group_limit is not None:
        groups = groups[:group_limit]
    group_ids = {int(row["id"]) for row in groups}
    subjects = read_rows(directory / "subjects.csv")
    subject_ids = {int(row["id"]) for row in subjects}
    people = read_rows(directory / "teachers.csv")
    teachers = {}
    metadata = {}
    for row in people:
        teacher_id = int(row["id"])
        days = {int(day) for day in row["methodical_days"].split(";") if day.strip()}
        if any(day not in range(5) for day in days):
            raise ValueError(f"Invalid methodical day for teacher {teacher_id}")
        teachers[teacher_id] = Teacher(
            id=teacher_id,
            name=row["name"],
            methodical_days=days,
            max_lessons_per_day=int(row["max_lessons_per_day"]),
        )
        metadata[teacher_id] = {
            "employment_rate": float(row["employment_rate"]),
            "annual_load_hours": float(row["annual_load_hours"]),
            "preferred_lessons_per_day": int(row["preferred_lessons_per_day"]),
        }
    requirements = []
    for row in read_rows(directory / "requirements.csv"):
        group_id = int(row["group_id"])
        if group_id not in group_ids:
            continue
        teacher_id = int(row["teacher_id"])
        subject_id = int(row["subject_id"])
        a = int(row["lessons_week_a"])
        b = int(row["lessons_week_b"])
        if teacher_id not in teachers or subject_id not in subject_ids or min(a, b) < 0:
            raise ValueError(f"Bad requirement: {row}")
        requirements.append(Requirement(group_id, subject_id, teacher_id, a, b))
    return groups, subjects, teachers, metadata, requirements


def load_calendar() -> dict:
    from repository import dataset

    rows = dataset("calendar")
    if not rows:
        raise ValueError("Календарь не настроен")
    return rows[0]
