from dataclasses import dataclass
import logging
import os
from pathlib import Path

from flask import Flask
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()  # noch ohne App
mail = Mail()


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

    def __init__(self):
        # Die Wichtigsten
        self.db: SQLAlchemy = db
        self.mail = mail
        self.app: Flask = None

        self.kontaktperson: dataclass | None = None

        # Pfade zu den verschiedenen Dateien
        self.datafolder: Path | None = None

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
        self.datafolder = Path(app.root_path) / "data"
        self.uploadfolder = Path(app.root_path) / "upload"

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


# 2) App-weiter Zustand (State) vorbereiten
state = AppState()
