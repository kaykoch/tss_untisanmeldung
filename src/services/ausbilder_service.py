from datetime import datetime, timedelta
import logging
from typing import Any

from flask import flash
from sqlalchemy import delete, false, select
from sqlalchemy.exc import SQLAlchemyError

from src.extensions import db, state
from src.forms import AnmeldungForm
from src.models import Ausbilder, Azubis, add_new_entries, delete_all, get_existing_keys


logger = logging.getLogger(__name__)
DEFAULT_TIMETOWAIT = 120


def create_ausbilder(form: AnmeldungForm) -> Ausbilder:
    """Erstellt einen neuen Ausbilder aus den Formulardaten und fügt ihn der Session hinzu."""
    ausbilder = Ausbilder(
        ausbilder_email=form.ausbilder_email.data,
        ausbilder_name=form.ausbilder_name.data,
        ausbilder_vorname=form.ausbilder_vorname.data,
        ausbilder_betrieb=form.ausbilder_betrieb.data,
        bestaetigt=False,
    )
    state.db.session.add(ausbilder)
    return ausbilder


def get_ausbilder_by_email(email: str) -> Ausbilder | None:
    """Lädt einen Ausbilder anhand seiner E-Mail-Adresse aus der Datenbank.

    Verwendet von: route_ausbilderanzeige
    """
    stmt = select(Ausbilder).where(Ausbilder.ausbilder_email == email)
    return state.db.session.execute(stmt).scalar_one_or_none()


def delete_ausbilder(ausbilder: Ausbilder) -> None:
    """Löscht einen Ausbilder samt aller Verknüpfungen aus der Datenbank.

    Gibt Flash-Feedback bei Erfolg und Fehler.

    Verwendet von: route_ausbilderanzeige
    """
    try:
        state.db.session.delete(ausbilder)
        state.db.session.commit()
        flash(
            f"{ausbilder.ausbilder_email} und alle Verknüpfungen zu Azubis wurden gelöscht.",
            "success",
        )
    except SQLAlchemyError:
        state.db.session.rollback()
        logger.error("DB-Fehler beim Löschen von Ausbilder %s", ausbilder.ausbilder_email)
        flash("Datenbankfehler beim Löschen.", "error")


def delete_unconfirmed_ausbilder(timetowait: int = DEFAULT_TIMETOWAIT) -> None:
    """Löscht alle Ausbilder, die seit `timetowait` Minuten unbestätigt in der DB sind."""
    zeitlimit = datetime.now() - timedelta(minutes=timetowait)
    stmt = delete(Ausbilder).where(
        Ausbilder.created_at < zeitlimit,
        Ausbilder.bestaetigt == false(),
    )
    db.session.execute(stmt)
    db.session.commit()


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

        existing = get_existing_keys(Ausbilder, Ausbilder.ausbilder_email)
        return add_new_entries(liste, "ausbilder_email", existing, "Ausbilder")

    except Exception as e:
        state.db.session.rollback()
        logger.error("Fehler in update_ausbilder_safe: %s", e)
        return ("Fehler beim Einfügen der Ausbilder.", "error")


def get_ausbilder_by_token(token: str) -> Ausbilder | None:
    """Lädt einen Ausbilder anhand seines Tokens aus der DB."""
    stmt = state.db.select(Ausbilder).where(Ausbilder.token == token)
    return state.db.session.execute(stmt).scalar_one_or_none()


def get_ausbilder_list() -> list[dict[str, Any]]:
    """Gibt alle Ausbilder als Liste von Dictionaries zurück."""
    try:
        stmt = db.select(
            Ausbilder.ausbilder_email,
            Ausbilder.ausbilder_name,
            Ausbilder.ausbilder_vorname,
            Ausbilder.ausbilder_betrieb,
            Ausbilder.bestaetigt,
            Ausbilder.token,
            Ausbilder.created_at,
        )
        return [dict(row._mapping) for row in db.session.execute(stmt)]

    except SQLAlchemyError as e:
        logger.error("DB-Fehler in _get_ausbilder_list: %s", e)
        return []
    except Exception as e:
        logger.error("Fehler in _get_ausbilder_list: %s", e)
        return []


def get_ausbilder_by_klasse(klasse: str) -> None:
    """Sendet Untis-Infomails an alle Ausbilder einer bestimmten Klasse.

    Verwendet von: route_azubianzeige
    """
    stmt = (
        state.db.select(Ausbilder)
        .join(Azubis, Ausbilder.ausbilder_email == Azubis.ausbilder_email)
        .where(Azubis.klasse == klasse)
        .distinct()
    )
    return state.db.session.execute(stmt).scalars().all()
