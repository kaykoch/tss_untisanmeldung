# ------------------------------------------------------------------------------
# Überprüft durch Claude 4
# ------------------------------------------------------------------------------

from io import BytesIO
import logging
from pathlib import Path

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
    return BytesIO(file.read())


def save_file(file, file_path: str) -> tuple[str, str]:
    """Speichert eine Datei unter einem festen Zielpfad (inkl. Dateiname).

    Args:
        file:      FileStorage-Objekt
        file_path: Vollständiger Zielpfad inklusive Dateiname.

    Returns:
        Tuple (Nachricht, Kategorie) mit Kategorie in {"success", "error"}.
    """
    try:
        target = Path(file_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        file.seek(0)
        file.save(str(target))
        return (f'Datei "{target.name}" erfolgreich gespeichert.', "success")
    except Exception:
        logger.exception("save_file_as: Fehler beim Speichern")
        return ("Die Datei konnte nicht gespeichert werden.", "error")


def upload_file(file, upload_dir: Path) -> tuple[str, str]:
    """Speichert eine hochgeladene Datei unter ihrem Originalnamen im Zielordner.

    Verwendung: Upload-Bereich – Originalname bleibt erhalten.

    Args:
        file:       FileStorage-Objekt.
        upload_dir: Zielordner (ohne Dateiname).
    """
    try:
        safe_name = secure_filename(file.filename or "")
        if not safe_name:
            return ("Ungültiger oder fehlender Dateiname.", "error")
        if not _is_allowed_file(safe_name):
            return ("Dateityp nicht erlaubt.", "error")

        target = (Path(upload_dir).resolve() / safe_name).resolve()

        if not target.is_relative_to(Path(upload_dir).resolve()):
            logger.warning("upload_file: Path-Traversal-Versuch: %s", safe_name)
            return ("Ungültiger Dateiname/Pfad.", "error")

        target.parent.mkdir(parents=True, exist_ok=True)
        file.seek(0)
        file.save(str(target))
        return (f'Datei "{safe_name}" erfolgreich hochgeladen.', "success")

    except OSError as e:
        logger.error("upload_file: Fehler beim Erstellen des Zielordners: %s", e)
        return ("Zielordner kann nicht erstellt werden.", "error")
    except Exception:
        logger.exception("upload_file: Fehler beim Speichern")
        return ("Die Datei konnte nicht gespeichert werden.", "error")


def get_files_from_upload(upload_folder: str | Path) -> list[str]:
    """Gibt eine sortierte Liste aller Dateinamen im Upload-Ordner zurück.

    Args:
        upload_folder: Pfad zum Upload-Verzeichnis.

    Returns:
        Sortierte Liste von Dateinamen (ohne Unterordner).
    """
    folder = Path(upload_folder)
    if not folder.exists():
        return []
    files = [f.name for f in folder.iterdir() if f.is_file()]
    return sorted(files)


def _is_allowed_file(filename: str) -> bool:
    """Gibt True zurück, wenn die Dateiendung in der Erlaubt-Liste steht

    Args:
        filename (str): Dateiname, der überprüft werden soll

    Returns:
        bool: True, wenn erlaubt
    """
    allowed = getattr(state, "allowed_extensions", None)
    if not allowed:
        logger.warning("_is_allowed_file: allowed_extensions ist leer oder nicht gesetzt.")
        return False
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def delete_file_safe(filename: str) -> tuple[str, str]:
    """Löscht eine einzelne Datei sicher aus dem Upload-Ordner.
    Gibt ein Tuple (Nachricht, Kategorie) zurück

    Args:
        filename (str): Datei, die gelöscht werden soll

    Returns:
        tuple[str, str]: (Nachricht, Kategorie) zur Ausgabe mit flash
    """
    if not filename:
        return ("Kein Dateiname angegeben.", "error")

    safe_name = secure_filename(filename)
    if not safe_name:
        return ("Ungültiger Dateiname.", "error")

    upload_dir = Path(state.uploadfolder).resolve()
    file_path = (upload_dir / safe_name).resolve()

    # Sicherstellen, dass der Pfad wirklich im Upload-Ordner liegt
    if not file_path.is_relative_to(upload_dir):
        logger.warning("Path-Traversal-Versuch erkannt: %s", filename)
        return ("Ungültiger Dateiname.", "error")

    if file_path.exists():
        try:
            file_path.unlink()
            return (f'Datei "{safe_name}" wurde gelöscht.', "success")
        except OSError:
            logger.exception("delete_file_safe: Fehler beim Löschen der Datei: %s", file_path)
            return (f'Datei "{safe_name}" konnte nicht gelöscht werden.', "error")
    else:
        return ("Die Datei wurde nicht gefunden.", "error")
