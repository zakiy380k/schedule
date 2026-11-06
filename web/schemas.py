from pydantic import BaseModel, Field, field_validator


class GenerateRequest(BaseModel):
    group_limit: int = Field(default=5, ge=1, le=25)
    optimize: bool = False


class TeacherUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    methodical_days: list[int] = Field(default_factory=list)
    max_lessons_per_day: int = Field(ge=1, le=4)
    employment_rate: float = Field(gt=0, allow_inf_nan=False)
    annual_load_hours: float = Field(ge=0, allow_inf_nan=False)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Имя не может быть пустым")

        return value

    @field_validator("methodical_days")
    @classmethod
    def validate_methodical_days(cls, value: list[int]) -> list[int]:
        if any(day not in range(5) for day in value):
            raise ValueError("Методические дни должны быть от 0 до 4")

        return sorted(set(value))
