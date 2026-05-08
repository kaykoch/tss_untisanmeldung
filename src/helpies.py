import logging
import os
from functools import wraps
from re import match as re_match

from flask import Response, request
from werkzeug.utils import secure_filename

from src.config import ALLOWD_EXTENSIONS

logger = logging.getLogger(__name__)
logging.basicConfig(
    filename="./src/data/untis.log",
    format="%(asctime)s %(message)s",
    encoding="utf-8",
    level=logging.WARNING,
    datefmt="%Y-%m-%d %H:%M:%S",
)

# + ----------------------------------------------------------------------------
# + HELPIES
# + ----------------------------------------------------------------------------


def _set_config(app, config_data):
    """Setzt die Konfigurationen für die Datenbank und den Mailversand"""
    global APP
    APP = app

    # Mail-Konfiguration
    app.config["MAIL_SERVER"] = config_data.mail_server
    app.config["MAIL_PORT"] = config_data.mail_port
    app.config["MAIL_USE_TLS"] = config_data.mail_use_tls
    app.config["MAIL_USE_SSL"] = config_data.mail_use_ssl
    app.config["MAIL_USERNAME"] = config_data.mail_username
    app.config["MAIL_PASSWORD"] = config_data.mail_password
    app.config["MAIL_DEFAULT_SENDER"] = config_data.mail_default_sender

    # UNTIS-Konfiguration
    app.config["UNTIS_KONTAKTPERSON"] = (
        {
            "name": config_data.kontakt_person_name,
            "mail": config_data.kontakt_person_mail,
        },
    )
    app.config["UNTIS_USERNAME"] = config_data.admin_login
    app.config["UNTIS_PASSWORD"] = config_data.admin_password
    app.config["UNTIS_TIMETOWAIT"] = config_data.timetowait

    app.secret_key = "nfdinkmvssodlfbdölbfk"


def _initialize_app(app, db, ConfigSetting):
    """Prüft beim Start, ob die DB existiert und erstellt sie ggf."""
    _log_message("Untisanmeldung gestartet", "warning")
    db_path = os.path.join(app.instance_path, "webuntis.sqlite")
    if not os.path.exists(db_path):
        with app.app_context():
            print("Datenbank nicht gefunden. Erstelle Datenbank...")
            # Falls der Ordner 'instance' noch nicht existiert, erstellen wir ihn
            os.makedirs(app.instance_path, exist_ok=True)

            # Hier rufst du deine Funktion oder direkt db.create_all() auf
            db.create_all()
            # Falls du zusätzliche Initialdaten hast:
            config = ConfigSetting()
            db.session.add(config)
            db.session.commit()
            print("Datenbank erfolgreich initialisiert.")
            _log_message("Datenbank erfolgreich initialisiert", "warning")
    else:
        print("Datenbank existiert bereits.")


def _is_not_valid_mail(email: str) -> bool:
    """Überprüft, ob eine emaiadresse valide ist

    Args:
        email (str): Emailadresse, die überprüft werden soll

    Returns:
        bool: True, wenn sie NICHT valide ist
    """
    regex = r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*$"
    return re_match(regex, email) is None


def _token_is_valid(token: str) -> bool:
    """Überprüft, ob das token dem Muster entspricht

    Args:
        token (str): Token, das überprüft werden soll

    Returns:
        bool: True, wenn das token dem Muster entspricht
    """
    if not token:
        return False
    return bool(re_match(r"^[A-Za-z0-9_-]{16}$", token))


def _get_error_page():
    """liefert eine Fehlerseite zurück, die als Antwort auf fehlerahfte Webanfragen dient
    Die Fehlermeldung wird angezeigt

    Returns:
    tupel:  (rudimentäre Webseite, 400)
    """
    return ("bad request!", 400)


def _is_allowed_file(filename) -> bool:
    """Überprüft ob die Dateiendung erlaubt ist

    Args:
        filename (str): Dateipfad der überprüft werden soll

    Returns:
        bool: True, wenn die Dateiendung erlaubt ist
    """
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWD_EXTENSIONS


def _save_file(file, file_path: str, is_path=False) -> tuple:
    """Überprüft und speichert eine Datei, die hochgeladen wurde.
    Sie muss in 'request.files["file"]' zu finden sein.
    Abhängig vom Parameter 'is_path' wird an der Parameter 'file_path' der Dateiname angehängt
    oder es handelt sich um den kompletten Pfad mit vorgegeben Dateinamen

    Args:
        file: Datei, die gespeichert werden soll (z.B. request.files["file"])
        file_path (str): Entweder der Ordner in dem gespeichert werden soll,
                        oder der komplette Pfad inkl. Dateiname
        is_path (bool): True -> Pfad des Ordners ohne Dateiname
                        False -> Pfad der Datei unter deren Namen die Datei gespeichert werden soll
    Returns:
        (tuple): Kommentar , Kategory des Kommentars (success, warning, error)
    """
    max_content_length = 5 * 1024 * 1024  # 5 MB

    if not file or file.filename == "":
        return ("Keine Datei ausgewählt", "error")

    if not _is_allowed_file(file.filename):
        _, dateierweiterung = os.path.splitext(file.filename)
        return (f"Dateityp '{dateierweiterung}' ist nicht erlaubt", "error")

    # max Dateigröße überprüfen
    file.seek(0, os.SEEK_END)
    file_length = file.tell()
    file.seek(0)  # Zeiger wieder an den Anfang setzen für das spätere Speichern
    if file_length > max_content_length:
        return (f"Datei ist zu groß (Maximal {max_content_length // (1024 * 1024)} MB erlaubt)", "error")

    try:
        # secure_filename säubert den Dateinamen
        filename = secure_filename(file.filename)

        # Wenn nur der Pfad übergeben wurde, wird der Dateiname angehängt
        if is_path:
            file_path = os.path.join(file_path, filename)

        # Absoluten Pfad erzwingen, um Path-Traversal auszuschließen
        full_path = os.path.abspath(file_path)

        # Datei speichern
        file.save(full_path)
        return (f'Datei "{filename}" erfolgreich hochgeladen.', "success")

    except Exception as e:
        _log_message(f"Fehler beim Speichern der Datei: {e}", "error")
        return ("Die Datei konnte aufgrund eines Serverfehlers nicht gespeichert werden.", "error")


def _log_message(message: str, category: str = "info"):
    """Loggt eine Nachricht mit einer Kategorie (info, warning, error)

    Args:
        message (str): Nachricht, die geloggt werden soll
        category (str, optional): Kategorie der Nachricht. Defaults to "info".
    """
    print(message)
    if category == "info":
        logging.info(message)
    elif category == "warning":
        logging.warning(message)
    elif category == "error":
        logging.error(message)


# + ----------------------------------------------------------------------------
# + AUTHENTIFIZIERUNG
# + ----------------------------------------------------------------------------
def __check_auth(username, password) -> bool:
    """Überprüft, ob username und Passwort stimmen

    Args:
        username (str): Benutzername, der überprüft werden soll
        password (str): Passwort, das überprüft werden soll

    Returns:
        bool: True, wenn Beide mit den erlaubten übereinstimmen
    """
    return username == APP.config["UNTIS_USERNAME"] and password == APP.config["UNTIS_PASSWORD"]


def __authenticate():
    """HTML Anfrage zur Authentifizierung"""
    return Response(
        "Login erforderlich",
        401,
        {"WWW-Authenticate": 'Basic realm="Login erforderlich"'},
    )


def _requires_auth(f):
    """Überprüft ob eine Authentifizierung notwendig ist oder bereits durchgeführt wurde"""

    @wraps(f)
    def decorated(*args, **kwargs):

        auth = request.authorization
        if not auth or not __check_auth(auth.username, auth.password):
            return __authenticate()
        return f(*args, **kwargs)

    return decorated


def _get_files_from_upload(UPLOADFOLDER):
    """Liest die absolutenn Pfade aller Dateien im Upload-Ordner aus und liefert sie als Liste zurück

    Args:
        UPLOADFOLDER (str): Ordner, dessen Dateien gelesen werden sollen

    Returns:
        list: Liste aller Dateipfade
    """
    files = []
    if os.path.exists(UPLOADFOLDER):
        for f in os.listdir(UPLOADFOLDER):
            # Stelle sicher, dass nur Dateien und keine Unterordner angezeigt werden
            if os.path.isfile(os.path.join(UPLOADFOLDER, f)):
                files.append(f)
    files.sort()
    return files
