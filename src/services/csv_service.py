# ------------------------------------------------------------------------------
#  CSV-Hilfsfunktionen
# ------------------------------------------------------------------------------
from collections.abc import Callable, Iterable
import csv
from datetime import datetime
import glob
from io import BytesIO, StringIO, TextIOWrapper
import logging
import os
from typing import Any

from src.extensions import state
from src.models import Ausbilder, Azubis
from src.services.ausbilder_service import get_ausbilder_list_for_csv
from src.services.azubi_service import get_azubi_list_for_csv


logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Hilfsfunktionen – intern
# ------------------------------------------------------------------------------


def _get_codec(testfile: str) -> str:
    """Ermittelt den Zeichensatz (Codec) einer CSV-Datei durch Probieren.

    Gibt den ersten funktionierenden Codec aus `state.codecs` zurück,
    oder einen leeren String, wenn keiner passt.

    Args:
        testfile: Pfad zur CSV-Datei.

    Returns:
        Codec-String (z. B. "utf-8") oder "" bei Misserfolg.
    """
    for codec in state.codecs:
        try:
            with open(testfile, encoding=codec) as f:
                reader = csv.DictReader(f)
                next(reader)  # StopIteration bei leerer Datei ist trotzdem gültig
            return codec
        except StopIteration:
            return codec  # Leere Datei – Encoding hat funktioniert
        except UnicodeDecodeError:
            continue  # Falsches Encoding – nächsten versuchen
        except Exception as e:
            logger.debug("_get_codec: Fehler mit Codec %s für %s: %s", codec, testfile, e)
            continue
    return ""


def _read_csv_file(filepath: str) -> tuple[list[str], list[dict]]:
    """Liest eine einzelne CSV-Datei (Semikolon-getrennt, UTF-8) ein.

    Returns:
        Tuple aus Spaltennamen und Liste von Zeilen-Dicts.

    Verwendet von: merge_csv_to_bytesio
    """
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def write_dicts_to_bytesio(fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> BytesIO:
    """
    Semikolon-CSV, UTF-8-BOM (utf-8-sig) und CRLF (Windows/Excel-freundlich).
    - fieldnames: Liste der Spaltenüberschriften / Reihenfolge
    - rows: Iterable von Dicts (keys werden nach fieldnames gemappt)
    """
    str_io = StringIO()
    writer = csv.DictWriter(
        str_io,
        fieldnames=fieldnames,
        delimiter=";",
        lineterminator="\r\n",  # CRLF für Excel
        extrasaction="ignore",
        restval="",
    )
    writer.writeheader()
    # writer.writerows akzeptiert Iterable[list|tuple], sicherheitshalber in Liste umwandeln,
    # falls rows ein Generator ist
    writer.writerows(list(rows))

    # UTF-8 with BOM für Excel:
    bytes_io = BytesIO(str_io.getvalue().encode("utf-8-sig"))
    bytes_io.seek(0)
    return bytes_io


def _read_bytesio_as_csv(bytes_io: BytesIO) -> csv.DictReader:
    """Setzt den BytesIO-Zeiger zurück und gibt einen DictReader zurück.

    Hinweis: Der Aufrufer ist verantwortlich für das Schließen des TextIOWrapper.

    Verwendet von: _generic_bytesio_import
    """
    bytes_io.seek(0)
    wrapper = TextIOWrapper(bytes_io, encoding="utf-8", errors="replace", newline="")
    return csv.DictReader(wrapper, delimiter=";"), wrapper


def _generic_bytesio_import(
    bytes_io: BytesIO, row_mapper: Callable[[dict], Any | None], context: str = ""
) -> list[Any]:
    """Liest ein BytesIO-Objekt zeilenweise als CSV und wendet eine Mapping-Funktion an.

    Gibt eine leere Liste zurück, wenn ein Fehler auftritt.

    Args:
        bytes_io:   Quelle der CSV-Daten.
        row_mapper: Funktion, die eine CSV-Zeile in ein Objekt umwandelt
                    oder None zurückgibt (Zeile überspringen).
        context:    Optionaler Name für Logging-Ausgaben.

    Verwendet von: import_azubis_from_bytesio, import_ausbilder_from_bytesio
    """
    bytes_io.seek(0)
    ergebnis: list[Any] = []

    try:
        with TextIOWrapper(bytes_io, encoding="utf-8", errors="replace", newline="") as f:
            for row in csv.DictReader(f, delimiter=";"):
                item = row_mapper(row)
                if item is not None:
                    ergebnis.append(item)
        return ergebnis
    except Exception as e:
        logger.error("Fehler beim BytesIO-Import (%s): %s", context or row_mapper.__name__, e)
        return []


def _generic_csv_import(csv_file: str, row_mapper: Callable[[dict], Any | None]) -> list[Any]:
    """Liest eine CSV-Datei zeilenweise ein und wendet eine Mapping-Funktion an.

    Ermittelt den Codec automatisch via `_get_codec`. Gibt eine leere Liste
    zurück, wenn die Datei nicht gefunden wird oder ein Fehler auftritt.

    Args:
        csv_file:   Pfad zur CSV-Datei.
        row_mapper: Funktion, die eine CSV-Zeile in ein Objekt umwandelt
                    oder None zurückgibt (Zeile überspringen).

    Verwendet von: import_azubis_from_csv, import_ausbilder_from_csv
    """
    codec = _get_codec(csv_file)
    ergebnis: list[Any] = []

    try:
        with open(csv_file, encoding=codec, errors="replace") as f:
            for row in csv.DictReader(f, delimiter=";"):
                item = row_mapper(row)
                if item is not None:
                    ergebnis.append(item)
        return ergebnis
    except FileNotFoundError:
        logger.error("CSV-Datei nicht gefunden: %s", csv_file)
        return []
    except Exception as e:
        logger.error("Fehler beim CSV-Import (%s) mit %s: %s", csv_file, row_mapper.__name__, e)
        return []


def _map_azubi_from_untis(row: dict) -> Azubis | None:
    """Wandelt eine Untis-CSV-Zeile in ein Azubis-Objekt um.

    Filtert Zeilen, deren Klassenname nicht mit "BS" oder "bs" beginnt.

    Args:
        row: CSV-Zeile als Dict (Untis-Format mit externKey, longName, …).

    Returns:
        Azubis-Objekt oder None (Zeile überspringen).

    Verwendet von: import_azubis_from_csv
    """
    if not row.get("klasse.name", "").startswith(("BS", "bs")):
        return None

    return Azubis(
        schueler_stamm_id=(row.get("externKey") or "").strip(),
        schueler_untis_id=row.get("name", "").replace(" ", "_"),
        schueler_familienname=(row.get("longName") or "").strip(),
        schueler_rufname=(row.get("foreName") or "").strip(),
        schueler_geburtsdatum=(row.get("birthDate") or "").strip(),
        klasse=(row.get("klasse.name") or "").strip(),
    )


def _map_azubi_from_db(row: dict) -> Azubis | None:
    """Wandelt eine DB-Export-CSV-Zeile in ein Azubis-Objekt um.

    Filtert Zeilen, deren Klasse nicht mit "BS" oder "bs" beginnt.

    Args:
        row: CSV-Zeile als Dict (DB-Format mit schueler_stamm_id, klasse, …).

    Returns:
        Azubis-Objekt oder None (Zeile überspringen).

    Verwendet von: import_azubis_from_bytesio
    """
    if not row.get("klasse", "").startswith(("BS", "bs")):
        return None

    return Azubis(
        schueler_stamm_id=row.get("schueler_stamm_id", ""),
        schueler_untis_id=row.get("schueler_untis_id", ""),
        schueler_familienname=row.get("schueler_familienname", ""),
        schueler_rufname=row.get("schueler_rufname", ""),
        schueler_geburtsdatum=row.get("schueler_geburtsdatum", ""),
        klasse=row.get("klasse", ""),
    )


def _map_ausbilder(row: dict) -> Ausbilder:
    """Wandelt eine CSV-Zeile in ein Ausbilder-Objekt um.

    Args:
        row: CSV-Zeile als Dict mit allen Ausbilder-Feldern.

    Returns:
        Ausbilder-Objekt.

    Raises:
        KeyError:   Falls ein benötigtes Feld fehlt.
        ValueError: Falls created_at nicht im Format %Y-%m-%d %H:%M:%S.%f vorliegt.

    Verwendet von: import_ausbilder_from_csv, import_ausbilder_from_bytesio
    """
    return Ausbilder(
        ausbilder_email=row["ausbilder_email"],
        ausbilder_name=row["ausbilder_name"],
        ausbilder_vorname=row["ausbilder_vorname"],
        ausbilder_betrieb=row["ausbilder_betrieb"],
        bestaetigt=row["bestaetigt"].strip().lower() == "true",  # bool("False") wäre True!
        token=row["token"],
        created_at=datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S.%f"),
    )


# ------------------------------------------------------------------------------
# Öffentliche Funktionen
# ------------------------------------------------------------------------------


def merge_csv_to_bytesio(upload_folder: str) -> BytesIO:
    """Liest alle CSV-Dateien im Upload-Ordner und fügt sie zu einem BytesIO zusammen.

    Alle Dateien müssen dieselben Spalten haben (Semikolon-getrennt, UTF-8).

    Raises:
        FileNotFoundError: Wenn keine CSV-Dateien im Ordner gefunden wurden.
    """
    search_path = os.path.join(upload_folder, "*.csv")
    csv_files = glob.glob(search_path)

    if not csv_files:
        raise FileNotFoundError(f"Keine CSV-Dateien in {upload_folder} gefunden.")

    all_rows: list[dict] = []
    fieldnames: list[str] = []

    for filepath in csv_files:
        headers, rows = _read_csv_file(filepath)
        if not fieldnames:
            fieldnames = headers  # Spalten der ersten Datei als Referenz
        all_rows.extend(rows)

    return write_dicts_to_bytesio(fieldnames, all_rows)


def export_to_csv(klasse: str) -> BytesIO | None:
    """Exportiert Ausbilder- oder Azubidaten als Semikolon-CSV in ein BytesIO-Objekt.

    Args:
        klasse: "ausbilder" für Ausbilderliste, sonst Klassenname für Azubis.

    Returns:
        BytesIO mit CSV-Inhalt, oder None bei Fehler.
    """
    list_to_csv = get_ausbilder_list_for_csv() if klasse == "ausbilder" else get_azubi_list_for_csv(klasse)

    try:
        if list_to_csv is None:
            raise ValueError("Die Datenliste darf nicht None sein.")

        if not list_to_csv:
            empty = BytesIO()
            empty.seek(0)
            return empty

        fieldnames = list(list_to_csv[0].keys())
        return write_dicts_to_bytesio(fieldnames, list_to_csv)

    except ValueError as e:
        logger.exception("export_to_csv -> %s", e)
        return None
    except OSError as e:
        logger.exception("export_to_csv -> %s", e)
        return None


def import_azubis_from_bytesio(bytes_io: BytesIO) -> list[Azubis]:
    """Importiert Azubis aus einem BytesIO-Objekt (DB-Export-Format).

    Nur Zeilen mit Klassen, die mit "BS" oder "bs" beginnen, werden importiert.
    """
    return _generic_bytesio_import(bytes_io, _map_azubi_from_db, context="azubis")


def import_ausbilder_from_bytesio(bytes_io: BytesIO) -> list[Ausbilder]:
    """Importiert Ausbilder aus einem BytesIO-Objekt.

    Alle Felder müssen in der CSV vorhanden sein.
    """
    return _generic_bytesio_import(bytes_io, _map_ausbilder, context="ausbilder")


# ------------------------------------------------------------------------------
# nicht genutzt
# ------------------------------------------------------------------------------
def import_azubis_from_csv(csv_file: str) -> list[Azubis]:
    """Importiert Azubis aus einer Untis-CSV-Datei (Dateipfad).

    Nur Zeilen mit Klassen, die mit "BS" oder "bs" beginnen, werden importiert.
    """
    return _generic_csv_import(csv_file, _map_azubi_from_untis)


def import_ausbilder_from_csv(csv_file: str) -> list[Ausbilder]:
    """Importiert Ausbilder aus einer CSV-Datei (Dateipfad).

    Alle Felder müssen in der CSV vorhanden sein.
    """
    return _generic_csv_import(csv_file, _map_ausbilder)
