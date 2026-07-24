# ------------------------------------------------------------------------------
#     USER-BEREICH
# ------------------------------------------------------------------------------

import logging
from typing import Any

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from markupsafe import Markup
from sqlalchemy.exc import SQLAlchemyError

from src.extensions import state
from src.forms import AnmeldungForm
from src.models import Ausbilder, Azubis
from src.services.ausbilder_service import (
    confirm_ausbilder,
    create_ausbilder,
    delete_unconfirmed_ausbilder,
    get_ausbilder_by_email,
    get_ausbilder_by_token,
)
from src.services.azubi_service import assign_schueler, get_azubi_list_for_csv, get_schueler_by_ids
from src.services.mail_service import send_mail_to_ausbilder
from src.utils.auth import requires_auth
from src.utils.helpers import get_fehlende_ids, token_is_valid


# ------------------------------------------------------------------------------
# Konstanten
# ------------------------------------------------------------------------------

_TITLE_INDEX = "Anmeldeseite für Ausbilderbetriebe zur Nutzung von WebUntis"
_TITLE_BESTAETIGUNG = "Anmeldung Ausbilderbetriebe WebUntis"
_TITLE_AZUBIS = "Liste der zugeordneten Azubis in WebUntis"

_TEMPLATEINDEX = "index.html"
_TEMPLATEBESTAETIGUNG = "bestaetigung.html"
_TEMPLATEAZUBIS = "azubismitausbilder.html"

_ALLOWED_ROLES_TSS: frozenset[str] = frozenset({"admin", "tss"})

# ------------------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------------------

logger = logging.getLogger(__name__)
main_bp = Blueprint("main", __name__)

# ------------------------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------------------------


def _render_bestaetigung(form: AnmeldungForm, **kwargs) -> str:
    """Rendert das Bestätigungs-Template mit Standardwerten."""
    return render_template(_TEMPLATEBESTAETIGUNG, form=form, title=_TITLE_BESTAETIGUNG, **kwargs)


def _parse_schueler_ids() -> list[str]:
    """Liest und bereinigt die Schüler-IDs aus dem Request-Formular."""
    return [s.strip() for s in request.form.getlist("schueler_untis_id[]") if s and s.strip()]


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


@main_bp.route("/", methods=["GET", "POST"])
@requires_auth(_ALLOWED_ROLES_TSS, allow_token_bypass=True)
def index() -> ResponseReturnValue:
    """Startseite:
    - Cleanup unbestätigter Ausbilder
    - Optionales Prefill des Formulars via Token
    - Anzeige von Infotexten und Anmeldeformular
    """

    delete_unconfirmed_ausbilder(state.app.config["TIMETOWAIT"])

    token: str | None = request.args.get("token")
    ausbilder: Ausbilder | None = get_ausbilder_by_token(token) if token else None
    form = AnmeldungForm(obj=ausbilder) if ausbilder else AnmeldungForm()

    if form.validate_on_submit():
        return redirect(url_for("main.route_bestaetigung"))

    info = Markup(state.get_text("infos", "index"))

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


@main_bp.route("/bestaetigung.html", methods=["GET", "POST"])
@state.limiter.limit("3 per minute")
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
        ausbilder = get_ausbilder_by_email(ausbilder_email)
        neu_angelegt = ausbilder is None

        if neu_angelegt:
            ausbilder = create_ausbilder(form)

        neue_schueler: list[Azubis] = []
        liste_fehler: list[str] = []

        if neue_schueler_ids:
            neue_schueler = get_schueler_by_ids(neue_schueler_ids)
            liste_fehler = get_fehlende_ids(neue_schueler_ids, neue_schueler)
            assign_schueler(neue_schueler, ausbilder_email)

        if neue_schueler:
            state.db.session.commit()
            if neu_angelegt:
                answer, category = send_mail_to_ausbilder(ausbilder)
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


@main_bp.route("/azubismitausbilder.html", methods=["GET", "POST"])
def route_azubismitausbilder() -> ResponseReturnValue:
    """Zeigt alle Azubis eines Ausbilders an.
    Der Ausbilder wird über ein Token identifiziert.
    """
    token: str | None = request.args.get("token")

    if not token or not token_is_valid(token):
        flash("Kein Token angegeben oder Token ist ungültig.", "error")
        return render_template(_TEMPLATEAZUBIS, title=_TITLE_AZUBIS, ausbilder=None)

    try:
        ausbilder = get_ausbilder_by_token(token)

        if ausbilder is None:
            flash("Diesen Ausbilder gibt es nicht oder das Token ist ungültig.", "error")
            return render_template(_TEMPLATEAZUBIS, title=_TITLE_AZUBIS, ausbilder=None)

        if not ausbilder.bestaetigt:
            confirm_ausbilder(ausbilder)
            flash("Ihre Anmeldung wurde bestätigt", "warning")

        azubi_liste: list[Azubis] = list(ausbilder.accounts)
        infos = state.get_text("infos", "azubimitausbilder")
        flash(Markup(infos), "success")

        return render_template(
            _TEMPLATEAZUBIS,
            title=_TITLE_AZUBIS,
            azubi_liste=azubi_liste,
            ausbilder=ausbilder,
        )

    except Exception as e:
        state.db.session.rollback()
        logger.error("Fehler in route_azubismitausbilder: %s", e)
        abort(500)


@main_bp.route("/api/zugeordete_schueler/<string:klasse_name>")
def zugeordete_schueler(klasse_name: str) -> ResponseReturnValue:
    """API-Endpunkt: Gibt alle Azubis einer Klasse als JSON zurück."""
    try:
        data: list[Any] = get_azubi_list_for_csv(klasse_name)
        return jsonify(data)
    except Exception as e:
        logger.error("Fehler in zugeordete_schueler: %s", e)
        return jsonify([])


@main_bp.route("/impressum.html", methods=["GET"])
def route_impressum() -> ResponseReturnValue:
    return render_template("impressum.html")
