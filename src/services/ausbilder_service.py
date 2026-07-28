# ------------------------------------------------------------------------------
# Überprüft durch Claude 4
# ------------------------------------------------------------------------------

from datetime import datetime, timedelta
import logging
from typing import Any

from sqlalchemy import delete, false, select
from sqlalchemy.exc import SQLAlchemyError

from src.extensions import state
from src.forms import AnmeldungForm
from src.models import Ausbilder, Azubis, add_new_entries, delete_all, get_existing_keys


logger = logging.getLogger(__name__)
DEFAULT_TIMETOWAIT = 120


def create_ausbilder(form: AnmeldungForm) -> Ausbilder:
    """ "Erstellt einen neuen Ausbilder aus den Formulardaten und fügt ihn der Session hinzu.

    Args:
        form (AnmeldungForm): Flask-Form mit Daten für Ausbilder

    Returns:
        Ausbilder: Ausbilder
    """
    ausbilder = Ausbilder(
        ausbilder_email=form.ausbilder_email.data,
        ausbilder_name=form.ausbilder_name.data,
        ausbilder_vorname=form.ausbilder_vorname.data,
        ausbilder_betrieb=form.ausbilder_betrieb.data,
        bestaetigt=False,
    )
    state.db.session.add(ausbilder)
    return ausbilder


def get_ausbilder_by_token(token: str) -> Ausbilder | None:
    """Liefert einen Ausbilder anhand seines Tokens aus der DB.

    Args:
        token (str): Token des Ausbilders

    Returns:
        Ausbilder | None: Ausbilder, wenn es ihn gibt. Sonst None
    """

    stmt = state.db.select(Ausbilder).where(Ausbilder.token == token)
    return state.db.session.execute(stmt).scalar_one_or_none()


def get_ausbilder_by_email(email: str) -> Ausbilder | None:
    """Liefert einen Ausbilder anhand seiner Mailadresse aus der DB

    Args:
        email (str): Mailadresse des Ausbilders

    Returns:
        Ausbilder | None: Ausbilder, wenn es ihn gibt. Sonst None

    Verwendet von: route_ausbilderanzeige
    """
    stmt = select(Ausbilder).where(Ausbilder.ausbilder_email == email)
    return state.db.session.execute(stmt).scalar_one_or_none()


def delete_ausbilder(ausbilder: Ausbilder) -> tuple:
    """Löscht einen Ausbilder samt aller Verknüpfungen aus der Datenbank.

    Args:
        ausbilder (Ausbilder): Ausbilder der gelöscht werden soll

    Verwendet von: route_ausbilderanzeige
    """

    try:
        mail = ausbilder.ausbilder_email
        betrieb = ausbilder.ausbilder_betrieb
        state.db.session.delete(ausbilder)
        state.db.session.commit()
        return (f"Der Betrieb <b>{betrieb}</b> ({mail}) und alle Verknüpfungen zu Azubis wurden gelöscht.", "success")

    except SQLAlchemyError:
        state.db.session.rollback()
        logger.error("DB-Fehler beim Löschen von Ausbilder %s", mail)
        return (f" DB-Fehler beim Löschen von Ausbilder:({mail})", "error")


def delete_unconfirmed_ausbilder(timetowait: int = DEFAULT_TIMETOWAIT) -> None:
    """Löscht alle Ausbilder, die seit timetowait Minuten unbestätigt in der DB sind.


    Args:
        timetowait (int, optional): Zeit in Minuten, die mindestens seit Anmeldung. Defaults to DEFAULT_TIMETOWAIT.
    """
    zeitlimit = datetime.now() - timedelta(minutes=timetowait)
    stmt = delete(Ausbilder).where(
        Ausbilder.created_at < zeitlimit,
        Ausbilder.bestaetigt == false(),
    )
    try:
        state.db.session.execute(stmt)
        state.db.session.commit()
    except SQLAlchemyError:
        state.db.session.rollback()
        logger.error("DB-Fehler in delete_unconfirmed_ausbilder")


def update_ausbilder_safe(liste: list, delete_existing: bool = False) -> tuple[str, str]:
    """Fügt neue Ausbilder in die DB ein, ohne bestehende Einträge zu überschreiben.

    Args:
        liste:           Liste von Ausbilder-Objekten.
        delete_existing: Bei True werden alle bestehenden Ausbilder vorher gelöscht.

    Returns:
        Tuple (Meldung, Kategorie) – Kategorie ist "success" oder "error".
    """
    try:
        if delete_existing:
            delete_all(Ausbilder)

        # vorhandene Werte des primarykeys "ausbilder_email" als Set lesen
        existing = get_existing_keys(Ausbilder, "ausbilder_email")

        # Fügt neue Werte anhand des Primarykeys in "Ausbilder" ein ohne vorhandene zu überschreiben
        answer, category = add_new_entries(liste, "ausbilder_email", existing, "Ausbilder")
        return answer, category

    except Exception as e:
        state.db.session.rollback()
        logger.error("Fehler in update_ausbilder_safe: %s", e)
        return ("Fehler beim Einfügen der Ausbilder.", "error")


def get_ausbilder_list() -> list[Ausbilder]:
    """Gibt alle Ausbilder-Objekte sortiert zurück (für Template-Anzeige)


    Returns:
        list[Ausbilder]: Liste mit Ausbilder
    """
    try:
        stmt = state.db.select(Ausbilder).order_by(Ausbilder.ausbilder_betrieb.asc())
        return state.db.session.execute(stmt).scalars().all()
    except SQLAlchemyError as e:
        logger.error("DB-Fehler in get_ausbilder_list: %s", e)
        return []


def get_ausbilder_list_for_csv() -> list[dict[str, Any]]:
    """Gibt alle Ausbilder als Liste von dicts zurück (nur die relevanten CSV-Felder).

    Returns:
        list[dict[str, Any]]: Liste mit Dictionaries aller Ausbilder
    """

    try:
        stmt = state.db.select(
            Ausbilder.ausbilder_email,
            Ausbilder.ausbilder_name,
            Ausbilder.ausbilder_vorname,
            Ausbilder.ausbilder_betrieb,
            Ausbilder.bestaetigt,
            Ausbilder.token,
            Ausbilder.created_at,
        ).order_by(Ausbilder.ausbilder_betrieb.asc())

        rows = state.db.session.execute(stmt).mappings().all()  # -> list[Mapping]
        return [dict(r) for r in rows]

    except SQLAlchemyError as e:
        logger.error("DB-Fehler in get_ausbilder_list_for_csv: %s", e)
        return []
    except Exception as e:
        logger.error("Fehler in get_ausbilder_list_for_csv: %s", e)
        return []


def get_ausbilder_list_by_klasse(klasse: str) -> list[Ausbilder]:
    """liefert eine Liste mit Ausbildern einer Klasse


    Args:
        klasse (str): Klassenname

    Returns:
        list[Ausbilder]: List mit Ausbildern
    """
    try:
        stmt = (
            state.db.select(Ausbilder)
            .join(Azubis, Ausbilder.ausbilder_email == Azubis.ausbilder_email)
            .where(Azubis.klasse == klasse)
            .distinct()
        )
        return state.db.session.execute(stmt).scalars().all()
    except SQLAlchemyError as e:
        logger.error("DB-Fehler in get_ausbilder_list_by_klasse: %s", e)
        return []


def confirm_ausbilder(ausbilder: Ausbilder) -> None:
    """Setzt den Flag für Bestätigt in der DB für einen Ausbilder

    Args:
        ausbilder (Ausbilder): Ausbilder, der sich bestätigt hat
    """
    if not ausbilder.bestaetigt:
        try:
            ausbilder.bestaetigt = True
            state.db.session.commit()
        except SQLAlchemyError:
            state.db.session.rollback()
            logger.error("DB-Fehler in confirm_ausbilder: %s", ausbilder.ausbilder_email)
            raise
