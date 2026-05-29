import os
from csv import DictReader as csv_DictReader
from csv import DictWriter as csv_DictWriter
from datetime import datetime
from typing import Dict, List

from flask import current_app

from src.base import Ausbilder, Azubis, _get_ausbilder_list, _get_azubi_list
from src.config import CODECS


def __get_codec(testfile) -> str:
    """Überprüft eine CSV Datei um den codec zu ermitteln
    Liefert den codec der CSV-Datei oder einen leerer String zurück
    Args:
        testfile: (str) Adresse der CSV Datei

    Returns:
    string: codec
    """
    for codec in CODECS:
        try:
            with open(testfile, encoding=codec) as f:
                # Ein paar Zeilen lesen und prüfen, ob CSV-Reader starten kann
                reader = csv_DictReader(f)
                # Versuche, die erste Daten- oder Header-Zeile zu lesen
                next(reader)  # kann StopIteration werfen, wenn Datei leer ist → trotzdem gültig
            # Kein Fehler, also richtigen Codec zurückgeben
            return codec

        except StopIteration:
            # Leere Datei – Encoding hat technisch funktioniert
            return codec
        except UnicodeDecodeError:
            # Falsches Encoding – weiterprobieren
            continue
        except Exception as e:
            # Unerwarteter Fehler (z. B. IO); loggen und weiterprobieren
            current_app.logger.debug("__get_codec: Fehler mit Codec %s für %s: %s", codec, testfile, e)
            continue
    # Kein Codec war richtig
    return ""


def _merge_csv_files(uploadfolder: str, destfile: str) -> bool:
    """Liest alle Dateien im Upload-Ordner und verbindet sie zu einer Datei (Trennzeichen ';').

    Args:
        uploadfolder (str): adresse des Ordners, im dem die CSV-Dateien gesucht werden
        destfile (str): Adresse der Datei, die in der die Daten gespeichert werden

    Returns:
        bool: True bei Erfolg
    """
    # Flag für Header. Nur der erste Header wird gespeichert
    header_written = False

    try:
        # 1) Liste der Dateien (nur reguläre Dateien) — deterministische Reihenfolge
        all_entries = sorted(os.listdir(uploadfolder))
        ls_files_to_merge = [
            os.path.join(uploadfolder, fn) for fn in all_entries if os.path.isfile(os.path.join(uploadfolder, fn))
        ]
        if not ls_files_to_merge:
            current_app.logger.info("Keine Dateien zum Zusammenführen im Ordner %s", uploadfolder)
            return True  # Nichts zu tun — gilt als Erfolg

        # codec der ersten Datei herausfinden
        codec = __get_codec(ls_files_to_merge[0])
        with open(destfile, "w") as f:
            for tempfile in ls_files_to_merge:
                with open(tempfile, encoding=codec) as inputFile:
                    lines = list(inputFile)
                    if header_written:
                        # Alle, außer dem ersten Header werden entfernt
                        lines.pop(0)

                    for line in lines:
                        # Normalisiere Zeilenenden und ersetze Tabs durch Semikolon
                        f.write(line.replace("\t", ";"))
                # Nach der ersten Datei wird kein weiterer header benötigt
                header_written = True

        return True

    except Exception as e:
        current_app.logger.exception("Fehler beim Zusammenführen von CSV-Dateien: %s", e)
        return False


def _export_to_csv(klasse: str, resultfile: str) -> str:
    """erstellt eine CSV Datei mit Azubis einer
    und speichert sie in resultfile

    Args:
        klasse (str): Name der Klasse aus der DB

    Returns:
        str: absoluter Pfad der Datei
    """
    try:
        if klasse == "ausbilder":
            toCSV: List[Dict] = _get_ausbilder_list()
        else:
            toCSV = _get_azubi_list(klasse)
        # Header ist in erster Zeile [0]
        fieldnames = toCSV[0].keys()
        with open(resultfile, "w", encoding="utf8", newline="") as output_file:
            fc = csv_DictWriter(output_file, fieldnames=fieldnames, delimiter=";")
            fc.writeheader()
            fc.writerows(toCSV)

        current_app.logger.info("CSV-Export erstellt: %s (Klasse=%s, Zeilen=%d)", resultfile, klasse, len(toCSV))
        return os.path.abspath(resultfile)
    except (OSError, IOError) as io_err:
        current_app.logger.exception(f"IO-Fehler beim CSV-Export: {io_err}")
        return None

    except Exception as e:
        current_app.logger.exception(f"Unbekannter Fehler beim CSV-Export: : {e}")
        return None


def _import_azubis_from_csv(csv_file):
    """Importiert Azubis aus einer Semikolon-separierten CSV-Datei und gibt ORM-Objekte zurück.
    Erwartete Spalten:
      - externKey, name, longName, foreName, birthDate, klasse.name

    Filter:
      - Nur Zeilen, deren 'klasse.name' mit 'BS' (case-insensitive) beginnt.

    Args:
        csv_file (str): Pfad zur CSV-Datei.

    Returns:
        list: Liste mit Azubis-ORM-Objekten. Bei Fehlern leere Liste.
    """
    # codec für Linux und Windows herausfinden
    codec = __get_codec(csv_file)

    azubis_liste: List[Azubis] = []

    try:
        with open(csv_file, mode="r", encoding=codec, errors="replace") as f:
            for row in csv_DictReader(f, delimiter=";"):
                if row["klasse.name"].startswith(("BS", "bs")):
                    azubis_liste.append(
                        Azubis(
                            schueler_stamm_id=(row.get("externKey") or "").strip(),
                            schueler_untis_id=row["name"].replace(" ", "_"),
                            schueler_familienname=(row.get("longName") or "").strip(),
                            schueler_rufname=(row.get("foreName") or "").strip(),
                            schueler_geburtsdatum=(row.get("birthDate") or "").strip(),
                            klasse=(row.get("klasse.name") or "").strip(),
                        )
                    )
        return azubis_liste

    except FileNotFoundError:
        current_app.logger.error("CSV-Datei nicht gefunden: %s", csv_file)
        return []
    except Exception as e:
        current_app.logger.exception("Fehler in _import_ausbilder_from_csv (%s): %s", csv_file, e)
        return []


def _import_ausbilder_from_csv(csv_file):
    """Liest Ausbilder-Datensätze aus einer CSV-Datei und gibt ORM-Objekte zurück.
    Erwartetes CSV-Format (Semikolon-getrennt):
      - ausbilder_email, ausbilder_name, ausbilder_vorname, ausbilder_betrieb
      - bestaetigt (beliebige truthy Werte wie '1', 'true', 'ja')
      - token
      - created_at (Format: '%Y-%m-%d %H:%M:%S.%f')
    Args:
        csv_file (_type_): Pfad zur CSV-Datei.

    Returns:
        list: Liste mit Ausbilder-ORM-Objekten. Bei Fehlern leere Liste.
    """
    # codec für Linux und Windows herausfinden
    codec = __get_codec(csv_file)

    ausbilder_liste: List[Ausbilder] = []

    try:
        with open(csv_file, mode="r", encoding=codec, errors="replace") as f:
            for row in csv_DictReader(f, delimiter=";"):
                created_at = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S.%f")
                bestaetigt = True if row["bestaetigt"] else False
                ausbilder_liste.append(
                    Ausbilder(
                        ausbilder_email=row["ausbilder_email"],
                        ausbilder_name=row["ausbilder_name"],
                        ausbilder_vorname=row["ausbilder_vorname"],
                        ausbilder_betrieb=row["ausbilder_betrieb"],
                        bestaetigt=bestaetigt,
                        token=row["token"],
                        created_at=created_at,
                    )
                )
        return ausbilder_liste

    except FileNotFoundError:
        current_app.logger.error("CSV-Datei nicht gefunden: %s", csv_file)
        return []
    except Exception as e:
        current_app.logger.exception("Fehler in _import_ausbilder_from_csv (%s): %s", csv_file, e)
        return []
