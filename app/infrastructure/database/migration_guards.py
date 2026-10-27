"""Fail-closed migration target validation guards for Alembic."""

import os
from sqlalchemy.engine import make_url

from app.config.settings import Settings

PROTECTED_DATABASES = frozenset({"fireassets", "postgres", "template0", "template1"})


class MigrationTargetError(RuntimeError):
    """Raised when an Alembic execution targets a prohibited or unconfirmed database."""

    pass


def validate_migration_target(settings: Settings) -> str:
    """Validate Alembic migration target database and enforce fail-closed safety guards.

    Returns the validated database name if permitted.
    Raises MigrationTargetError if the target is prohibited or lacks explicit dual-confirmation.
    """
    raw_url = settings.database_url
    if not raw_url:
        raise MigrationTargetError("DATABASE_URL no está configurada.")

    try:
        url = make_url(raw_url)
    except Exception as e:
        raise MigrationTargetError(f"DATABASE_URL no es una URL de conexión válida: {e}") from e

    database_name = url.database
    if not database_name:
        raise MigrationTargetError(
            f"DATABASE_URL no especifica una base de datos válida: {raw_url}"
        )

    env_name = (settings.environment or "").strip().lower()
    env_file = os.getenv("ENV_FILE", "").strip()

    is_protected = database_name in PROTECTED_DATABASES

    # Discrepancia peligrosa 1: Entorno productivo apuntando a base de test
    if env_name == "production" and ("test" in database_name.lower()):
        raise MigrationTargetError(
            f"DISCREPANCIA PELIGROSA: ENVIRONMENT='production' pero la base seleccionada es '{database_name}' (contiene 'test'). "
            "Se aborta para evitar aplicar migraciones productivas a una base de pruebas."
        )

    # Discrepancia peligrosa 2: Entorno development/test apuntando a base protegida (fireassets)
    if env_name in ("development", "test") and is_protected:
        raise MigrationTargetError(
            f"DISCREPANCIA PELIGROSA: ENVIRONMENT='{env_name}' pero la base seleccionada es protegida ('{database_name}'). "
            "Se prohíbe operar sobre bases protegidas desde entornos declarados como desarrollo o pruebas."
        )

    # Discrepancia peligrosa 3: Invocación con .env.test pero apuntando a otra base
    if env_file == ".env.test" and database_name != "fireassets_test":
        raise MigrationTargetError(
            f"DISCREPANCIA PELIGROSA: ENV_FILE='.env.test' pero la base seleccionada es '{database_name}' "
            "(se esperaba estrictamente 'fireassets_test')."
        )

    # Reglas para base de producción / protegida (fireassets)
    if is_protected:
        # Exigir selección explícita de archivo .env de producción
        if env_file != ".env" and not os.path.basename(env_file).startswith(".env.prod"):
            raise MigrationTargetError(
                f"BLOQUEO FAIL-CLOSED: La base de datos '{database_name}' es de producción. "
                "Para migrarla, debe especificarse explícitamente el archivo de entorno productivo (ej. ENV_FILE='.env'). "
                "La ejecución por omisión sin ENV_FILE está bloqueada."
            )

        # Exigir que el entorno sea producción
        if env_name != "production":
            raise MigrationTargetError(
                f"BLOQUEO FAIL-CLOSED: La base '{database_name}' requiere ENVIRONMENT='production' "
                f"(detectado: '{env_name}')."
            )

        # Mecanismo documentado de confirmación dual: variable de autorización + nombre exacto de la base
        allow_prod = (
            os.getenv("ALLOW_PRODUCTION_MIGRATIONS", "").strip().lower()
            in ("1", "true", "yes")
        )
        confirm_db = os.getenv("CONFIRM_PRODUCTION_DATABASE", "").strip()

        if not allow_prod:
            raise MigrationTargetError(
                f"🛑 OPERACIÓN BLOQUEADA: Intento de ejecutar operaciones de migración sobre la base de producción '{database_name}'.\n"
                "Falta la autorización explícita: export ALLOW_PRODUCTION_MIGRATIONS=1."
            )

        if confirm_db != database_name:
            raise MigrationTargetError(
                f"🛑 OPERACIÓN BLOQUEADA: Confirmación de base de producción incorrecta o ausente.\n"
                f"Se requiere CONFIRM_PRODUCTION_DATABASE='{database_name}' (detectado: '{confirm_db}').\n"
                "Esto previene que una variable genérica autorice migraciones accidentales sobre una base equivocada."
            )

    return database_name
