"""Create or reset the local administrator password interactively."""

import getpass
import hashlib
import json
import secrets

from web.auth import CREDENTIALS

if __name__ == "__main__":
    username = input("Логин [admin]: ").strip() or "admin"
    password = getpass.getpass("Пароль (минимум 10 символов): ")
    if len(password) < 10:
        raise SystemExit("Слишком короткий пароль")
    if password != getpass.getpass("Повторите пароль: "):
        raise SystemExit("Пароли не совпадают")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000).hex()
    CREDENTIALS.write_text(
        json.dumps({"username": username, "salt": salt.hex(), "hash": digest}),
        encoding="utf-8",
    )
    print("Готово. Откройте /admin. На внешнем сервере используйте HTTPS.")
