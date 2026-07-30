# ------------------------------------------------------------------------------
# Überprüft durch Claude 4
# ------------------------------------------------------------------------------

import logging
from re import match as re_match

from flask import flash
from markupsafe import Markup

from src.models import Azubis


logger = logging.getLogger(__name__)

_TOKEN_REGEX = r"^[A-Za-z0-9_-]{16}$"


def _copy_model_attributes(obj) -> dict:
    """Kopiert alle instanzeigenen, nicht-privaten Attribute eines SQLAlchemy-Objekts.

    Args:
        obj: SQLAlchemy-Modell-Instanz.

    Returns:
        Dictionary mit den kopierten Attributen, oder {} wenn obj None ist.
    """
    if obj is None:
        return {}
    return {key: value for key, value in vars(obj).items() if not key.startswith("_")}


def flash_form_errors(context: str, form) -> None:
    """Loggt Formular-Fehler und gibt sie als Flash-Nachricht aus.

    Args:
        context: Name des aufrufenden Kontexts (z. B. Funktions- oder Routenname).
        form:    WTForms-Formular-Objekt mit einem errors-Dictionary.
    """
    logger.error("Formular-Fehler in %s: %s", context, form.errors)
    texts = [msg for messages in form.errors.values() for msg in messages]
    flash(Markup("<br>".join(texts)), "error")


def token_is_valid(token: str) -> bool:
    """Gibt True zurück, wenn das Token dem erwarteten Muster entspricht.

    Args:
        token (str): Zu prüfendes Token.

    Returns:
        bool: True, wenn das Token 16 Zeichen aus [A-Za-z0-9_-] enthält.
    """
    return bool(token and re_match(_TOKEN_REGEX, token))


def get_fehlende_ids(angefragt: list[str], gefunden: list[Azubis]) -> list[str]:
    """Gibt die IDs zurück, die angefragt, aber nicht in der DB gefunden wurden.

    Args:
        angefragt (list[str]): Liste der angefragten Schüler-IDs.
        gefunden  (list[Azubis]): Liste der gefundenen Azubi-Objekte aus der DB.

    Returns:
        list[str]: IDs, die in der DB nicht vorhanden sind.
    """
    gefundene_ids = {a.schueler_untis_id for a in gefunden}
    return [sid for sid in angefragt if sid not in gefundene_ids]


def flash_all(messages: list[tuple[str, str]]) -> None:
    """Flasht eine Liste von (Nachricht, Kategorie)-Tuples auf einmal.

    Jede Nachricht wird als Markup gerendert (HTML-Tags werden nicht escaped).

    Args:
        messages: Liste von (Nachricht, Kategorie)-Tuples,
                  z. B. [("Erfolg", "success"), ("Fehler", "error")].
    """
    for msg, category in messages:
        flash(Markup(msg), category)


def update_db() -> None:
    """Führt manuelle Datenbankmigrationen aus.

    Muss in _init_db() nach STATE.db.create_all() einkommentiert werden.
    Nach erfolgreicher Migration wieder auskommentieren.
    """
    from sqlalchemy import text

    from src.extensions import state

    new_att = "mail_encryption"
    print(new_att)

    for cls in ["ConfigSetting"]:
        try:
            state.db.session.execute(text(f"ALTER TABLE {cls} ADD COLUMN {new_att} String"))
            state.db.session.commit()
            logger.info("update_db: Spalte '%s' zu '%s' hinzugefügt.", new_att, cls)
        except Exception as e:
            logger.warning("update_db: Fehler bei '%s': %s", cls, e)
