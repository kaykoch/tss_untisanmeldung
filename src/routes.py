# ------------------------------------------------------------------------------
#     USER-BEREICH
# ------------------------------------------------------------------------------

import logging
from typing import Any

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from markupsafe import Markup
from sqlalchemy.exc import SQLAlchemyError

from src.extensions import state
from src.forms import AnmeldungForm
from src.helpies import _get_error_page, _requires_auth, _send_mail_to_ausbilder, _token_is_valid
from src.models import (
    Ausbilder,
    Azubis,
    _delete_unconfirmed_ausbilder,
    _get_ausbilder_by_token,
    _get_azubi_list,
)


# ------------------------------------------------------------------------------
# Konstanten
# ------------------------------------------------------------------------------

_TITLE_INDEX = "Anmeldeseite für Ausbilderbetriebe zur Nutzung von WebUntis"
_TITLE_BESTAETIGUNG = "Anmeldung Ausbilderbetriebe WebUntis"
_TITLE_AZUBIS = "Liste der zugeordneten Azubis in WebUntis"

_TEMPLATEINDEX = "index.html"
_TEMPLATEBESTAETIGUNG = "bestaetigung.html"
_TEMPLATEAZUBIS = "azubismitausbilder.html"

_ALLOWED_ROLES_TSS = ["admin", "tss"]

# ------------------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------------------

logger = logging.getLogger(__name__)
bp = Blueprint("main", __name__)

limiter = Limiter(
    get_remote_address,
    app=state.app,
    default_limits=["10 per minute"],
    storage_uri="memory://",
)

# ------------------------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------------------------


def _render_bestaetigung(form: AnmeldungForm, **kwargs) -> str:
    """Rendert das Bestätigungs-Template mit Standardwerten."""
    return render_template(_TEMPLATEBESTAETIGUNG, form=form, title=_TITLE_BESTAETIGUNG, **kwargs)


def _get_ausbilder_by_email(email: str) -> Ausbilder | None:
    """Lädt einen Ausbilder anhand seiner E-Mail aus der DB."""
    stmt = state.db.select(Ausbilder).where(Ausbilder.ausbilder_email == email)
    return state.db.session.execute(stmt).scalar_one_or_none()


def _create_ausbilder(form: AnmeldungForm) -> Ausbilder:
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


def _parse_schueler_ids() -> list[str]:
    """Liest und bereinigt die Schüler-IDs aus dem Request-Formular."""
    return [s.strip() for s in request.form.getlist("schueler_untis_id[]") if s and s.strip()]


def _load_schueler(ids: list[str]) -> list[Azubis]:
    """Lädt alle Azubis, deren untis_id in der übergebenen Liste enthalten ist."""
    stmt = state.db.select(Azubis).where(Azubis.schueler_untis_id.in_(ids))
    return list(state.db.session.execute(stmt).scalars())


def _assign_schueler(schueler_liste: list[Azubis], ausbilder_email: str) -> None:
    """Weist alle Schüler dem Ausbilder zu."""
    for schueler in schueler_liste:
        schueler.ausbilder_email = ausbilder_email


def _get_fehlende_ids(angefragt: list[str], gefunden: list[Azubis]) -> list[str]:
    """Gibt die IDs zurück, die nicht in der DB gefunden wurden."""
    gefundene_ids = {a.schueler_untis_id for a in gefunden}
    return [sid for sid in angefragt if sid not in gefundene_ids]


def _flash_zuordnung_feedback(neue_schueler_ids: list[str], liste_fehler: list[str]) -> None:
    """Gibt dem Nutzer Feedback über den Erfolg der Schüler-Zuordnung."""
    if not neue_schueler_ids:
        flash("Es wurden keine Schüler-IDs übermittelt.", "info")
    elif not liste_fehler:
        flash("Alle Schüler wurden erfolgreich zugeordnet.", "success")
    elif len(liste_fehler) < len(neue_schueler_ids):
        flash("Einige Schüler konnten nicht zugeordnet werden.", "warning")
    else:
        flash("Keine der angegebenen Schüler-IDs konnte gefunden werden.", "warning")


# ------------------------------------------------------------------------------
# Routen
# ------------------------------------------------------------------------------


@bp.route("/", methods=["GET", "POST"])
@_requires_auth(_ALLOWED_ROLES_TSS, allow_token_bypass=True)
def index() -> ResponseReturnValue:
    """Startseite:
    - Cleanup unbestätigter Ausbilder
    - Optionales Prefill des Formulars via Token
    - Anzeige von Infotexten und Anmeldeformular
    """
    _delete_unconfirmed_ausbilder(state.app.config["TIMETOWAIT"])

    token: str | None = request.args.get("token")
    ausbilder: Ausbilder | None = _get_ausbilder_by_token(token) if token else None
    form = AnmeldungForm(obj=ausbilder) if ausbilder else AnmeldungForm()

    if form.validate_on_submit():
        return redirect(url_for("main.route_bestaetigung"))

    info = Markup(f"{state.infotexte['index_1']}{state.infotexte['index_2']}")

    flash(info, "success")
    if token is not None:
        info = Markup(
            "Sie sind auf unsere neue Website [https://untis.tss-bitburg.de] umgeleitet worden. "
            f"Bitte rufen Sie in Zukunft direkt diesen <a href='https://untis.tss-bitburg.de/?token={token}'>Link</a> "
            "auf, um neue Auszubildende zu registrieren."
            "<p>Diese Information wird vorläufig auch angezeigt, wenn Sie bereits die neue Adresse aufgerufen haben</p>"
        )
        flash(info, "warning")

    return render_template(_TEMPLATEINDEX, form=form, title=_TITLE_INDEX)


@bp.route("/bestaetigung.html", methods=["GET", "POST"])
@limiter.limit("3 per minute")
def route_bestaetigung() -> ResponseReturnValue:
    """Bestätigungsseite: Verarbeitet Ausbilder-Anmeldung und Schüler-Zuordnung."""
    form = AnmeldungForm()

    if not form.validate_on_submit():
        return _render_bestaetigung(form)

    ausbilder_email = form.ausbilder_email.data
    if not ausbilder_email:
        flash("E-Mail-Adresse des Ausbilders fehlt.", "warning")
        return _render_bestaetigung(form)

    neue_schueler_ids = _parse_schueler_ids()

    try:
        ausbilder = _get_ausbilder_by_email(ausbilder_email)
        neu_angelegt = ausbilder is None

        if neu_angelegt:
            ausbilder = _create_ausbilder(form)

        neue_schueler: list[Azubis] = []
        liste_fehler: list[str] = []

        if neue_schueler_ids:
            neue_schueler = _load_schueler(neue_schueler_ids)
            liste_fehler = _get_fehlende_ids(neue_schueler_ids, neue_schueler)
            _assign_schueler(neue_schueler, ausbilder_email)

        if neue_schueler:
            state.db.session.commit()
            if neu_angelegt:
                answer, category = _send_mail_to_ausbilder(ausbilder)
                flash(answer, category)

        _flash_zuordnung_feedback(neue_schueler_ids, liste_fehler)

        return _render_bestaetigung(
            form,
            liste_erfolgreich=neue_schueler,
            liste_fehler=liste_fehler,
            ausbilder=ausbilder,
        )

    except SQLAlchemyError as e:
        state.db.session.rollback()
        logger.error("DB-Fehler in route_bestaetigung: %s", e)
        flash("Ein Datenbankfehler ist aufgetreten.", "error")
        return _render_bestaetigung(form)


@bp.route("/azubismitausbilder.html", methods=["GET", "POST"])
def route_azubismitausbilder() -> ResponseReturnValue:
    """Zeigt alle Azubis eines Ausbilders an.
    Der Ausbilder wird über ein Token identifiziert.
    """
    token: str | None = request.args.get("token")

    if not token or not _token_is_valid(token):
        flash("Kein Token angegeben oder Token ist ungültig.", "error")
        return render_template(_TEMPLATEAZUBIS, title=_TITLE_AZUBIS, ausbilder=None)

    try:
        ausbilder = _get_ausbilder_by_token(token)

        if ausbilder is None:
            flash("Diesen Ausbilder gibt es nicht oder das Token ist ungültig.", "error")
            return render_template(_TEMPLATEAZUBIS, title=_TITLE_AZUBIS, ausbilder=None)

        if not ausbilder.bestaetigt:
            ausbilder.bestaetigt = True
            state.db.session.commit()
            flash("Ihre Anmeldung wurde bestätigt", "warning")

        azubi_liste: list[Azubis] = list(ausbilder.accounts)
        flash(Markup(state.infotexte["azubismitausbilder"]), "success")

        return render_template(
            _TEMPLATEAZUBIS,
            title=_TITLE_AZUBIS,
            azubi_liste=azubi_liste,
            ausbilder=ausbilder,
        )

    except SQLAlchemyError as e:
        state.db.session.rollback()
        logger.error("DB-Fehler in route_azubismitausbilder: %s", e)
        return _get_error_page()
    except Exception as e:
        logger.error("Fehler in route_azubismitausbilder: %s", e)
        return _get_error_page()


@bp.route("/api/zugeordete_schueler/<string:klasse_name>")
def zugeordete_schueler(klasse_name: str) -> ResponseReturnValue:
    """API-Endpunkt: Gibt alle Azubis einer Klasse als JSON zurück."""
    try:
        data: list[Any] = _get_azubi_list(klasse_name)
        return jsonify(data)
    except Exception as e:
        logger.error("Fehler in zugeordete_schueler: %s", e)
        return jsonify([])


@bp.route("/impressum.html", methods=["GET"])
def route_impressum() -> ResponseReturnValue:
    return render_template("impressum.html")
