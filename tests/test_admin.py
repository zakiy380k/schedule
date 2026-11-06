import hashlib
import json
import shutil

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

import database
import repository
import web.auth as auth
from web.app import app

AUTH = ("admin", "test-password")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    shutil.copy2(database.BASE_DIR / "college.db", path)
    engine = create_engine(
        f"sqlite:///{path}", connect_args={"check_same_thread": False}
    )
    database.SessionLocal.configure(bind=engine)
    monkeypatch.setattr(repository, "engine", engine)
    credentials = tmp_path / "auth.json"
    salt = bytes.fromhex("12" * 16)
    credentials.write_text(
        json.dumps(
            {
                "username": "admin",
                "salt": salt.hex(),
                "hash": hashlib.pbkdf2_hmac(
                    "sha256", b"test-password", salt, 600000
                ).hex(),
            }
        )
    )
    monkeypatch.setattr(auth, "CREDENTIALS", credentials)
    with TestClient(app) as c:
        yield c
    database.SessionLocal.configure(bind=database.engine)
    engine.dispose()


def test_auth(client):
    assert client.get("/admin").status_code == 401
    assert client.get("/admin", auth=("admin", "wrong")).status_code == 401
    assert client.get("/admin", auth=AUTH).status_code == 200


def test_teacher(client):
    row = client.get("/api/teachers").json()[0]
    row.update(methodical_days=[1, 4], annual_load_hours=1)
    path = f"/api/admin/data/teachers/{row['id']}"
    assert client.put(path, json=row, auth=AUTH).status_code == 200
    assert client.get("/api/teachers").json()[0]["methodical_days"] == [1, 4]
    assert client.get("/api/admin/validation", auth=AUTH).json()["errors"]
    row["methodical_days"] = [8]
    assert client.put(path, json=row, auth=AUTH).status_code == 422
    assert client.put(f"/api/teachers/{row['id']}", json=row).status_code == 401
    assert client.post("/api/generate", json={"group_limit": 1}).status_code == 422


def test_crud(client):
    r = client.put(
        "/api/admin/data/groups/0", json={"name": "Новая", "course": 2}, auth=AUTH
    )
    assert r.status_code == 200, r.text
    i = r.json()["id"]
    assert any(row["id"] == i for row in client.get("/api/groups").json())
    assert client.delete(f"/api/admin/data/groups/{i}", auth=AUTH).status_code == 200
    assert client.delete("/api/admin/data/groups/1", auth=AUTH).status_code == 409
    bad = {
        "group_id": 99999,
        "subject_id": 1,
        "teacher_id": 1,
        "lessons_week_a": 1,
        "lessons_week_b": 1,
    }
    assert (
        client.put("/api/admin/data/requirements/0", json=bad, auth=AUTH).status_code
        == 422
    )


def test_calendar(client):
    row = client.get("/api/admin/data/calendar", auth=AUTH).json()[0]
    row.update(week_a_count=0, week_b_count=0)
    assert (
        client.put("/api/admin/data/calendar/1", json=row, auth=AUTH).status_code == 422
    )
    row["week_b_count"] = 17
    assert (
        client.put("/api/admin/data/calendar/1", json=row, auth=AUTH).status_code == 200
    )
    assert repository.dataset("calendar")[0]["week_a_count"] == 0


def test_generation(client):
    r = client.post("/api/generate", json={"group_limit": 25, "optimize": False})
    assert r.status_code == 200, r.text
    assert r.json()["lessons_count"] == 784
    from collections import Counter

    counts = Counter((l["group_id"], l["week"], l["day"]) for l in r.json()["schedule"])
    assert len(counts) == 250
    assert set(counts.values()) <= {3, 4}


def test_teacher_creation_and_deletion(client):
    payload = {
        "name": "Тестовый преподаватель",
        "methodical_days": [2],
        "max_lessons_per_day": 3,
        "employment_rate": 1.0,
        "annual_load_hours": 900,
    }
    response = client.put("/api/admin/data/teachers/0", json=payload, auth=AUTH)
    assert response.status_code == 200
    teacher_id = response.json()["id"]
    assert any(row["id"] == teacher_id for row in client.get("/api/teachers").json())
    assert (
        client.delete(f"/api/admin/data/teachers/{teacher_id}", auth=AUTH).status_code
        == 200
    )


def test_import_does_not_restore_intentionally_empty_section(client):
    from sqlalchemy import delete

    from db_models import DataRecord

    with database.SessionLocal.begin() as db:
        db.execute(delete(DataRecord).where(DataRecord.section == "requirements"))
    repository.initialize_data()
    assert repository.dataset("requirements") == []
