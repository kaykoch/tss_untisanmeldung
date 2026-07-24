# ------------------------------------------------------------------------------
# Überprüft durch Claude 4
# ------------------------------------------------------------------------------

import logging
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from src.extensions import state
from src.models import Ausbilder, Azubis, add_new_entries, delete_all, get_existing_keys


logger = logging.getLogger(__name__)


def get_klassen_list() -> list[str]:
    """liefert alle Klassen mit Azubis

    Returns:
        list[str]: Liste mit Namen der Klassen
    """
    try:
        stmt = state.db.select(Azubis.klasse).distinct().order_by(Azubis.klasse.asc())
        return list(state.db.session.execute(stmt).scalars().all())
    except SQLAlchemyError as e:
        logger.error("DB-Fehler in get_klassen_list: %s", e)
        return []


def get_azubi_list(klasse_name: str = "all") -> list[Azubis]:
    """Gibt Azubi-Objekte sortiert zurück (für Templates / Anwendungscode)

    Args:
        klasse_name (str, optional): Name der Klasse. Defaults to "all".

    Returns:
        list[Azubis]: Liste mit Azubis
    """
    try:
        stmt = state.db.select(Azubis)

        if klasse_name and klasse_name != "all":
            stmt = stmt.where(Azubis.klasse == klasse_name)

        stmt = stmt.order_by(
            Azubis.klasse.asc(),
            Azubis.schueler_familienname.asc(),
            Azubis.schueler_rufname.asc(),
        )

        return state.db.session.execute(stmt).scalars().all()

    except SQLAlchemyError as e:
        logger.error("DB-Fehler in get_azubi_list: %s", e)
        return []
    except Exception as e:
        logger.error("Fehler in get_azubi_list: %s", e)
        return []


def get_azubi_list_for_csv(klasse_name: str = "all") -> list[dict[str, Any]]:
    """Gibt Azubis einer Klasse (oder alle) als Liste von Dicts zurück (CSV-geeignet).
    Liefert nur die ausgewählten Spalten (inkl. Ausbilder-Felder via OUTER JOIN).

    Args:
        klasse_name (str, optional): Name der Klasse. Defaults to "all".

    Returns:
        list[dict[str, Any]]:  Liste mit Dictionaries der Schüler
    """
    try:
        stmt = (
            state.db.select(
                Azubis.schueler_stamm_id.label("schueler_stamm_id"),
                Azubis.schueler_untis_id.label("schueler_untis_id"),
                Azubis.schueler_familienname.label("schueler_familienname"),
                Azubis.schueler_rufname.label("schueler_rufname"),
                Azubis.schueler_geburtsdatum.label("schueler_geburtsdatum"),
                Azubis.klasse.label("klasse"),
                Ausbilder.ausbilder_email.label("ausbilder_email"),
                Ausbilder.ausbilder_name.label("ausbilder_name"),
                Ausbilder.ausbilder_vorname.label("ausbilder_vorname"),
            )
            .select_from(Azubis)
            .outerjoin(Ausbilder, Azubis.ausbilder_email == Ausbilder.ausbilder_email)
        )

        if klasse_name != "all":
            stmt = stmt.where(Azubis.klasse == klasse_name)

        stmt = stmt.order_by(
            Azubis.klasse.asc(),
            Azubis.schueler_familienname.asc(),
            Azubis.schueler_rufname.asc(),
        )

        rows = state.db.session.execute(stmt).mappings().all()  # stabile Mapping-Objekte
        return [dict(r) for r in rows]

    except SQLAlchemyError as e:
        logger.error("DB-Fehler in get_azubi_list_for_csv: %s", e)
        return []
    except Exception as e:
        logger.error("Fehler in get_azubi_list_for_csv: %s", e)
        return []


def update_azubis_safe(liste: list[Azubis], delete_existing: bool = False) -> tuple[str, str]:
    """Fügt neue Azubis in die DB ein, ohne bestehende Einträge zu überschreiben.

    Args:
        liste:           Liste von Azubis-Objekten.
        delete_existing: Bei True werden alle bestehenden Azubis vorher gelöscht.

    Returns:
        Tuple (Meldung, Kategorie) – Kategorie ist "success" oder "error".
    """
    try:
        if delete_existing:
            delete_all(Azubis)

        # vorhandene Werte des primarykeys "schueler_stamm_id" als Set lesen
        existing = get_existing_keys(Azubis, Azubis.schueler_stamm_id)

        # Fügt neue Werte anhand des Primarykeys in "Azubis" ein ohne vorhandene zu überschreiben
        answer, category = add_new_entries(liste, "schueler_stamm_id", existing, "Azubis")

        return answer, category

    except Exception as e:
        state.db.session.rollback()
        logger.error("Fehler in update_azubis_safe: %s", e)
        return ("Fehler beim Einfügen der Azubis.", "error")


def get_klassen_choices() -> list[tuple[str, str]]:
    """Befüllt die Klassen-Choices des Formulars dynamisch aus der Datenbank.

    Returns:
        list[tuple[str, str]]: Choices-Liste mit Platzhalter und allen Klassen
    """
    klassen = get_klassen_list()  # gibt [] zurück bei Fehler
    return [("", "Bitte wählen..."), ("all", "Alle Klassen")] + [(k, k) for k in klassen]


def get_schueler_by_ids(ids: list[str]) -> list[Azubis]:
    """Lädt alle Azubis, deren untis_id in der übergebenen Liste enthalten ist.

    Args:
        ids (list[str]): Liste mit Untis_Ids

    Returns:
        list[Azubis]: Liste mit Azubis
    """
    try:
        stmt = state.db.select(Azubis).where(Azubis.schueler_untis_id.in_(ids))
        return list(state.db.session.execute(stmt).scalars())
    except SQLAlchemyError as e:
        logger.error("DB-Fehler in get_schueler_by_ids: %s", e)
        return []


def assign_schueler(schueler_liste: list[Azubis], ausbilder_email: str) -> None:
    """Weist alle Schüler dem Ausbilder zu

    Args:
        schueler_liste (list[Azubis]): Liste mit Azubis, die zugeordnet werden soll
        ausbilder_email (str): Emailadresse des Ausbilders
    """
    try:
        for schueler in schueler_liste:
            schueler.ausbilder_email = ausbilder_email
        state.db.session.commit()
    except SQLAlchemyError as e:
        state.db.session.rollback()
        logger.error("DB-Fehler in assign_schueler: %s", e)
        raise
