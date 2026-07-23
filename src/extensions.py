from dataclasses import dataclass
import logging
import os
from pathlib import Path

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


@dataclass
class Kontaktpersondata:
    """
    Repräsentiert eine Datenstruktur aus vier Strings mit dataclasses.
    """

    vorname: str
    nachname: str
    mail: str
    komplett: str


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
        self.kontaktperson: dataclass | None = None

        # Pfade zu den verschiedenen Dateien
        self.staticfolder: Path = self._STATIC_DIR
        self.datafolder: Path = self._DATA_DIR
        self.uploadfolder: Path = self._UPLOAD_DIR

        self.infofile: Path | None = None
        self.prototypeazubi: Path | None = None
        self.prototypeausbilder: Path | None = None

        self.allowed_extensions = ["csv", "pdf"]
        self.codecs = ["UTF-8", "ISO-8859-1"]
        self.infotexte = {
            "index_1": os.getenv("TEXT_INDEX_1"),
            "index_2": os.getenv("TEXT_INDEX_2"),
            "azubismitausbilder": os.getenv("TEXT_AZUBIMITAUSBILDER"),
        }
        self.logfile: Path = self.__ensure_file_exists(self._LOG_DIR, self._LOG_FILE)

    def set_kontaktperson(self, vorname: str, nachname: str, mail: str):
        self.kontaktperson = Kontaktpersondata(
            vorname,
            nachname,
            mail,
            f"{nachname}, {vorname} ({mail})",
        )

    def set_data(self, app, **kwargs):
        """setzt die Pfade der Dateien und initialisiert die Schulformen

        Args:
            datafolder (path): absoluter Pfad zum Ordner der Dateien

            **kwargs: mehrere Dateinamen

                erlaubte keys sind:
                klassenfile (str): Name der CSV-Datei mit den Klassennamen für den Upload
                prototypefile (str): Name der CSV-Datei im korrekten Format für den Upload
        """
        self.app: Flask = app

        for attr_name, filename in kwargs.items():
            # Alle übergebenden Werte
            if hasattr(self, attr_name):
                # Es gibt den Schlüssel hier in der Class
                file_path = self.__ensure_file_exists(self.datafolder, filename)
                setattr(self, attr_name, file_path)
                logger.info(f"Datei: {attr_name} vorhanden")

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
