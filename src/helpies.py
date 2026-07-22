# ------------------------------------------------------------------------------
#  HILFSFUNKTIONEN
# ------------------------------------------------------------------------------

from functools import wraps
from io import BytesIO
import logging
import os
from pathlib import Path
from re import match as re_match
from smtplib import SMTPAuthenticationError, SMTPException
from time import sleep

from cryptography.fernet import Fernet
from flask import Response, flash, render_template, request
from flask_mail import Message
from markupsafe import Markup
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.inspection import inspect
from werkzeug.security import check_password_hash

from src.extensions import AppState
from src.models import ConfigSetting, _get_ausbilder_by_token


logger = logging.getLogger(__name__)

STATE: AppState | None = None


# ------------------------------------------------------------------------------
# Konstanten
# ------------------------------------------------------------------------------

_EMAIL_REGEX = r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*$"
_TOKEN_REGEX = r"^[A-Za-z0-9_-]{16}$"
_MAIL_LIMIT = 30  # Maximale Anzahl Mails pro Versandaufruf
_MAIL_DELAY = 1  # Sekunden Pause zwischen Mails

_SUBJECT_UNTIS = "Ihr WebUntis-Zugang – Zugriff auf Fehlzeiten Ihrer Auszubildenden"
_SUBJECT_CONFIRM = "Bestätigung der Azubianmeldung für WebUntis an der TSS Bitburg"

_AUSBILDER_USER = "tssbit"


# ------------------------------------------------------------------------------
# Datenbank – Initialisierung
# ------------------------------------------------------------------------------


def _init_db(state: AppState) -> None:
    """Initialisiert die SQLite-Datenbank beim App-Start.

    Erstellt alle Tabellen, falls nicht vorhanden, und legt einen
    Standard-ConfigSetting-Eintrag an. Speichert `state` in der
    globalen Variable STATE, um zirkuläre Imports zu vermeiden.

    Args:
        state: Beinhaltet alle notwendigen Variablen der Applikation.
    """
    global STATE
    STATE = state

    try:
        Path(STATE.app.instance_path).mkdir(parents=True, exist_ok=True)

        # Import hier, damit Modelle registriert sind, bevor create_all() aufgerufen wird
        import src.models  # noqa: F401

        STATE.db.create_all()
        # update_db()

        config = STATE.db.session.query(src.models.ConfigSetting).first()
        if config is None:
            STATE.db.session.add(src.models.ConfigSetting())
            STATE.db.session.commit()

        logger.info("Datenbanktabellen erstellt/überprüft.")

    except SQLAlchemyError as e:
        logger.exception("Fehler beim Erstellen der Datenbanktabellen: %s", e)
        raise
    except Exception as e:
        logger.exception("_init_db -> Fehler bei der Datenbankinitialisierung: %s", e)
        raise


def _update_app() -> None:
    """Lädt dynamische Konfigurationswerte aus der DB in die Flask-App-Konfiguration.

    Attributnamen des Modells werden in Großbuchstaben umgewandelt:
    ``admin_login`` → ``app.config["ADMIN_LOGIN"]``

    Passwort-Felder (admin_login, admin_password) werden übersprungen.
    Das Mail-Passwort wird entschlüsselt vor dem Schreiben in app.config.
    """
    _IGNORE_KEYS = {"admin_login", "admin_password"}

    def _to_dict(obj) -> dict:
        mapper = inspect(obj).mapper
        return {c.key: getattr(obj, c.key) for c in mapper.columns}

    print(1)
    try:
        cfg = None
        for cfg in STATE.db.session.query(ConfigSetting):
            data = _to_dict(cfg)
            data.pop("id", None)
            for key, value in data.items():
                if key not in _IGNORE_KEYS:
                    STATE.app.config[key.upper()] = value

        STATE.app.config["MAIL_PASSWORD"] = _get_decrypted_mail_password(STATE.app.config["MAIL_PASSWORD"])

        if cfg is not None:
            STATE.set_kontaktperson(
                cfg.kontaktperson_vorname,
                cfg.kontaktperson_nachname,
                cfg.kontaktperson_mail,
            )

    except Exception as e:
        logger.exception("Konnte App-Konfiguration nicht aus DB laden: %s", e)


# ------------------------------------------------------------------------------
# Mail – intern
# ------------------------------------------------------------------------------


def __send_mail(msg: Message) -> bool:
    """Sendet eine Flask-Mail-Message.

    Returns:
        True bei erfolgreichem Versand, sonst False.
    """
    try:
        print(STATE.app.config)
        print(msg.recipients)
        # STATE.mail.send(msg)
        logger.debug("Mail gesendet an: %s", msg.recipients)
        return True

    except SMTPAuthenticationError:
        logger.error("Mail-Fehler: Authentifizierung am SMTP-Server fehlgeschlagen.")
    except SMTPException as e:
        logger.error("Allgemeiner SMTP-Fehler beim Mailversand: %s", e)
    except Exception as e:
        logger.exception("Unerwarteter Fehler beim E-Mail-Versand: %s", e)

    return False


def __build_flash_result(success: bool, ok_msg: str, err_msg: str) -> tuple[str, str]:
    """Gibt ein (Nachricht, Kategorie)-Tuple zurück.

    Verwendet von: _send_untisinfo_to_ausbilder, _send_mail_to_ausbilder
    """
    return (ok_msg, "success") if success else (err_msg, "error")


# ------------------------------------------------------------------------------
# Mail – öffentlich
# ------------------------------------------------------------------------------


def _send_untisinfo_to_ausbilder(ausbilder_liste: list) -> None:
    """Sendet WebUntis-Zugangsinformationen an bis zu `_MAIL_LIMIT` Ausbilder.

    Args:
        ausbilder_liste: Liste von Ausbilder-Objekten.
    """
    for ausbilder in ausbilder_liste[:_MAIL_LIMIT]:
        html = render_template(
            "mail/mail_untis_ausbilder.html",
            server_url=f"https://{request.host}/",
            ausbilder=ausbilder,
        )
        msg = Message(subject=_SUBJECT_UNTIS, recipients=[ausbilder.ausbilder_email], html=html)
        sent = __send_mail(msg)

        recipient = f"{ausbilder.ausbilder_betrieb} ({ausbilder.ausbilder_email})"
        info, result = __build_flash_result(
            sent,
            ok_msg=f"OK: An {recipient} gesendet.<br>",
            err_msg=f"FEHLER: An {recipient} konnte nicht versandt werden.",
        )

        logger.info(info)
        flash(Markup(info), result)
        sleep(_MAIL_DELAY)


def _send_mail_to_ausbilder(ausbilder) -> tuple[Markup, str]:
    """Sendet eine Bestätigungsmail an einen Ausbilder nach der Anmeldung.

    Args:
        ausbilder: Ausbilder-Objekt mit E-Mail und Betriebsdaten.

    Returns:
        Tuple (Markup-Nachricht, Kategorie).
    """
    html = render_template(
        "mail/mail_confirm_ausbilder.html",
        ausbilder=ausbilder,
        server_url=f"https://{request.host}/",
        kontaktperson=STATE.kontaktperson,
    )
    msg = Message(subject=_SUBJECT_CONFIRM, recipients=[ausbilder.ausbilder_email], html=html)
    sent = __send_mail(msg)

    if sent:
        logger.info(
            "Mail verschickt an: %s, %s (%s)",
            ausbilder.ausbilder_name,
            ausbilder.ausbilder_vorname,
            ausbilder.ausbilder_email,
        )

    return __build_flash_result(
        sent,
        ok_msg=(
            f"Die Mail wurde an {ausbilder.ausbilder_email} gesendet<br>"
            "Bitte bestätigen Sie Ihre Daten innerhalb von 2 Stunden"
        ),
        err_msg=f"Die Mail an {ausbilder.ausbilder_email} konnte nicht versandt werden.",
    )


# ------------------------------------------------------------------------------
# Verschlüsselung
# ------------------------------------------------------------------------------


def _get_decrypted_mail_password(mail_password: str) -> str:
    """Entschlüsselt das Mail-Passwort für den SMTP-Versand.

    Args:
        mail_password: Verschlüsseltes Passwort aus der Datenbank.

    Returns:
        Entschlüsseltes Passwort als String, oder "" bei fehlendem Key/Passwort.
    """
    secret_key = STATE.app.config.get("ENCRYPTION_KEY")
    if not secret_key or not mail_password:
        return ""
    decrypted = Fernet(secret_key.encode()).decrypt(mail_password.encode())
    return decrypted.decode()


# ------------------------------------------------------------------------------
# Validierung
# ------------------------------------------------------------------------------


def _is_not_valid_mail(email: str) -> bool:
    """Gibt True zurück, wenn die E-Mail-Adresse NICHT valide ist."""
    return re_match(_EMAIL_REGEX, email) is None


def _token_is_valid(token: str) -> bool:
    """Gibt True zurück, wenn das Token dem erwarteten Muster entspricht."""
    return bool(token and re_match(_TOKEN_REGEX, token))


def _is_allowed_file(filename: str) -> bool:
    """Gibt True zurück, wenn die Dateiendung in der Erlaubt-Liste steht."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in STATE.allowed_extensions


# ------------------------------------------------------------------------------
# Dateiverwaltung
# ------------------------------------------------------------------------------


def _get_error_page() -> tuple[str, int]:
    """Gibt eine rudimentäre 400-Fehlerseite zurück."""
    return ("bad request!", 400)


def _uploaded_file_to_bytesio(file) -> BytesIO:
    """Liest eine hochgeladene Datei in ein BytesIO-Objekt ein.

    Args:
        file: Datei-Storage-Objekt (z. B. aus request.files).

    Returns:
        BytesIO mit dem Dateiinhalt, Zeiger am Anfang.
    """
    buf = BytesIO(file.read())
    buf.seek(0)
    return buf


def _save_file(file, file_path: str) -> tuple[str, str]:
    """Speichert ein hochgeladenes Dateiobjekt auf dem Dateisystem.

    Args:
        file:      Dateiupload-Objekt (z. B. request.files["file"]).
        file_path: Vollständiger Zielpfad inklusive Dateiname.

    Returns:
        Tuple (Nachricht, Kategorie) mit Kategorie in {"success", "error"}.
    """
    target = Path(file_path).resolve()

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error("Fehler beim Erstellen des Zielordners: %s", e)
        return ("Zielordner kann nicht erstellt werden.", "error")

    try:
        file.seek(0)
        file.save(target)
        return (f'Datei "{file.filename}" erfolgreich hochgeladen.', "success")
    except Exception as e:
        logger.error("_save_file -> Fehler beim Speichern der Datei: %s", e)
        return ("Die Datei konnte aufgrund eines Serverfehlers nicht gespeichert werden.", "error")


def _get_files_from_upload(upload_folder: str) -> list[str]:
    """Gibt eine sortierte Liste aller Dateinamen im Upload-Ordner zurück.

    Args:
        upload_folder: Pfad zum Upload-Verzeichnis.

    Returns:
        Sortierte Liste von Dateinamen (ohne Unterordner).
    """
    if not os.path.exists(upload_folder):
        return []
    files = [f for f in os.listdir(upload_folder) if os.path.isfile(os.path.join(upload_folder, f))]
    return sorted(files)


def __load_config() -> ConfigSetting | None:
    """Lädt den ersten ConfigSetting-Eintrag aus der Datenbank."""
    return STATE.db.session.execute(STATE.db.select(ConfigSetting)).scalars().first()


# ------------------------------------------------------------------------------
# Authentifizierung – intern
# ------------------------------------------------------------------------------


def __check_auth_and_get_type(username: str, password: str) -> str | None:
    """Prüft Zugangsdaten gegen die Datenbank und gibt den Login-Typ zurück.

    Args:
        username: Benutzername aus der HTTP-Basic-Auth-Anfrage.
        password: Klartext-Passwort aus der HTTP-Basic-Auth-Anfrage.

    Returns:
        "admin" | "tss" bei Erfolg, None bei ungültigen Daten.
    """
    config = STATE.db.session.execute(STATE.db.select(ConfigSetting)).scalars().first()

    if not config:
        return None

    if username == config.admin_login and check_password_hash(config.admin_password, password):
        return "admin"

    if username == _AUSBILDER_USER and check_password_hash(config.tss_password, password):
        return "tss"

    return None


def __authenticate() -> Response:
    """Gibt eine 401-Response zurück, die den Browser zur Eingabe von Zugangsdaten auffordert."""
    return Response(
        "Login erforderlich",
        401,
        {"WWW-Authenticate": 'Basic realm="Login erforderlich"'},
    )


# ------------------------------------------------------------------------------
# Authentifizierung – Dekorator
# ------------------------------------------------------------------------------


def _requires_auth(allowed_login_types: str | list | tuple, allow_token_bypass: bool = False):
    """Dekorator-Fabrik: Schützt eine Route auf bestimmte Login-Typen.

    Args:
        allowed_login_types: Erlaubter Typ oder Liste von Typen ("admin", "tss").
        allow_token_bypass:  Wenn True, wird ein gültiges URL-Token als
                             Authentifizierung akzeptiert (kein Passwort nötig).
    """
    if not isinstance(allowed_login_types, (list, tuple)):
        allowed_login_types = [allowed_login_types]

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):

            # Token-Bypass: nur wenn explizit erlaubt und Token gültig
            if allow_token_bypass:
                token = request.args.get("token")
                if token and _get_ausbilder_by_token(token) is not None:
                    return f(*args, **kwargs)

            # Normaler Basic-Auth-Flow
            auth = request.authorization
            if not auth:
                return __authenticate()

            login_type = __check_auth_and_get_type(auth.username, auth.password)
            if login_type in allowed_login_types:
                return f(*args, **kwargs)

            return __authenticate()

        return decorated

    return decorator


# ------------------------------------------------------------------------------
# DB-Migration (manuell aktivieren)
# ------------------------------------------------------------------------------


def update_db() -> None:
    """Führt manuelle Datenbankmigrationen aus.

    Muss in _init_db() nach STATE.db.create_all() einkommentiert werden.
    Nach erfolgreicher Migration wieder auskommentieren.
    """
    new_att = "tss_password"

    for cls in ["ConfigSetting"]:
        try:
            STATE.db.session.execute(text(f"ALTER TABLE {cls} ADD COLUMN {new_att} String"))
            STATE.db.session.commit()
        except Exception as e:
            logger.warning("update_db: Fehler bei '%s': %s", cls, e)
