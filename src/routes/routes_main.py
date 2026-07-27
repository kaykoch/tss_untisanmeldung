# ------------------------------------------------------------------------------
# Überprüft durch Claude 4
# ------------------------------------------------------------------------------

import logging
from typing import Any

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from markupsafe import Markup, escape
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
@main_bp.route("/old")
def willkommen():
    """Temporäre Seite., weil sich die Domain geändert hatte und eine Weiterleitung auf /old gibt"""
    token = request.args.get("token")
    if token:
        target = url_for("main.index", token=token, _external=True)
    else:
        target = url_for("main.index", _external=True)

    link_html = f'<a href="{escape(target)}" rel="noopener noreferrer">{escape(target)}</a>'
    info = Markup(
        "<p>Wir sind umgezogen.</p>"
        f"<p>Unsere neue Seite lautet: {link_html}</p>"
        "<p>Bitte rufen Sie in Zukunft direkt diesen Link auf, um neue Auszubildende zu registrieren.</p>"
    )
    flash(info, "warning")
    return render_template("oldside.html")


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

    info = Markup(state.infos.content.index)
    flash(info, "success")

    return render_template(_TEMPLATEINDEX, form=form, title=_TITLE_INDEX)


@main_bp.route("/bestaetigung.html", methods=["GET", "POST"])
@state.limiter.limit("3 per minute")
@requires_auth(_ALLOWED_ROLES_TSS, allow_token_bypass=True)
def route_bestaetigung() -> ResponseReturnValue:
    """Bestätigungsseite: Speichert Ausbilder-Anmeldung und Schüler-Zuordnung."""
    print(1)
    form = AnmeldungForm()

    if not form.validate_on_submit():
        return _render_bestaetigung(form)
    print(2)
    ausbilder_email = form.ausbilder_email.data
    if not ausbilder_email:
        flash("E-Mail-Adresse des Ausbilders fehlt.", "warning")
        return _render_bestaetigung(form)
    print(3)
    neue_schueler_ids = _parse_schueler_ids()
    print(4)
    try:
        # Ist der Ausbilder bereits vorhanden, oder neu?
        ausbilder = get_ausbilder_by_email(ausbilder_email)
        neu_angelegt = ausbilder is None

        neue_schueler: list[Azubis] = []
        liste_fehler: list[str] = []

        if neue_schueler_ids:
            # Gibt es Schüler zu diesen IDs
            neue_schueler = get_schueler_by_ids(neue_schueler_ids)
            liste_fehler = get_fehlende_ids(neue_schueler_ids, neue_schueler)

            if neue_schueler:
                print(5)
                # Es gibt Schüler mit den IDs
                if neu_angelegt:
                    # Der Ausbilder muss neu angelegt werden
                    ausbilder = create_ausbilder(form)
                # Die Schüler werden dem Ausbilder zugeordnet
                assign_schueler(neue_schueler, ausbilder_email)
                state.db.session.commit()

                if neu_angelegt:
                    answer, category = send_mail_to_ausbilder(ausbilder)
                    flash(answer, category)
            print(6)
            answer, category = send_mail_to_ausbilder(ausbilder)
        _flash_zuordnung_feedback(neue_schueler_ids, liste_fehler)

        return _render_bestaetigung(
            form,
            liste_erfolgreich=neue_schueler,
            liste_fehler=liste_fehler,
            ausbilder=ausbilder,  # Wenn None -> wird im Template abgesichert
        )

    except SQLAlchemyError as e:
        state.db.session.rollback()
        logger.exception("DB-Fehler in route_bestaetigung: %s", e)
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
        infos = state.infos.content.azubimitausbilder
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


@main_bp.route("/api/zugeordnete_schueler/<string:klasse_name>")
@requires_auth(_ALLOWED_ROLES_TSS)
def zugeordnete_schueler(klasse_name: str) -> ResponseReturnValue:
    """API-Endpunkt: Gibt alle Azubis einer Klasse als JSON zurück."""
    try:
        data: list[Any] = get_azubi_list_for_csv(klasse_name)
        return jsonify(data)
    except Exception as e:
        logger.error("Fehler in zugeordnete_schueler: %s", e)
        return jsonify([])


@main_bp.route("/impressum.html", methods=["GET"])
def route_impressum() -> ResponseReturnValue:
    """Zeigt die Impressumseite an"""
    return render_template("impressum.html")
