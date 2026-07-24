import logging

from cryptography.fernet import Fernet
from flask import (
    flash,
)
from sqlalchemy.inspection import inspect
from werkzeug.security import generate_password_hash

from src.extensions import state
from src.forms import ConfigForm
from src.models import ConfigSetting
from src.services.crypto_service import get_decrypted_mail_password


logger = logging.getLogger(__name__)

_IGNORE_CONFIG_KEYS = {"admin_login", "admin_password"}
_HASH_PASSWORD_FIELDS: frozenset[str] = frozenset({"admin_password", "tss_password"})
_SYSTEM_FIELDS: frozenset[str] = frozenset({"csrf_token", "submit"})
_EXCLUDED_FIELDS: frozenset[str] = _HASH_PASSWORD_FIELDS | _SYSTEM_FIELDS


def _config_to_dict(cfg: ConfigSetting) -> dict:
    """Wandelt ein ConfigSetting-Objekt in ein Dictionary um (ohne 'id')."""
    mapper = inspect(cfg).mapper
    data = {c.key: getattr(cfg, c.key) for c in mapper.columns}
    data.pop("id", None)
    return data


def load_defaults() -> None:
    """Lädt dynamische Konfigurationswerte aus der DB in die Flask-App-Konfiguration.

    Attributnamen des Modells werden in Großbuchstaben umgewandelt:
    ``sprechtag_beginn`` → ``app.config["SPRECHTAG_BEGINN"]``

    Passwort-Felder (admin_*, tss_*) werden übersprungen.
    Das Mail-Passwort wird vor dem Schreiben entschlüsselt.
    """
    try:
        cfg = load_config()
        if cfg is None:
            logger.warning("_load_defaults: Keine Konfiguration in der Datenbank gefunden.")
            return

        data = _config_to_dict(cfg)
        state.app.config.update({key.upper(): value for key, value in data.items() if key not in _IGNORE_CONFIG_KEYS})

        state.app.config["MAIL_PASSWORD"] = get_decrypted_mail_password(state.app.config["MAIL_PASSWORD"])

        state.set_kontaktperson(
            cfg.kontaktperson_vorname,
            cfg.kontaktperson_nachname,
            cfg.kontaktperson_mail,
        )

    except Exception as e:
        logger.exception("Konnte App-Konfiguration nicht aus DB laden: %s", e)


def load_config() -> ConfigSetting | None:
    """Lädt den ersten Konfigurationsdatensatz aus der Datenbank."""
    stmt = state.db.select(ConfigSetting).limit(1)
    return state.db.session.execute(stmt).scalar_one_or_none()


def apply_config_form(form: ConfigForm, cfg: ConfigSetting) -> None:
    _apply_non_password_fields(form, cfg)
    _apply_password_fields(form, cfg)


def _apply_non_password_fields(form: ConfigForm, cfg: ConfigSetting) -> None:
    """Schreibt alle Nicht-Passwort- und Nicht-Systemfelder in das Config-Objekt."""
    for fieldname, value in form.data.items():
        if fieldname not in _EXCLUDED_FIELDS:
            setattr(cfg, fieldname, value)


def _apply_password_fields(form: ConfigForm, cfg: ConfigSetting) -> None:
    """Verarbeitet Passwörter: Admin/TSS werden gehasht, Mail wird verschlüsselt."""

    # 1. Admin & TSS Passwörter HASHTEN (One-Way)
    for field in _HASH_PASSWORD_FIELDS:
        if form[field].data:
            hashed_password = generate_password_hash(form[field].data)
            setattr(cfg, field, hashed_password)

    # 2. Mail-Passwort VERSCHLÜSSELN (Two-Way)
    if form.mail_password.data:
        # Hole den Master-Key aus den Umgebungsvariablen der app (config.py)
        secret_key = state.app.config["ENCRYPTION_KEY"]

        if secret_key:
            fernet = Fernet(secret_key.encode())
            # Passwort in Bytes umwandeln, verschlüsseln und als String in DB speichern
            encrypted_password = fernet.encrypt(form.mail_password.data.encode()).decode()
            cfg.mail_password = encrypted_password
        else:
            # Sicherheits-Fallback, falls du den Key vergessen hast einzurichten
            logger.error("E-Mail-Passwort konnte nicht verschlüsselt werden: ENCRYPTION_KEY fehlt!")
            flash("Fehler: Verschlüsselungs-Key nicht konfiguriert.", "error")
