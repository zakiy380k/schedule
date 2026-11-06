"""Authenticated administration API and source-data validation."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from db_models import DataRecord, TeacherDB
from models import Requirement, Teacher
from repository import dataset
from web.auth import require_admin
from web.schemas import TeacherUpdate
from workload import (
    validate_group_workload,
    validate_teacher_capacity,
    validate_teacher_workload,
)

router = APIRouter(dependencies=[Depends(require_admin)])
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


class GroupInput(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    course: int = Field(ge=1, le=6)
    program: str = ""


class SubjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    program: str = ""
    allowed_location_ids: str = ""


class RequirementInput(BaseModel):
    group_id: int = Field(gt=0)
    subject_id: int = Field(gt=0)
    teacher_id: int = Field(gt=0)
    lessons_week_a: int = Field(ge=0, le=20)
    lessons_week_b: int = Field(ge=0, le=20)


class CalendarInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    academic_year: str = Field(min_length=1)
    week_a_count: int = Field(ge=0, le=53)
    week_b_count: int = Field(ge=0, le=53)
    lesson_duration_minutes: int = Field(gt=0, le=240)
    tariff_academic_hours_per_lesson: float = Field(gt=0, le=10)


SCHEMAS = {
    "groups": GroupInput,
    "subjects": SubjectInput,
    "requirements": RequirementInput,
    "calendar": CalendarInput,
}


def teacher_dict(t):
    return {
        key: getattr(t, key)
        for key in (
            "id",
            "name",
            "methodical_days",
            "max_lessons_per_day",
            "employment_rate",
            "annual_load_hours",
        )
    }


@router.get("/admin", response_class=HTMLResponse)
def page(request: Request):
    return templates.TemplateResponse(request=request, name="admin.html")


@router.get("/api/admin/data/{section}")
def read_section(section: str, db: Session = Depends(get_db)):
    if section == "teachers":
        return [
            teacher_dict(t)
            for t in db.scalars(select(TeacherDB).order_by(TeacherDB.id))
        ]
    if section not in SCHEMAS:
        raise HTTPException(404, "Раздел не найден")
    return dataset(section)


@router.put("/api/admin/data/{section}/{row_id}")
def save_row(section: str, row_id: int, payload: dict, db: Session = Depends(get_db)):
    if row_id < 0:
        raise HTTPException(422, "Некорректный ID")
    schema = TeacherUpdate if section == "teachers" else SCHEMAS.get(section)
    if schema is None:
        raise HTTPException(404, "Раздел не найден")
    try:
        values = schema.model_validate(payload).model_dump()
    except ValidationError as error:
        raise HTTPException(422, error.errors(include_context=False))
    if "name" in values:
        values["name"] = values["name"].strip()
        if not values["name"]:
            raise HTTPException(422, "Название не может быть пустым")
    if section == "calendar":
        row_id = 1
        if values["week_a_count"] + values["week_b_count"] == 0:
            raise HTTPException(422, "Нужна хотя бы одна учебная неделя")
    if section == "requirements":
        for target, key in (("groups", "group_id"), ("subjects", "subject_id")):
            if db.get(DataRecord, (target, values[key])) is None:
                raise HTTPException(422, f"Отсутствует {key}")
        if db.get(TeacherDB, values["teacher_id"]) is None:
            raise HTTPException(422, "Преподаватель не найден")
        if values["lessons_week_a"] + values["lessons_week_b"] == 0:
            raise HTTPException(422, "Укажите хотя бы одну пару")
    if section == "teachers":
        if row_id == 0:
            row_id = (db.scalar(select(func.max(TeacherDB.id))) or 0) + 1
            row = TeacherDB(id=row_id, **values)
            db.add(row)
        else:
            row = db.get(TeacherDB, row_id)
            if row is None:
                raise HTTPException(404, "Преподаватель не найден")
            for key, value in values.items():
                setattr(row, key, value)
    else:
        if row_id == 0:
            row_id = (
                db.scalar(
                    select(func.max(DataRecord.id)).where(DataRecord.section == section)
                )
                or 0
            ) + 1
            row = None
        else:
            row = db.get(DataRecord, (section, row_id))
            if row is None:
                raise HTTPException(404, "Запись не найдена")
        # Keep imported metadata not exposed in the editor.
        merged = dict(row.payload) if row else {}
        merged.update(values)
        merged["id"] = row_id
        if row:
            row.payload = merged
        else:
            db.add(DataRecord(section=section, id=row_id, payload=merged))
    db.commit()
    return {"status": "success", "id": row_id}


@router.delete("/api/admin/data/{section}/{row_id}")
def delete_row(section: str, row_id: int, db: Session = Depends(get_db)):
    if section not in (*SCHEMAS, "teachers") or section == "calendar":
        raise HTTPException(422, "Этот раздел нельзя удалить")
    if section in ("teachers", "groups", "subjects"):
        key = {
            "teachers": "teacher_id",
            "groups": "group_id",
            "subjects": "subject_id",
        }[section]
        if any(int(r[key]) == row_id for r in dataset("requirements")):
            raise HTTPException(
                409,
                "Запись используется в учебной нагрузке. Сначала измените назначения.",
            )
    row = (
        db.get(TeacherDB, row_id)
        if section == "teachers"
        else db.get(DataRecord, (section, row_id))
    )
    if row is None:
        raise HTTPException(404, "Запись не найдена")
    db.delete(row)
    db.commit()
    return {"status": "success"}


@router.get("/api/admin/validation")
def validation(db: Session = Depends(get_db)):
    calendar = dataset("calendar")[0]
    requirements = [
        Requirement(
            **{
                k: int(r[k])
                for k in (
                    "group_id",
                    "subject_id",
                    "teacher_id",
                    "lessons_week_a",
                    "lessons_week_b",
                )
            }
        )
        for r in dataset("requirements")
    ]
    errors = []
    reports = []
    groups = {int(g["id"]) for g in dataset("groups")}
    subjects = {int(s["id"]) for s in dataset("subjects")}
    people = list(db.scalars(select(TeacherDB)))
    teacher_ids = {t.id for t in people}
    for r in requirements:
        if (
            r.group_id not in groups
            or r.subject_id not in subjects
            or r.teacher_id not in teacher_ids
        ):
            errors.append("Учебный план содержит ссылку на отсутствующую запись")
    if errors:
        return {"errors": errors, "teachers": []}
    for row in people:
        teacher = Teacher(
            row.id,
            row.name,
            set(row.methodical_days),
            row.max_lessons_per_day,
            row.employment_rate,
            row.annual_load_hours,
        )
        report = validate_teacher_workload(
            teacher,
            requirements,
            int(calendar["week_a_count"]),
            int(calendar["week_b_count"]),
            float(calendar["tariff_academic_hours_per_lesson"]),
        )
        if not report["valid"]:
            errors.append(f"{row.name}: {report['message']}")
        errors.extend(validate_teacher_capacity(teacher, requirements))
        reports.append({"id": row.id, "name": row.name, **report})
    errors.extend(validate_group_workload(groups, requirements))
    return {
        "errors": errors,
        "teachers": reports,
        "calendar_status": calendar.get(
            "tariff_coefficient_status", "Настройки администратора"
        ),
    }
