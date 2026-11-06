"""Local administrator credentials: salted PBKDF2, HTTP Basic over local HTTP/HTTPS."""

import hashlib
import hmac
import json
from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

CREDENTIALS = Path(__file__).resolve().parents[1] / "admin_credentials.json"
security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
    if not CREDENTIALS.exists():
        raise HTTPException(503, "Сначала выполните python setup_admin.py")
    config = json.loads(CREDENTIALS.read_text(encoding="utf-8"))
    digest = hashlib.pbkdf2_hmac(
        "sha256", credentials.password.encode(), bytes.fromhex(config["salt"]), 600000
    ).hex()
    if not (
        hmac.compare_digest(credentials.username.encode(), config["username"].encode())
        and hmac.compare_digest(digest, config["hash"])
    ):
        raise HTTPException(
            401, "Неверный логин или пароль", headers={"WWW-Authenticate": "Basic"}
        )
    return credentials.username
