from datetime import datetime, timedelta
from secrets import token_urlsafe

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import delete, false
from sqlalchemy.exc import SQLAlchemyError

from src.helpies import _log_message

# Hauptapplikation erstellen und Kongiguration festlegen
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///webuntis.sqlite"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "VuowbBtCQS8pTLd9NzrUGw"  # secrets.token_urlsafe(16)

# Datebank erstellen
db = SQLAlchemy(app)


# ------------------------------------------------------------------------------
# + DATENBANK-MODELLE und -ABFRAGEN
# ------------------------------------------------------------------------------
class Ausbilder(db.Model):
    """Repräsentiert die Ausbilder

    Args:
        db (_type_): _description_

    Returns:
        _type_: _description_
    """

    __tablename__ = "Ausbilder"

    ausbilder_email = db.Column(db.String(100), primary_key=True)
    ausbilder_name = db.Column(db.String(50), nullable=False, index=True)
    ausbilder_vorname = db.Column(db.String(50), nullable=False)
    ausbilder_betrieb = db.Column(db.String(100), nullable=False)
    bestaetigt = db.Column(db.Boolean, nullable=False, default=False)
    token = db.Column(db.String(32), default=lambda: token_urlsafe(12))
    # WICHTIG: Callable (ohne Klammern) übergeben, damit es bei jedem Insert neu berechnet wird
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Beziehung zu den Accounts (Backref erlaubt Zugriff von Account auf Ausbilder)
    accounts = db.relationship("Azubis", backref="Ausbilder", lazy=True)

    def __repr__(self):
        return f"<Ausbilder: {self.ausbilder_email}: {self.ausbilder_name}>"


class Azubis(db.Model):
    """Repräsentiert die Azubis"""

    __tablename__ = "Azubis"

    schueler_stamm_id = db.Column(db.String(50), primary_key=True)
    schueler_untis_id = db.Column(db.String(50), nullable=False, unique=True)
    schueler_familienname = db.Column(db.String(50), nullable=False, index=True)
    schueler_rufname = db.Column(db.String(50), nullable=False)
    schueler_geburtsdatum = db.Column(db.String(50), nullable=False)
    klasse = db.Column(db.String(20), nullable=False, index=True)
    # Foreign Key Verknüpfung
    ausbilder_email = db.Column(
        db.String(100), db.ForeignKey("Ausbilder.ausbilder_email", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self):
        return f"<Azubi: {self.schueler_untis_id}: {self.schueler_familienname}>"


class ConfigSetting(db.Model):
    __tablename__ = "ConfigSetting"

    id = db.Column(db.Integer, primary_key=True)

    # Admin Credentials
    admin_login = db.Column(db.String(100), nullable=False, default="admin")
    admin_password = db.Column(db.String(255), nullable=False, default="admin")

    # Kontakt
    kontakt_person_name = db.Column(db.String(255), default="John Lennon")
    kontakt_person_mail = db.Column(db.String(255), default="john@beatles.com")

    # Mail Server Einstellungen
    mail_server = db.Column(db.String(255), default="imap.beatles.com")
    mail_port = db.Column(db.Integer, default=587)
    mail_use_ssl = db.Column(db.Boolean, default=False)
    mail_use_tls = db.Column(db.Boolean, default=True)
    mail_username = db.Column(db.String(255), default="john@beatles.com")
    mail_password = db.Column(db.String(255), default="yellosubmarine")
    mail_default_sender = db.Column(db.String(255), default="paul@beatles.com")

    # Sonstiges
    timetowait = db.Column(db.Integer, default=120)


def _delete_unconfirmed_ausbilder(timetowait: int = 120):
    """Löscht alle Ausbilder die seit zwei Stunden in der DB sind und nicht bestätigt wurden"""

    zeitlimit = datetime.now() - timedelta(minutes=timetowait)
    stmt = delete(Ausbilder).where(Ausbilder.created_at < zeitlimit, Ausbilder.bestaetigt == false())
    db.session.execute(stmt)
    db.session.commit()


def _get_ausbilder_list() -> list:
    """erstellt eine Liste mit Dictionaries der Ausbildern

    Returns:
        list: Liste mit Dictionaries
    """
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

        result = db.session.execute(stmt)
        # Row -> dict via offiziellem Mapping
        return [dict(row._mapping) for row in result]

    except SQLAlchemyError as e:
        _log_message(f"DB-Fehler in _get_ausbilder_list: {e}", "error")
        return []
    except Exception as e:
        _log_message(f"Fehler in _get_ausbilder_list: {e}", "error")
        return []


def _get_azubi_list(klasse_name: str) -> list:
    """Erstellt eine Liste von Dictionaries zu Azubis inkl. optionaler Ausbilderdaten.

    Args:
        klasse_name: Klassenbezeichnung. Bei "all" werden alle Azubis geliefert.

    Returns:
        Liste von Dictionaries (Schüler- und Ausbilderfelder).
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
        # Eine Klasse wurde ausgewählt
        stmt = stmt.order_by(Azubis.klasse.asc(), Azubis.schueler_familienname.asc())

        result = db.session.execute(stmt).all()

        # rows sind Sequenzen/Row-Objekte; _mapping ist stabiler als _asdict()
        return [dict(row._mapping) for row in result]

    except SQLAlchemyError as e:
        _log_message(f"DB-Fehler in _get_azubi_list: {e}", "error")
        return []
    except Exception as e:
        _log_message(f"Fehler in _get_azubi_list: {e}", "error")
        return []


def _update_ausbilder_safe(liste: list, delete_existing: bool = False) -> tuple:
    """fügt eine Liste von Ausbildern in die datenbank ein
        - Es werden nur Ausbilder hinzugefügt, die noch nicht in der DB existieren (basierend auf der E-Mail)
        - Es wird keine Löschung durchgeführt, damit bestehende Accounts und Verknüpfungen erhalten bleiben

    Args:
        liste (list): Liste mit Objektender Klasse Ausbilder die in die Datenbank eingefügt werden sollen
        delete_existing (bool, optional): Ob bestehende Ausbilder gelöscht werden sollen. Defaults to False.

    Returns:
        tupel: Tupel mit zwei Elementen: (Nachricht, Kategorie), wobei Kategorie entweder "success" oder "error" ist
    """
    try:
        if delete_existing:
            db.session.query(Ausbilder).delete()
            db.session.commit()

        # 1. Eingabeliste deduplizieren (falls das Objekt eine E-Mail-Eigenschaft hat)
        # Wir erstellen ein Dictionary mit der E-Mail als Key.
        # Falls eine Mail doppelt vorkommt, überschreibt sie sich hier selbst.
        unique_input = {item.ausbilder_email: item for item in liste}

        # 2. Bestehende E-Mails aus der Datenbank abrufen
        # Wir holen uns nur die E-Mails, das ist performant.
        existing_emails = {r[0] for r in db.session.query(Ausbilder.ausbilder_email).all()}

        # 3. Filtern: Nur Elemente hinzufügen, die NICHT in der DB existieren
        to_add = [item for email, item in unique_input.items() if email not in existing_emails]
        # 4. Einfügen
        if to_add:
            db.session.add_all(to_add)
            db.session.commit()
            return (f"{len(to_add)} neue Azubis hinzugefügt.", "success")
        else:
            return ("Keine neuen Azubis gefunden (alle existieren bereits)", "success")

    except Exception as e:
        db.session.rollback()
        _log_message(f"Fehler im Modul _update_ausbilder_safe: {e}", "error")
        return ("Fehler beim Einfügen:", "error")


def _update_azubis_safe(liste: list, delete_existing: bool = False) -> tuple:
    """fügt eine Liste von Azubis in die datenbank ein
        - Es werden nur Azubis hinzugefügt, die noch nicht in der DB existieren (basierend auf der schueler_stamm_id)
        - Es wird keine Löschung durchgeführt, damit bestehende Accounts und Verknüpfungen erhalten bleiben

    Args:
        liste (list): Liste mit Objektender Klasse Azubis die in die Datenbank eingefügt werden sollen
        delete_existing (bool, optional): Ob bestehende Azubis gelöscht werden sollen. Defaults to False.

    Returns:
        tupel: Tupel mit zwei Elementen: (Nachricht, Kategorie), wobei Kategorie entweder "success" oder "error" ist
    """
    try:
        if delete_existing:
            db.session.query(Azubis).delete()
            db.session.commit()

        # 1. Eingabeliste deduplizieren (falls das Objekt eine schueler_stamm_id-Eigenschaft hat)
        # Wir erstellen ein Dictionary mit der schueler_stamm_id als Key.
        # Falls eine Mail doppelt vorkommt, überschreibt sie sich hier selbst.
        unique_input = {item.schueler_stamm_id: item for item in liste}

        # 2. Bestehende schueler_stamm_id aus der Datenbank abrufen
        # Wir holen uns nur die schueler_stamm_ids, das ist performant.
        existing_ids = {r[0] for r in db.session.query(Azubis.schueler_stamm_id).all()}

        # 3. Filtern: Nur Elemente hinzufügen, die NICHT in der DB existieren
        to_add = [item for schueler_stamm_id, item in unique_input.items() if schueler_stamm_id not in existing_ids]

        # 4. Einfügen
        if to_add:
            db.session.add_all(to_add)
            db.session.commit()
            return (f"{len(to_add)} neue Azubis hinzugefügt.", "success")
        else:
            return ("Keine neuen Azubis gefunden (alle existieren bereits)", "success")

    except Exception as e:
        db.session.rollback()
        _log_message(f"Fehler im Modul _update_azubis_safe: {e}", "error")
        return ("Fehler beim Einfügen:", "error")
