from data_loader import load_csv
from database import SessionLocal
from db_models import TeacherDB


def import_teachers():
    rows = load_csv("teachers.csv")
    added = 0
    skipped = 0

    with SessionLocal() as session:
        with session.begin():
            for row in rows:
                teacher_id = int(row["id"])

                if session.get(TeacherDB, teacher_id) is not None:
                    skipped += 1
                    continue

                methodical_days = sorted(
                    {
                        int(day)
                        for day in row["methodical_days"].split(";")
                        if day.strip()
                    }
                )

                if any(day not in range(5) for day in methodical_days):
                    raise ValueError(
                        f"Преподаватель {teacher_id}: "
                        "методические дни должны быть от 0 до 4"
                    )

                name = row["name"].strip()

                if not name:
                    raise ValueError(f"Преподаватель {teacher_id}: пустое имя")

                teacher = TeacherDB(
                    id=teacher_id,
                    name=name,
                    methodical_days=methodical_days,
                    max_lessons_per_day=int(row["max_lessons_per_day"]),
                    employment_rate=float(row["employment_rate"]),
                    annual_load_hours=float(row["annual_load_hours"]),
                )

                session.add(teacher)
                added += 1

    print(f"Добавлено: {added}, пропущено: {skipped}")


if __name__ == "__main__":
    import_teachers()
