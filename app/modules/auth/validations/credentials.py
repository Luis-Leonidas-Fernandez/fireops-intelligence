import re

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 320 or not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Ingresá un correo electrónico válido.")
    return email


def validate_registration_password(value: str) -> str:
    if (
        len(value) < 8
        or len(value) > 128
        or not any(c.isalpha() for c in value)
        or not any(c.isdigit() for c in value)
    ):
        raise ValueError(
            "La contraseña debe tener entre 8 y 128 caracteres, con letras y números."
        )
    return value
