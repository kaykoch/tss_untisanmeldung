from io import BytesIO
import logging
import os
from pathlib import Path

from flask import (
    flash,
)
from werkzeug.utils import secure_filename

from src.extensions import state


logger = logging.getLogger(__name__)


def uploaded_file_to_bytesio(file) -> BytesIO:
    """Liest eine hochgeladene Datei in ein BytesIO-Objekt ein.

    Args:
        file: Datei-Storage-Objekt (z. B. aus request.files).

    Returns:
        BytesIO mit dem Dateiinhalt, Zeiger am Anfang.
    """
    buf = BytesIO(file.read())
    buf.seek(0)
    return buf


def save_file(file, file_path: str) -> tuple[str, str]:
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


def get_files_from_upload(upload_folder: str) -> list[str]:
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


def _is_allowed_file(filename: str) -> bool:
    """Gibt True zurück, wenn die Dateiendung in der Erlaubt-Liste steht."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in state.allowed_extensions


def delete_file_safe(filename: str) -> None:
    """Löscht eine einzelne Datei sicher aus dem Upload-Ordner.

    Gibt Flash-Feedback bei Erfolg, fehlendem Namen und Fehlern.

    Verwendet von: route_filehandling (Aktionen: delete_single, delete_all)
    """
    if not filename:
        flash("Kein Dateiname angegeben.", "error")
        return
    safe_name = secure_filename(filename)
    file_path = os.path.join(state.uploadfolder, safe_name)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            flash(f'Datei "{safe_name}" wurde gelöscht.', "success")
        except OSError:
            logger.error("Fehler beim Löschen der Datei %s", file_path)
            flash(f'Datei "{safe_name}" konnte nicht gelöscht werden.', "error")
    else:
        flash("Die Datei wurde nicht gefunden.", "error")
