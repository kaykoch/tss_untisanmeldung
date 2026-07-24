# ------------------------------------------------------------------------------
#  DATENBANK-MODELLE UND -ABFRAGEN
# ------------------------------------------------------------------------------

from datetime import datetime
import logging
from secrets import token_urlsafe

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


def delete_all(model) -> None:
    """Löscht alle Einträge eines Modells und committed sofort.

    Verwendet von: update_ausbilder_safe, _update_azubis_safe
    """
    db.session.query(model).delete()
    db.session.commit()


def get_existing_keys(model, column) -> set:
    """Gibt alle vorhandenen Werte einer Spalte als Set zurück.

    Verwendet von: update_ausbilder_safe, _update_azubis_safe
    """
    return {r[0] for r in db.session.query(column).all()}


def add_new_entries(
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

    Verwendet von: update_ausbilder_safe, _update_azubis_safe
    """
    unique_input = {getattr(item, key_attr): item for item in liste}
    to_add = [item for key, item in unique_input.items() if key not in existing_keys]

    if to_add:
        db.session.add_all(to_add)
        db.session.commit()
        return (f"{len(to_add)} neue {label} hinzugefügt.", "success")

    return (f"Keine neuen {label} gefunden (alle existieren bereits).", "success")
