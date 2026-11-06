import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from constraints import expand_requirements
from data_loader import load_calendar, load_csv
from database import get_db
from db_models import TeacherDB
from generator import generate_schedule_fast
from models import Requirement, Teacher
from optimizer import optimize_schedule
from repository import initialize_data
from scoring import (
    count_group_windows,
    count_teacher_windows,
    evaluate_schedule,
    score_details,
)
from validator import validate_schedule
from web.admin import router as admin_router
from web.auth import require_admin
from web.schemas import GenerateRequest, TeacherUpdate
from workload import (
    validate_group_workload,
    validate_teacher_capacity,
    validate_teacher_workload,
)


@asynccontextmanager
async def lifespan(app):
    initialize_data()
    yield


WEB_DIR = Path(__file__).resolve().parent
app = FastAPI(title="College Schedule API", version="0.2.0", lifespan=lifespan)
app.include_router(admin_router)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, error: Exception):
    logging.getLogger(__name__).error(
        "Необработанная ошибка %s",
        request.url.path,
        exc_info=(type(error), error, error.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Внутренняя ошибка сервера. Подробности в терминале Uvicorn."
        },
    )


app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

templates = Jinja2Templates(directory=WEB_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/teachers")
def get_teachers(db: Session = Depends(get_db)):
    teachers = db.scalars(select(TeacherDB).order_by(TeacherDB.id)).all()

    return [
        {
            "id": teacher.id,
            "name": teacher.name,
            "methodical_days": teacher.methodical_days,
            "max_lessons_per_day": teacher.max_lessons_per_day,
            "employment_rate": teacher.employment_rate,
            "annual_load_hours": teacher.annual_load_hours,
        }
        for teacher in teachers
    ]


@app.get("/api/groups")
def get_groups():
    return load_csv("groups.csv")


@app.get("/api/subjects")
def get_subjects():
    return load_csv("subjects.csv")


@app.put("/api/teachers/{teacher_id}", dependencies=[Depends(require_admin)])
def update_teacher(teacher_id: int, data: TeacherUpdate, db: Session = Depends(get_db)):
    teacher = db.get(TeacherDB, teacher_id)

    if teacher is None:
        raise HTTPException(status_code=404, detail="Преподаватель не найден")

    teacher.name = data.name
    teacher.methodical_days = data.methodical_days
    teacher.max_lessons_per_day = data.max_lessons_per_day
    teacher.employment_rate = data.employment_rate
    teacher.annual_load_hours = data.annual_load_hours

    db.commit()

    return {"status": "success", "teacher_id": teacher.id}


@app.post("/api/generate")
def generate_api(data: GenerateRequest, db: Session = Depends(get_db)):

    group_rows = load_csv("groups.csv")
    requirement_rows = load_csv("requirements.csv")

    selected_group_ids = {int(row["id"]) for row in group_rows[: data.group_limit]}

    if not selected_group_ids:
        raise HTTPException(
            422, "Нет групп для генерации. Добавьте группы и нагрузку в админке."
        )

    teacher_rows = db.scalars(select(TeacherDB).order_by(TeacherDB.id)).all()

    if not teacher_rows:
        raise HTTPException(
            status_code=422, detail="В базе нет преподавателей. Выполните импорт."
        )

    teachers = {}

    for row in teacher_rows:
        teacher = Teacher(
            id=row.id,
            name=row.name,
            methodical_days=set(row.methodical_days),
            max_lessons_per_day=row.max_lessons_per_day,
            employment_rate=row.employment_rate,
            annual_load_hours=row.annual_load_hours,
        )

        teachers[teacher.id] = teacher

    requirements = []

    for row in requirement_rows:
        if int(row["group_id"]) not in selected_group_ids:
            continue

        requirements.append(
            Requirement(
                group_id=int(row["group_id"]),
                subject_id=int(row["subject_id"]),
                teacher_id=int(row["teacher_id"]),
                lessons_week_a=int(row["lessons_week_a"]),
                lessons_week_b=int(row["lessons_week_b"]),
            )
        )
    missing_teacher_ids = {
        requirement.teacher_id
        for requirement in requirements
        if requirement.teacher_id not in teachers
    }

    if missing_teacher_ids:
        raise HTTPException(
            status_code=422,
            detail=(
                "В учебном плане указаны отсутствующие преподаватели: "
                + ", ".join(map(str, sorted(missing_teacher_ids)))
            ),
        )
    all_requirements = [
        Requirement(
            **{
                k: int(row[k])
                for k in (
                    "group_id",
                    "subject_id",
                    "teacher_id",
                    "lessons_week_a",
                    "lessons_week_b",
                )
            }
        )
        for row in requirement_rows
    ]
    group_errors = validate_group_workload(selected_group_ids, requirements)
    if group_errors:
        raise HTTPException(
            422, detail={"message": "Проверьте нагрузку групп", "errors": group_errors}
        )
    calendar = load_calendar()
    workload_errors = []

    for teacher in teachers.values():
        result = validate_teacher_workload(
            teacher=teacher,
            requirements=all_requirements,
            week_a_count=calendar["week_a_count"],
            week_b_count=calendar["week_b_count"],
            academic_hours_per_lesson=calendar["tariff_academic_hours_per_lesson"],
        )

        if not result["valid"]:
            workload_errors.append(
                {"teacher_id": teacher.id, "teacher_name": teacher.name, **result}
            )

    if workload_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Генерация отменена: проверьте нагрузку преподавателей",
                "errors": workload_errors,
            },
        )

    capacity_errors = []

    for teacher in teachers.values():
        capacity_errors.extend(validate_teacher_capacity(teacher, all_requirements))

    if capacity_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Недостаточно доступных пар у преподавателей",
                "errors": capacity_errors,
            },
        )
    tasks = expand_requirements(requirements)
    schedule = []

    try:
        success = generate_schedule_fast(tasks, schedule, teachers, time_limit=20.0)
    except TimeoutError as error:
        raise HTTPException(status_code=503, detail=str(error))

    if not success:
        raise HTTPException(status_code=422, detail="Не вдалося зробити росклад")

    score_before = evaluate_schedule(schedule)

    windows_before = sum(
        count_teacher_windows(teacher_id, schedule) for teacher_id in teachers
    )

    group_windows_before = sum(
        count_group_windows(group_id, schedule) for group_id in selected_group_ids
    )

    optimization_started = perf_counter()

    if data.optimize:
        schedule = optimize_schedule(
            schedule, teachers, max_iterations=65, max_swap_checks=500
        )

    optimization_seconds = perf_counter() - optimization_started

    validation_errors = validate_schedule(schedule, requirements, teachers)

    if validation_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Расписание не прошло проверку",
                "errors": validation_errors[:20],
            },
        )

    score_after = evaluate_schedule(schedule)

    windows_after = sum(
        count_teacher_windows(teacher_id, schedule) for teacher_id in teachers
    )

    group_windows_after = sum(
        count_group_windows(group_id, schedule) for group_id in selected_group_ids
    )
    return {
        "status": "success",
        "groups": len(selected_group_ids),
        "lessons_count": len(schedule),
        "optimized": data.optimize,
        "score_before": round(score_before, 2),
        "score_after": round(score_after, 2),
        "windows_before": windows_before,
        "windows_after": windows_after,
        "group_windows_before": group_windows_before,
        "group_windows_after": group_windows_after,
        "optimization_seconds": round(optimization_seconds, 3),
        "workload_status": "within_configured_limits",
        "score_details": score_details(schedule),
        "schedule": [asdict(lesson) for lesson in schedule],
    }
