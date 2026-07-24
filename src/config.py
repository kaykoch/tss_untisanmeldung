# ------------------------------------------------------------------------------
# Überprüft durch Claude 4
# ------------------------------------------------------------------------------

import logging
import os
import secrets

from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger(__name__)


def _get_env(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name)
    if val is None or val == "":
        return default
    return val


def _get_env_int(name: str, default: int | None = None) -> int | None:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except ValueError as exc:
        raise RuntimeError(f"Umgebungsvariable {name} muss ein Integer sein, war: {v!r}") from exc


def _require_env(name: str) -> str:
    v = _get_env(name)
    if not v:
        raise RuntimeError(
            f"Erforderliche Umgebungsvariable {name} fehlt. Setze sie in der Umgebung oder in deiner .env-Datei."
        )
    return v


class BaseConfig:
    # Default DB (relativer Pfad). In Prod kannst du SQLALCHEMY_DATABASE_URI setzen.
    SQLALCHEMY_DATABASE_URI: str = _get_env("SQLALCHEMY_DATABASE_URI", "sqlite:///tss_untisanmeldung.sqlite")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Secret / Encryption: können in Basisklasse gesetzt oder überschrieben werden
    SECRET_KEY: str | None = _get_env("SECRET_KEY")
    ENCRYPTION_KEY: str | None = _get_env("ENCRYPTION_KEY")

    # Max upload size: Default 16 MiB
    MAX_CONTENT_LENGTH: int | None = _get_env_int("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)


class ProductionConfig(BaseConfig):
    """Produktions-Config: Abbruch (RuntimeError) wenn kritische ENV fehlen."""

    DEBUG = False

    # Diese Zeilen führen beim Import eine Prüfung durch und werfen Fehler, falls nicht gesetzt.
    SECRET_KEY: str = _require_env("SECRET_KEY")
    ENCRYPTION_KEY: str = _require_env("ENCRYPTION_KEY")

    # Optional: du kannst hier weitere zwingend erforderliche Variablen prüfen:
    # DATABASE_URL = _require_env("DATABASE_URL")


class DevConfig(BaseConfig):
    """Entwicklungs-Config: generiert Fallbacks und loggt Warnungen."""

    DEBUG = True

    if BaseConfig.SECRET_KEY:
        SECRET_KEY = BaseConfig.SECRET_KEY
    else:
        SECRET_KEY = secrets.token_urlsafe(32)
        logger.warning("DEV: SECRET_KEY nicht gesetzt — temporärer Schlüssel wird erzeugt (nicht für Produktion).")

    if BaseConfig.ENCRYPTION_KEY:
        ENCRYPTION_KEY = BaseConfig.ENCRYPTION_KEY
    else:
        ENCRYPTION_KEY = "dev-encryption-key"
        logger.warning("DEV: ENCRYPTION_KEY nicht gesetzt — Dev-Fallback wird verwendet (nicht für Produktion).")
