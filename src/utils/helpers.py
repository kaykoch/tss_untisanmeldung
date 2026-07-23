import logging
from re import match as re_match

from flask import flash
from markupsafe import Markup

from src.models import Azubis


logger = logging.getLogger(__name__)

_TOKEN_REGEX = r"^[A-Za-z0-9_-]{16}$"


def _copy_model_attributes(obj) -> dict:
    """Kopiert alle öffentlichen, nicht-aufrufbaren Attribute eines SQLAlchemy-Objekts.

    Args:
        obj: SQLAlchemy-Modell-Instanz.

    Returns:
        Dictionary mit den kopierten Attributen, oder {} wenn obj None ist.
    """
    if obj is None:
        return {}
    return {key: getattr(obj, key) for key in dir(obj) if not key.startswith("_") and not callable(getattr(obj, key))}


def flash_form_errors(context: str, form) -> None:
    logger.error("Formular-Fehler in %s: %s", context, form.errors)
    texts = [msg for messages in form.errors.values() for msg in messages]
    flash(Markup("<br>".join(texts)), "error")


def token_is_valid(token: str) -> bool:
    """Gibt True zurück, wenn das Token dem erwarteten Muster entspricht."""
    return bool(token and re_match(_TOKEN_REGEX, token))


def get_fehlende_ids(angefragt: list[str], gefunden: list[Azubis]) -> list[str]:
    """Gibt die IDs zurück, die nicht in der DB gefunden wurden."""
    gefundene_ids = {a.schueler_untis_id for a in gefunden}
    return [sid for sid in angefragt if sid not in gefundene_ids]
