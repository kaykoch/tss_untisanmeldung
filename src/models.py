# ------------------------------------------------------------------------------
#  DATENBANK-MODELLE UND -ABFRAGEN
# ------------------------------------------------------------------------------

from datetime import datetime, timedelta
import logging
from secrets import token_urlsafe
from typing import Any

from sqlalchemy import delete, false
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from src.extensions import db


logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Konstanten
# ------------------------------------------------------------------------------

# Admin Zugang
DEFAULT_ADMINLOGIN = "admin"
DEFAULT_ADMINPASSWORD = "admin"

# Ausbilder Zugang
DEFAULT_TSSPASSWORD = "tssbit"

# Kontaktperson
DEFAULT_VORNAME = "John"
DEFAULT_NACHNAME = "Lennon"
DEFAULT_MAIL = "john@beatles.com"

# Mail Zugang
DEFAULT_MAIL_SERVER = "smtp.office365.com"
DEFAULT_MAIL_PORT = 587
DEFAULT_MAIL_SENDER = "paul@beatles.com"
DEFAULT_MAIL_USER = "john@beatles.com"
DEFAULT_MAIL_PASS = "yellosubmarine"

# Weitere
TOKEN_LENGTH = 12
DEFAULT_TIMETOWAIT = 120


# ------------------------------------------------------------------------------
# Modelle
# ------------------------------------------------------------------------------


class Ausbilder(db.Model):
    """Repräsentiert einen Ausbildungsbetrieb mit Kontaktperson."""

    __tablename__ = "Ausbilder"

    ausbilder_email = db.Column(db.String(100), primary_key=True)
    ausbilder_name = db.Column(db.String(50), nullable=False, index=True)
    ausbilder_vorname = db.Column(db.String(50), nullable=False)
    ausbilder_betrieb = db.Column(db.String(100), nullable=False)
    bestaetigt = db.Column(db.Boolean, nullable=False, default=False)
    # WICHTIG: Callable (ohne Klammern) übergeben, damit es bei jedem Insert neu berechnet wird
    token = db.Column(db.String(32), default=lambda: token_urlsafe(TOKEN_LENGTH))
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Beziehung zu Azubis (Backref erlaubt Zugriff von Azubi auf Ausbilder)
    accounts = db.relationship("Azubis", backref="Ausbilder", lazy=True)

    def __repr__(self) -> str:
        return f"<Ausbilder: {self.ausbilder_email}: {self.ausbilder_name}>"


class Azubis(db.Model):
    """Repräsentiert einen Auszubildenden mit optionaler Ausbilder-Verknüpfung."""

    __tablename__ = "Azubis"

    schueler_stamm_id = db.Column(db.String(50), primary_key=True)
    schueler_untis_id = db.Column(db.String(50), nullable=False, unique=True)
    schueler_familienname = db.Column(db.String(50), nullable=False, index=True)
    schueler_rufname = db.Column(db.String(50), nullable=False)
    schueler_geburtsdatum = db.Column(db.String(50), nullable=False)
    klasse = db.Column(db.String(20), nullable=False, index=True)

    # Foreign Key – SET NULL bei Löschung des Ausbilders, damit Azubi erhalten bleibt
    ausbilder_email = db.Column(
        db.String(100),
        db.ForeignKey("Ausbilder.ausbilder_email", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<Azubi: {self.schueler_untis_id}: {self.schueler_familienname}>"


class ConfigSetting(db.Model):
    """Speichert alle zur Laufzeit änderbaren Anwendungseinstellungen."""

    __tablename__ = "ConfigSetting"

    id = db.Column(db.Integer, primary_key=True)

    # Admin-Zugangsdaten
    admin_login = db.Column(db.String(100), nullable=False, default=DEFAULT_ADMINLOGIN)
    # WICHTIG: Callable (ohne Klammern) übergeben, damit es bei jedem Insert neu berechnet wird
    admin_password = db.Column(
        db.String(255), nullable=False, default=lambda: generate_password_hash(DEFAULT_ADMINPASSWORD)
    )
    tss_password = db.Column(
        db.String(255), nullable=False, default=lambda: generate_password_hash(DEFAULT_TSSPASSWORD)
    )

    # Kontaktperson
    kontaktperson_vorname = db.Column(db.String(255), default=DEFAULT_VORNAME)
    kontaktperson_nachname = db.Column(db.String(255), default=DEFAULT_NACHNAME)
    kontaktperson_mail = db.Column(db.String(255), default=DEFAULT_MAIL)

    # Mail-Server-Einstellungen
    mail_server = db.Column(db.String(255), default=DEFAULT_MAIL_SERVER)
    mail_port = db.Column(db.Integer, default=DEFAULT_MAIL_PORT)
    mail_use_tls = db.Column(db.Boolean, default=True)
    mail_use_ssl = db.Column(db.Boolean, default=False)
    mail_username = db.Column(db.String(255), default=DEFAULT_MAIL_USER)
    mail_password = db.Column(db.String(255), default=DEFAULT_MAIL_PASS)
    mail_default_sender = db.Column(db.String(255), default=DEFAULT_MAIL_SENDER)

    # Sonstiges
    timetowait = db.Column(db.Integer, default=DEFAULT_TIMETOWAIT)


# ------------------------------------------------------------------------------
# Hilfsfunktionen – intern
# ------------------------------------------------------------------------------


def __delete_all(model) -> None:
    """Löscht alle Einträge eines Modells und committed sofort.

    Verwendet von: _update_ausbilder_safe, _update_azubis_safe
    """
    db.session.query(model).delete()
    db.session.commit()


def __get_existing_keys(model, column) -> set:
    """Gibt alle vorhandenen Werte einer Spalte als Set zurück.

    Verwendet von: _update_ausbilder_safe, _update_azubis_safe
    """
    return {r[0] for r in db.session.query(column).all()}


def __add_new_entries(
    liste: list,
    key_attr: str,
    existing_keys: set,
    label: str,
) -> tuple[str, str]:
    """Dedupliziert eine Liste, filtert bereits vorhandene Einträge und fügt neue ein.

    Args:
        liste:         Liste von ORM-Objekten.
        key_attr:      Name des eindeutigen Schlüsselattributs (z. B. "ausbilder_email").
        existing_keys: Set der bereits in der DB vorhandenen Schlüssel.
        label:         Bezeichnung für die Flash-Meldung (z. B. "Ausbilder").

    Returns:
        Tuple (Meldung, Kategorie).

    Verwendet von: _update_ausbilder_safe, _update_azubis_safe
    """
    unique_input = {getattr(item, key_attr): item for item in liste}
    to_add = [item for key, item in unique_input.items() if key not in existing_keys]

    if to_add:
        db.session.add_all(to_add)
        db.session.commit()
        return (f"{len(to_add)} neue {label} hinzugefügt.", "success")

    return (f"Keine neuen {label} gefunden (alle existieren bereits).", "success")


# ------------------------------------------------------------------------------
# Öffentliche DB-Funktionen
# ------------------------------------------------------------------------------


def _delete_unconfirmed_ausbilder(timetowait: int = DEFAULT_TIMETOWAIT) -> None:
    """Löscht alle Ausbilder, die seit `timetowait` Minuten unbestätigt in der DB sind."""
    zeitlimit = datetime.now() - timedelta(minutes=timetowait)
    stmt = delete(Ausbilder).where(
        Ausbilder.created_at < zeitlimit,
        Ausbilder.bestaetigt == false(),
    )
    db.session.execute(stmt)
    db.session.commit()


def _get_ausbilder_list() -> list[dict[str, Any]]:
    """Gibt alle Ausbilder als Liste von Dictionaries zurück."""
    try:
        stmt = db.select(
            Ausbilder.ausbilder_email,
            Ausbilder.ausbilder_name,
            Ausbilder.ausbilder_vorname,
            Ausbilder.ausbilder_betrieb,
            Ausbilder.bestaetigt,
            Ausbilder.token,
            Ausbilder.created_at,
        )
        return [dict(row._mapping) for row in db.session.execute(stmt)]

    except SQLAlchemyError as e:
        logger.error("DB-Fehler in _get_ausbilder_list: %s", e)
        return []
    except Exception as e:
        logger.error("Fehler in _get_ausbilder_list: %s", e)
        return []


def _get_azubi_list(klasse_name: str) -> list[dict[str, Any]]:
    """Gibt Azubis einer Klasse (oder alle) als Liste von Dictionaries zurück.

    Args:
        klasse_name: Klassenbezeichnung oder "all" für alle Klassen.

    Returns:
        Liste von Dictionaries mit Schüler- und Ausbilderfeldern.
    """
    try:
        stmt = (
            db.select(
                Azubis.schueler_stamm_id,
                Azubis.schueler_untis_id,
                Azubis.schueler_familienname,
                Azubis.schueler_rufname,
                Azubis.schueler_geburtsdatum,
                Azubis.klasse,
                Ausbilder.ausbilder_email,
                Ausbilder.ausbilder_name,
                Ausbilder.ausbilder_vorname,
            )
            .select_from(Azubis)
            .outerjoin(Ausbilder, Azubis.ausbilder_email == Ausbilder.ausbilder_email)
        )

        if klasse_name != "all":
            stmt = stmt.where(Azubis.klasse == klasse_name)

        stmt = stmt.order_by(Azubis.klasse.asc(), Azubis.schueler_familienname.asc())

        return [dict(row._mapping) for row in db.session.execute(stmt).all()]

    except SQLAlchemyError as e:
        logger.error("DB-Fehler in _get_azubi_list: %s", e)
        return []
    except Exception as e:
        logger.error("Fehler in _get_azubi_list: %s", e)
        return []


def _update_ausbilder_safe(liste: list, delete_existing: bool = False) -> tuple[str, str]:
    """Fügt neue Ausbilder in die DB ein, ohne bestehende Einträge zu überschreiben.

    Args:
        liste:           Liste von Ausbilder-Objekten.
        delete_existing: Bei True werden alle bestehenden Ausbilder vorher gelöscht.

    Returns:
        Tuple (Meldung, Kategorie) – Kategorie ist "success" oder "error".
    """
    try:
        if delete_existing:
            __delete_all(Ausbilder)

        existing = __get_existing_keys(Ausbilder, Ausbilder.ausbilder_email)
        return __add_new_entries(liste, "ausbilder_email", existing, "Ausbilder")

    except Exception as e:
        db.session.rollback()
        logger.error("Fehler in _update_ausbilder_safe: %s", e)
        return ("Fehler beim Einfügen der Ausbilder.", "error")


def _update_azubis_safe(liste: list, delete_existing: bool = False) -> tuple[str, str]:
    """Fügt neue Azubis in die DB ein, ohne bestehende Einträge zu überschreiben.

    Args:
        liste:           Liste von Azubis-Objekten.
        delete_existing: Bei True werden alle bestehenden Azubis vorher gelöscht.

    Returns:
        Tuple (Meldung, Kategorie) – Kategorie ist "success" oder "error".
    """
    try:
        if delete_existing:
            __delete_all(Azubis)

        existing = __get_existing_keys(Azubis, Azubis.schueler_stamm_id)
        return __add_new_entries(liste, "schueler_stamm_id", existing, "Azubis")

    except Exception as e:
        db.session.rollback()
        logger.error("Fehler in _update_azubis_safe: %s", e)
        return ("Fehler beim Einfügen der Azubis.", "error")


def _get_ausbilder_by_token(token: str) -> Ausbilder | None:
    """Lädt einen Ausbilder anhand seines Tokens aus der DB."""
    stmt = db.select(Ausbilder).where(Ausbilder.token == token)
    return db.session.execute(stmt).scalar_one_or_none()
