import logging
from pathlib import Path
import tomllib

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()  # noch ohne App
mail = Mail()

limiter = Limiter(
    get_remote_address,
    default_limits=["10 per minute"],
    storage_uri="memory://",
)

logger = logging.getLogger(__name__)


class AppState:
    """verkörpert Zustände, die während der Laufzeit gespeichert werden müssen"""

    _LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
    _LOG_FILE = "untis.log"

    _STATIC_DIR = Path(__file__).resolve().parent / "static"
    _DATA_DIR = Path(__file__).resolve().parent / "data"
    _UPLOAD_DIR = Path(__file__).resolve().parent / "upload"

    def __init__(self):
        # Die Wichtigsten
        self.db: SQLAlchemy = db
        self.mail = mail
        self.app: Flask = None
        self.limiter: Limiter | None = Limiter(
            get_remote_address,
            default_limits=["10 per minute"],
            storage_uri="memory://",
        )

        # Pfade zu den verschiedenen Dateien
        self.staticfolder: Path = self._STATIC_DIR
        self.datafolder: Path = self._DATA_DIR
        self.uploadfolder: Path = self._UPLOAD_DIR

        # Dateien mit Pfad
        self.infofile: Path | None = None
        self.tomlfile: Path | None = None
        self.prototypeazubi: Path | None = None
        self.prototypeausbilder: Path | None = None
        self.logfile: Path = self.__ensure_file_exists(self._LOG_DIR, self._LOG_FILE)

        # Texte aus text.toml
        self.infos: dict | None = None

        self.allowed_extensions = ["csv", "pdf"]
        self.codecs = ["UTF-8", "ISO-8859-1", "utf-8-sig"]

    def set_data(self, app: Flask, **kwargs):
        """setzt die Pfade der Dateien und lädt die Textbausteine

        Args:
            app (Flask): ap

            **kwargs: mehrere Dateinamen

                erlaubte keys sind:
                infofile (str): Name der pdf Datei, die heruntergeladen werden kann
                textfile (str): Name der toml-Datei mit Textbausteinen
                prototypeazubi (str): Name der CSV-Datei im korrekten Format für den Upload
                prototypeausbilder (str): Name der CSV-Datei im korrekten Format für den Upload
        """
        # app in state soeichern
        self.app: Flask = app

        for attr_name, filename in kwargs.items():
            # Alle übergebenden Werte
            if hasattr(self, attr_name):
                # Es gibt den Schlüssel hier in der Class
                file_path = self.__ensure_file_exists(self.datafolder, filename)
                setattr(self, attr_name, file_path)

                logger.info(f"Datei: {attr_name} vorhanden")

        # Textbausteine laden
        self.load_texts()

    def load_texts(self) -> None:
        """Lädt die Texte aus der TOML-Datei in den internen Cache."""
        try:
            with open(self.tomlfile, "rb") as f:
                self.infos = tomllib.load(f)

            logger.info("Texte geladen aus: %s", self.tomlfile)
        except FileNotFoundError:
            logger.error("texts.toml nicht gefunden: %s", self.tomlfile)
            self.infos = {}
        except tomllib.TOMLDecodeError:
            logger.exception("Fehler beim Parsen von texts.toml")
            self.infos = {}

    def get_text(self, section: str, key: str, fallback: str = "") -> str:
        """Gibt einen Text aus dem Cache zurück.

        Args:
            section:  Abschnitt in der TOML-Datei, z. B. "anmeldung".
            key:      Schlüssel innerhalb des Abschnitts, z. B. "intro".
            fallback: Rückgabewert, wenn Abschnitt oder Schlüssel fehlen.

        Returns:
            str: Der gefundene Text oder der Fallback.
        """
        return self.infos.get(section, {}).get(key, fallback)

    def get_section(self, section: str) -> dict[str, str]:
        """Gibt einen ganzen Abschnitt zurück (z. B. für Template-Übergabe).

        Args:
            section: Abschnitt in der TOML-Datei.

        Returns:
            dict[str, str]: Alle Key-Value-Paare des Abschnitts, oder leeres Dict.
        """
        return self.infos.get(section, {})

    def __ensure_file_exists(self, directory: str, filename: str) -> Path:
        # 1. Sicherstellen, dass directory ein String ist (falls None übergeben wurde)
        directory_str = directory or "."

        # 2. Pfad-Objekt erstellen
        filepath = Path(directory_str) / filename

        try:
            # 3. Elternverzeichnis erstellen, falls es nicht existiert
            filepath.parent.mkdir(parents=True, exist_ok=True)

            # 4. Datei erstellen (tut nichts, wenn sie schon existiert)
            filepath.touch(exist_ok=True)

            # 5. Absoluten Pfad zurückgeben
            return filepath.resolve()

        except Exception as e:
            logger.exception(f"Kann Datei nicht anlegen: {filepath}: ({e})")
            # 6. Im Fehlerfall ein leeres Pfad-Objekt zurückgeben
            return Path()


# ------------------------------------------------------------------------------
# Modul-Singleton
# ------------------------------------------------------------------------------

state = AppState()
