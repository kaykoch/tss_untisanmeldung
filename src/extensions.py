# ------------------------------------------------------------------------------
# Überprüft durch Claude 4
# ------------------------------------------------------------------------------

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

limiter = Limiter(get_remote_address, default_limits=["10 per minute"], storage_uri="memory://")

logger = logging.getLogger(__name__)


class TomlState:
    """verkörpert die Texte aus einer Tomldatei"""

    def __init__(self, data: dict):
        for key, value in data.items():
            if isinstance(value, dict):
                # Verschachtelte Dictionaries ebenfalls umwandeln
                setattr(self, key, TomlState(value))
            else:
                setattr(self, key, value)


class AppState:
    """verkörpert Zustände, die während der Laufzeit gespeichert werden müssen"""

    _LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
    _LOG_FILE = "untis.log"

    _STATIC_DIR = Path(__file__).resolve().parent / "static"
    _DATA_DIR = Path(__file__).resolve().parent / "data"
    _UPLOAD_DIR = Path(__file__).resolve().parent / "upload"

    def __init__(self):
        # Extensions / App
        self.db: SQLAlchemy = db
        self.mail = mail
        self.limiter: Limiter = limiter
        self.app: Flask | None = None

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
        self.infos: TomlState = TomlState({})

        self.allowed_extensions = ["csv", "pdf"]
        self.codecs = ["UTF-8", "ISO-8859-1", "utf-8-sig"]

    def set_data(self, app: Flask, **kwargs):
        """setzt die Pfade der Dateien und lädt die Textbausteine

        Args:
            app (Flask): ap

            **kwargs: mehrere Dateinamen

                erlaubte keys sind:
                infofile (str): Name der pdf Datei, die heruntergeladen werden kann
                tomlfile (str): Name der toml-Datei mit Textbausteinen
                prototypeazubi (str): Name der CSV-Datei im korrekten Format für den Upload
                prototypeausbilder (str): Name der CSV-Datei im korrekten Format für den Upload
        """
        # app in state soeichern
        self.app = app

        for attr_name, filename in kwargs.items():
            if hasattr(self, attr_name) and isinstance(filename, str) and filename:
                file_path = self.__ensure_file_exists(self.datafolder, filename)
                setattr(self, attr_name, file_path)
                logger.info("Datei '%s' vorhanden: %s", attr_name, file_path)

        # Falls tomlfile nicht angegeben war: auf Standard texts.toml im data-Ordner setzen
        if self.tomlfile is None:
            self.tomlfile = self.__ensure_file_exists(self.datafolder, "texts.toml")
            logger.info("Standard TOML gesetzt: %s", self.tomlfile)
        # Textbausteine laden
        self.infos = self.load_texts(self.tomlfile)

    def load_texts(self, tomlfile) -> None:
        """Lädt die Texte aus der TOML-Datei in den internen Cache."""
        if tomlfile is None:
            logger.warning("Keine TOML-Datei angegeben; verwende leere Texte.")
            return TomlState({})
        try:
            with open(tomlfile, "rb") as f:
                data = tomllib.load(f)
            logger.info("Texte geladen aus: %s", tomlfile)
            return TomlState(data)

        except FileNotFoundError:
            logger.error("texts.toml nicht gefunden: %s", tomlfile)
            return TomlState({})
        except tomllib.TOMLDecodeError:
            logger.exception("Fehler beim Parsen von texts.toml")
            return TomlState({})

    def __ensure_file_exists(self, directory: Path | str, filename: str) -> Path:
        # 1. Pfad-Objekt erstellen
        base = Path(directory) if directory else Path(".")
        filepath = base / filename

        try:
            # 2. Elternverzeichnis erstellen
            filepath.parent.mkdir(parents=True, exist_ok=True)
            # 3. Datei anlegen (wenn fehlend)
            filepath.touch(exist_ok=True)
            # 4. Absoluten Pfad zurückgeben
            return filepath.resolve()
        except Exception as e:
            logger.exception("Kann Datei nicht anlegen: %s (%s)", filepath, e)
            return Path()


# ------------------------------------------------------------------------------
# Modul-Singleton
# ------------------------------------------------------------------------------

state = AppState()
