import logging
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from src.extensions import state
from src.forms import AzubiAuswahlForm
from src.models import Ausbilder, Azubis, add_new_entries, delete_all, get_existing_keys


logger = logging.getLogger(__name__)


def get_azubi_list(klasse_name: str) -> list[dict[str, Any]]:
    """Gibt Azubis einer Klasse (oder alle) als Liste von Dictionaries zurück.

    Args:
        klasse_name: Klassenbezeichnung oder "all" für alle Klassen.

    Returns:
        Liste von Dictionaries mit Schüler- und Ausbilderfeldern.
    """
    try:
        stmt = (
            state.db.select(
                Azubis.schueler_stamm_id,
                Azubis.schueler_untis_id,
                Azubis.schueler_familienname,
                Azubis.schueler_rufname,
                Azubis.schueler_geburtsdatum,
                Azubis.klasse,
                Ausbilder.ausbilder_email,
                Ausbilder.ausbilder_name,
                Ausbilder.ausbilder_vorname,
            )
            .select_from(Azubis)
            .outerjoin(Ausbilder, Azubis.ausbilder_email == Ausbilder.ausbilder_email)
        )

        if klasse_name != "all":
            stmt = stmt.where(Azubis.klasse == klasse_name)

        stmt = stmt.order_by(Azubis.klasse.asc(), Azubis.schueler_familienname.asc())

        return [dict(row._mapping) for row in state.db.session.execute(stmt).all()]

    except SQLAlchemyError as e:
        logger.error("DB-Fehler in _get_azubi_list: %s", e)
        return []
    except Exception as e:
        logger.error("Fehler in _get_azubi_list: %s", e)
        return []


def update_azubis_safe(liste: list, delete_existing: bool = False) -> tuple[str, str]:
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

        existing = get_existing_keys(Azubis, Azubis.schueler_stamm_id)
        return add_new_entries(liste, "schueler_stamm_id", existing, "Azubis")

    except Exception as e:
        state.db.session.rollback()
        logger.error("Fehler in _update_azubis_safe: %s", e)
        return ("Fehler beim Einfügen der Azubis.", "error")


def build_klassen_choices(form: AzubiAuswahlForm) -> None:
    """Befüllt die Klassen-Choices des Formulars dynamisch aus der Datenbank.

    Verwendet von: route_azubianzeige
    """
    klassen = state.db.session.query(Azubis.klasse).distinct().order_by(Azubis.klasse.asc()).all()
    form.klassen.choices = [("", "Bitte wählen..."), ("all", "Alle Klassen")] + [
        (k.klasse, k.klasse) for k in klassen if k.klasse
    ]


def get_schueler_by_ids(ids: list[str]) -> list[Azubis]:
    """Lädt alle Azubis, deren untis_id in der übergebenen Liste enthalten ist."""
    stmt = state.db.select(Azubis).where(Azubis.schueler_untis_id.in_(ids))
    return list(state.db.session.execute(stmt).scalars())


def assign_schueler(schueler_liste: list[Azubis], ausbilder_email: str) -> None:
    """Weist alle Schüler dem Ausbilder zu."""
    for schueler in schueler_liste:
        schueler.ausbilder_email = ausbilder_email
