from csv import DictReader as csv_DictReader
from csv import DictWriter as csv_DictWriter
from datetime import datetime
from glob import glob as glob_glob

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
            with open(testfile, encoding=codec) as csvdatei:
                reader = csv_DictReader(csvdatei)
                # Erste Zeile einlesen. Führt zu einem Fehler bei falschem Codec
                next(reader)
            # Kein Fehler, also richtigen Codec zurückgeben
            return codec

        except Exception:
            # Falscher Codec. Weiter mit dem nächsten
            pass
    # Kein Codec war richtig
    return ""


def _merge_csv_files(uploadfolder, destfile) -> bool:
    """Liest alle Dateien im Upload Ordner ein und verbindet sie zu einer
    Die Datei wird mit Trennzeichen ";" gespeichert

    Args:
        uploadfolder (str): adresse des Ordners, im dem die CSV-Dateien gesucht werden
        destfile (str): Adresse der Datei, die in der die Daten gespeichert werden

    Returns:
        bool: True bei Erfolg
    """
    # Liste aller Dateien erstellen
    ls_files_to_merge = glob_glob(f"{uploadfolder}/*")
    # codec der ersten Datei herausfinden
    codec = __get_codec(ls_files_to_merge[0])
    # Flag für Header. Nur der erste Header wird gespeichert
    no_header = False

    try:
        with open(destfile, "w") as f:
            for tempfile in ls_files_to_merge:
                with open(tempfile, encoding=codec) as inputFile:
                    lines = list(inputFile)
                    if no_header:
                        # Alle, außer dem ersten Header werden entfernt
                        lines.pop(0)

                    for line in lines:
                        # Alle Zeilen werden gespeichert, nachdem das Trennzeichen von TAB -> ; geändert wurde
                        f.write(line.replace("\t", ";"))
                # Nach der ersten Datei wird kein weiterer header benötigt

                no_header = True
        return True

    except Exception as e:
        print("__merge_csv_files", e)
        return False


def _export_to_csv(klasse: str, resultfile: str) -> str:
    """erstellt eine CSV Datei mit Azubis einer
    und speichert sie in resultfile

    Args:
        klasse (str): Name der Klasse aus der DB

    Returns:
        str: absoluter Pfad der Datei
    """
    if klasse == "ausbilder":
        toCSV = _get_ausbilder_list()
    else:
        toCSV = _get_azubi_list(klasse)

    with open(resultfile, "w", encoding="utf8", newline="") as output_file:
        fc = csv_DictWriter(output_file, fieldnames=toCSV[0].keys(), delimiter=";")
        fc.writeheader()
        fc.writerows(toCSV)
    return resultfile


def _import_azubis_from_csv(csv_file):
    """Importiert eine liste mit Azubis von einer CSV-Datei
    und erstellt eine Liste mit mit Azubis vom Datentyp Azubis

    Args:
        csv_file (_type_): Liste mit Azubis, die eingelesen werden soll

    Returns:
        list: Liste mit Azubiss
    """
    # codec für Linux und Windows herausfinden
    codec = __get_codec(csv_file)

    azubis_liste = []

    try:
        with open(csv_file, encoding=codec) as csvdatei:
            for row in csv_DictReader(csvdatei, delimiter=";"):
                if row["klasse.name"].startswith(("BS", "bs")):
                    azubis_liste.append(
                        Azubis(
                            schueler_stamm_id=row["externKey"],
                            schueler_untis_id=row["name"].replace(" ", "_"),
                            schueler_familienname=row["longName"],
                            schueler_rufname=row["foreName"],
                            schueler_geburtsdatum=row["birthDate"],
                            klasse=row["klasse.name"],
                        )
                    )
        return azubis_liste
    except Exception as e:
        print("_import_azubis_from_csv", e)
        return False


def _import_ausbilder_from_csv(csv_file):
    """Importiert eine liste mit Ausbilderdaten von einer CSV-Datei
    und erstellt eine Liste mit mit Ausbildern vom Datentyp Ausbilder

    Args:
        csv_file (_type_): Liste mit Azubis, die eingelesen werden soll

    Returns:
        list: Liste mit Ausbildern
    """
    # codec für Linux und Windows herausfinden
    codec = __get_codec(csv_file)

    ausbilder_liste = []

    try:
        with open(csv_file, encoding=codec) as csvdatei:
            for row in csv_DictReader(csvdatei, delimiter=";"):
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

    except Exception as e:
        print("_import_ausbilder_from_csv", e)
        return False
