import logging

from sqlalchemy.inspection import inspect

from src.extensions import state
from src.models import ConfigSetting
from src.services.crypto_service import get_decrypted_mail_password


logger = logging.getLogger(__name__)

_IGNORE_CONFIG_KEYS = {"admin_login", "admin_password"}


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
