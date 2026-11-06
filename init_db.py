"""Idempotent initialization; existing administrator edits are preserved."""

from import_teachers import import_teachers
from repository import initialize_data

if __name__ == "__main__":
    initialize_data()
    import_teachers()
    print("База готова. Существующие записи не перезаписаны.")
