"""Single database source for editable datasets; CSV is only the initial import."""

import csv
import json

from sqlalchemy import select

from database import BASE_DIR, Base, SessionLocal, engine
from db_models import DataRecord, DataSection

SECTIONS = ("groups", "subjects", "requirements", "calendar")


def initialize_data():
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as db:
        for section in SECTIONS:
            if db.get(DataSection, section):
                continue
            path = (
                BASE_DIR
                / "data"
                / (section + (".json" if section == "calendar" else ".csv"))
            )
            if section == "calendar":
                rows = [json.loads(path.read_text(encoding="utf-8-sig"))]
            else:
                with path.open(encoding="utf-8-sig", newline="") as stream:
                    rows = list(csv.DictReader(stream))
            for index, row in enumerate(rows, 1):
                row_id = int(row.get("id", index))
                db.add(DataRecord(section=section, id=row_id, payload=row))
            db.add(DataSection(name=section))


def dataset(section):
    with SessionLocal() as db:
        return [
            dict(row.payload, id=row.id)
            for row in db.scalars(
                select(DataRecord)
                .where(DataRecord.section == section)
                .order_by(DataRecord.id)
            )
        ]
