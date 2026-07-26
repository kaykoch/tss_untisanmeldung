# ------------------------------------------------------------------------------
# Überprüft durch Claude 4
# ------------------------------------------------------------------------------

import logging

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask.typing import ResponseReturnValue
from markupsafe import Markup
from sqlalchemy.exc import SQLAlchemyError

from src.extensions import state
from src.forms import AusbilderAktionForm, AzubiAuswahlForm, ConfigForm, FilehandlingAktionForm
from src.models import (
    ConfigSetting,
)
from src.services.ausbilder_service import (
    delete_ausbilder,
    get_ausbilder_by_email,
    get_ausbilder_list,
    get_ausbilder_list_by_klasse,
    update_ausbilder_safe,
)
from src.services.azubi_service import get_klassen_choices, update_azubis_safe
from src.services.config_service import apply_config_form, load_config, load_defaults
from src.services.csv_service import (
    export_to_csv,
    import_ausbilder_from_bytesio,
    import_azubis_from_bytesio,
    merge_csv_to_bytesio,
)
from src.services.file_service import (
    delete_file_safe,
    get_files_from_upload,
    save_file,
    upload_file,
    uploaded_file_to_bytesio,
)
from src.services.mail_service import send_mail_to_ausbilder, send_mail_to_kontaktperson, send_untisinfo_to_ausbilder
from src.utils.auth import requires_auth
from src.utils.helpers import flash_all, flash_form_errors


# ------------------------------------------------------------------------------
# Konstanten
# ------------------------------------------------------------------------------

TITLE_ADMIN = "Administration - Ausbilderbetriebe WebUntis"
TITLE_CONFIG = "Einstellungen - Ausbilderbetriebe WebUntis"
TITLE_AUSBILDER = "Anzeige und Download der Ausbilderbetriebe"
TITLE_AZUBIS = "Anzeige und Download der Azubis"
TITLE_FILEHANDLING = "Dateimanager - Azubis WebUntis"

TEMPLATE_ADMIN = "admin/admin.html"
TEMPLATE_CONFIG = "admin/config.html"
TEMPLATE_AUSBILDER = "admin/ausbilderanzeige.html"
TEMPLATE_AZUBIANZEIGE = "admin/azubianzeige.html"
TEMPLATE_UPLOAD = "admin/upload.html"
TEMPLATE_FILEHANDLING = "admin/filehandling.html"

ALLOWED_UPLOAD_ACTIONS: frozenset[str] = frozenset({"ausbilder", "azubis", "info"})
ALLOWED_AUSBILDER_ACTIONS: frozenset[str] = frozenset({"add", "resend", "delete", "download", "show"})
ALLOWED_FILE_ACTIONS: frozenset[str] = frozenset(
    {"delete_single", "delete_all", "update_db", "reset_db", "upload_file"}
)

_PROTOTYPE_FILES = {"info": state.infofile, "ausbilder": state.prototypeausbilder, "azubis": state.prototypeazubi}
# ------------------------------------------------------------------------------
# Setup
# ------------------------------------------------------------------------------

logger = logging.getLogger(__name__)
admin_bp = Blueprint("admin", __name__)


# ------------------------------------------------------------------------------
# Hilfsfunktionen – allgemein (mehrere Routen)
# ------------------------------------------------------------------------------


def _send_csv_file(file_io, download_name: str) -> ResponseReturnValue:
    """Sendet eine CSV-Datei als Download.

    Verwendet von: route_ausbilderanzeige, route_azubianzeige
    """
    # Prüfen, ob file-like Objekt geschlossen ist
    if hasattr(file_io, "closed") and file_io.closed:
        logger.error("Attempt to send closed file-like object")
        abort(500)

    # Sicherstellen, dass wir am Anfang lesen
    if hasattr(file_io, "seek"):
        file_io.seek(0)

    return send_file(
        file_io,
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=download_name,
        conditional=False,
    )


# ------------------------------------------------------------------------------
# Hilfsfunktionen – route_filehandling
# ------------------------------------------------------------------------------


def _update_db_from_upload(reset: bool = False) -> None:
    """Fasst alle CSV-Dateien im Upload-Ordner zusammen und aktualisiert die Azubi-Datenbank.

    Args:
        reset (bool, optional): Löscht alle alten Einträge bei True. Defaults to False.

    Verwendet von: route_filehandling (Aktionen: update_db, reset_db)
    """
    bytesio = merge_csv_to_bytesio(state.uploadfolder)
    if not bytesio:
        flash("Fehler beim Zusammenfassen der einzelnen Dateien.", "error")
        return
    try:
        neue_azubis = import_azubis_from_bytesio(bytesio)
        answer, category = update_azubis_safe(neue_azubis, reset)
        flash(answer, category)
    except Exception:
        logger.exception("Allg. Fehler bei _update_db_from_upload")
        flash("Fehler beim Aktualisieren der Daten.", "error")


# ------------------------------------------------------------------------------
# Routen
# ------------------------------------------------------------------------------


@admin_bp.route("/", methods=["GET"])
@requires_auth("admin")
def route_admin() -> str:
    """Zeigt alle administrativen Aufgaben auf einer Übersichtsseite."""
    return render_template(TEMPLATE_ADMIN, title=TITLE_ADMIN)


@admin_bp.route("/config.html", methods=["GET", "POST"])
@requires_auth("admin")
def route_config() -> ResponseReturnValue:
    """Zeigt die Konfigurationsseite an und speichert Änderungen."""

    try:
        cfg = load_config()
        form = ConfigForm(obj=cfg)

        if form.validate_on_submit():
            if cfg is None:
                cfg = ConfigSetting()
                state.db.session.add(cfg)

            try:
                apply_config_form(form, cfg)
                state.db.session.commit()
                flash("Konfiguration erfolgreich gespeichert.", "success")
                load_defaults()

            except RuntimeError as exc:
                state.db.session.rollback()
                logger.exception("Konfigurationsfehler")
                flash(str(exc), "error")
                return render_template(TEMPLATE_CONFIG, title=TITLE_CONFIG, form=form), 400

            except SQLAlchemyError:
                state.db.session.rollback()
                logger.exception("DB-Fehler beim Speichern der Config")
                flash("Datenbankfehler beim Speichern der Konfiguration.", "error")
                return render_template(TEMPLATE_CONFIG, title=TITLE_CONFIG, form=form), 500

        elif request.method == "POST":
            logger.warning("Formular-Fehler in route_config: %s", form.errors)

        return render_template(TEMPLATE_CONFIG, title=TITLE_CONFIG, form=form)

    except Exception:
        logger.exception("Fehler in route_config: ")
        abort(500)


@admin_bp.route("/ausbilderanzeige.html", methods=["GET", "POST"])
@requires_auth("admin")
def route_ausbilderanzeige() -> ResponseReturnValue:
    """Zeigt alle Ausbilder an und erlaubt Aktionen (anzeigen, hinzufügen, Mail, löschen, Download)."""
    form = AusbilderAktionForm()

    try:
        if form.validate_on_submit() and form.action.data in ALLOWED_AUSBILDER_ACTIONS:
            action: str = form.action.data
            ausbilder = get_ausbilder_by_email(form.ausbilder_email.data)
            answer = None

            match action:
                case "show":
                    if ausbilder:
                        return redirect(url_for("main.route_azubismitausbilder", token=ausbilder.token))
                case "add":
                    if ausbilder:
                        return redirect(url_for("main.index", token=ausbilder.token))
                case "resend":
                    if ausbilder:
                        answer, category = send_mail_to_ausbilder(ausbilder)
                case "delete":
                    if ausbilder:
                        answer, category = delete_ausbilder(ausbilder)
                case "download":
                    try:
                        return _send_csv_file(export_to_csv("ausbilder"), "ausbilder.csv")
                    except Exception:
                        logger.exception("Fehler beim CSV-Export in route_ausbilderanzeige")
                        flash("Fehler beim Erstellen der CSV-Datei.", "error")
                        return redirect(url_for("admin.route_ausbilderanzeige"))
            if answer:
                flash(answer, category)
        else:
            if request.method == "GET":
                flash("Für weitere Informationen mit der Maus über die Kopfzeile fahren.", "success")

        ausbilder_liste = get_ausbilder_list()

        return render_template(
            TEMPLATE_AUSBILDER,
            title=TITLE_AUSBILDER,
            ausbilder_liste=ausbilder_liste,
            form=form,
        )

    except Exception:
        logger.exception("Fehler in route_ausbilderanzeige: ")
        abort(500)


@admin_bp.route("/azubianzeige.html", methods=["GET", "POST"])
@requires_auth("admin")
def route_azubianzeige() -> ResponseReturnValue:
    """Anzeige und Download der Azubis einer Klasse oder aller Klassen."""
    form = AzubiAuswahlForm()
    form.klassen.choices = get_klassen_choices()

    try:
        if form.validate_on_submit():
            klasse: str = form.klassen.data

            if form.submit_csv.data:
                try:
                    return _send_csv_file(export_to_csv(klasse), "azubis.csv")
                except Exception:
                    logger.exception("Fehler beim CSV-Export in route_azubianzeige")
                    flash("Fehler beim Erstellen der CSV-Datei.", "error")
                    return render_template(TEMPLATE_AZUBIANZEIGE, title=TITLE_AZUBIS, form=form)

            if form.submit_mail_tss.data:
                answer, category = send_mail_to_kontaktperson(export_to_csv(klasse), klasse)
                flash(Markup(answer), category)

            elif form.submit_mail_untis.data:
                flash_results = send_untisinfo_to_ausbilder(get_ausbilder_list_by_klasse(klasse))
                flash_all(flash_results)

            else:
                return "Aktion nicht gefunden", 404

        elif request.method == "POST":
            logger.warning("Formular-Fehler in route_azubianzeige: %s", form.errors)

        return render_template(
            TEMPLATE_AZUBIANZEIGE, title=TITLE_AZUBIS, form=form, kontaktperson=state.infos.kontaktperson
        )

    except Exception:
        logger.exception("Fehler in route_azubianzeige: ")
        abort(500)


@admin_bp.route("/upload.html", methods=["GET", "POST"])
@requires_auth("admin")
def route_upload() -> ResponseReturnValue:
    """Einstiegsseite für den direkten Datei-Upload (Azubis, Ausbilder, Info)."""
    form = FilehandlingAktionForm()

    try:
        action = request.args.get("action")
        if action not in ALLOWED_UPLOAD_ACTIONS:
            abort(400)

        title = f"Upload {action.title()} - WebUntis"
        flash(
            f"!! WICHTIG !! – Die bisherige Datei mit {action.title()}daten wird überschrieben.",
            "warning",
        )
        confirmmsg = f"Möchtest du wirklich ALLE {action.title()} löschen und mit Neuen überschreiben?"

        return render_template(
            TEMPLATE_UPLOAD,
            title=title,
            action=action,
            confirmmsg=confirmmsg,
            form=form,
        )

    except Exception:
        logger.exception("Fehler in route_upload: ")
        abort(500)


@admin_bp.route("/upload_direkt", methods=["POST"])
@requires_auth("admin")
def route_upload_direkt() -> ResponseReturnValue:
    """Verarbeitet den direkten Datei-Upload und aktualisiert die DB oder speichert die Datei."""
    form = FilehandlingAktionForm()
    action = ""
    title = ""

    if not (form.validate_on_submit() and form.action.data in ALLOWED_UPLOAD_ACTIONS):
        if request.method == "POST":
            flash_form_errors("route_upload_direkt", form)
        return render_template(TEMPLATE_UPLOAD, title=title, action=action, form=form)

    file = form.upload_file.data
    if not file:
        flash("Keine Datei ausgewählt.", "warning")
        return redirect(url_for("admin.route_upload", action=action))

    action = form.action.data
    title = f"Upload {action.title()} - WebUntis"

    match action:
        case "ausbilder":
            kind_of_data = "Ausbilderdaten"
            neue_eintraege = import_ausbilder_from_bytesio(uploaded_file_to_bytesio(file))
            answer, category = update_ausbilder_safe(neue_eintraege)
        case "azubis":
            kind_of_data = "Azubidaten"
            neue_eintraege = import_azubis_from_bytesio(uploaded_file_to_bytesio(file))
            answer, category = update_azubis_safe(neue_eintraege)
        case "info":
            kind_of_data = "Informationen"
            answer, category = save_file(file, state.infofile)
        case _:
            abort(500)

    flash(answer, category)

    if action != "info":
        if category == "success":
            flash(f"Die Datenbank wurde mit {kind_of_data} überschrieben.", "success")
        else:
            flash("Es gab einen Fehler bei der Erstellung der Datenbank.", "error")

    return render_template(TEMPLATE_UPLOAD, title=title, action=action, form=form)


@admin_bp.route("/download_prototyp", methods=["GET"])
@requires_auth("admin")
def route_download_prototyp() -> ResponseReturnValue:
    """Stellt Prototyp-Dateien (Info, Ausbilder, Azubis) zum Download bereit."""

    try:
        action = request.args.get("action")
        if not action:
            abort(400)

        prototype_path = _PROTOTYPE_FILES.get(action)
        if not prototype_path:
            abort(400)

        if not prototype_path.is_file():
            return "Datei nicht gefunden", 404

        return send_file(
            prototype_path,
            as_attachment=True,
            download_name=prototype_path.name,
            conditional=False,
        )

    except FileNotFoundError:
        return "Datei nicht gefunden", 404
    except Exception:
        logger.exception("Fehler beim Download des Prototyps: ")
        abort(500)


@admin_bp.route("/filehandling.html", methods=["GET", "POST"])
@requires_auth("admin")
def route_filehandling() -> ResponseReturnValue:
    """Dateimanager: Einzelne oder alle Dateien löschen, DB aktualisieren/zurücksetzen, Datei hochladen."""
    form = FilehandlingAktionForm()

    try:
        if form.validate_on_submit() and form.action.data in ALLOWED_FILE_ACTIONS:
            action: str = form.action.data

            match action:
                case "delete_single":
                    answer, category = delete_file_safe(form.filename.data)
                    flash(answer, category)
                case "delete_all":
                    if state.uploadfolder.exists():
                        for path in state.uploadfolder.iterdir():
                            answer, category = delete_file_safe(path.name)
                            flash(answer, category)
                case "update_db":
                    _update_db_from_upload(reset=False)
                case "reset_db":
                    _update_db_from_upload(reset=True)
                case "upload_file":
                    file = form.upload_file.data
                    if not file:
                        flash("Keine Datei ausgewählt.", "warning")
                    else:
                        answer, category = upload_file(file, state.uploadfolder)
                        flash(answer, category)
                case _:
                    flash("Unbekannte Aktion.", "error")

        elif request.method == "POST":
            flash_form_errors("route_filehandling", form)

        files = get_files_from_upload(state.uploadfolder)
        return render_template(
            TEMPLATE_FILEHANDLING,
            title=TITLE_FILEHANDLING,
            files=files,
            folder=state.uploadfolder,
            form=form,
        )

    except Exception:
        logger.exception("Fehler in route_filehandling: ")
        abort(500)


@admin_bp.route("/upload", methods=["POST"])
@requires_auth("admin")
def route_upload_file() -> ResponseReturnValue:
    """Datei-Upload-Endpunkt für den Filehandling-Bereich."""
    form = FilehandlingAktionForm()

    if form.validate_on_submit():
        file = form.upload_file.data
        if not file:
            flash("Keine Datei ausgewählt.", "warning")
            return redirect(url_for("admin.route_filehandling"))
        try:
            answer, category = upload_file(file, state.uploadfolder)
            flash(answer, category)
        except Exception:
            logger.exception("Fehler beim Datei-Upload: ")
            flash("Beim Upload ist ein Fehler aufgetreten.", "error")

    elif request.method == "POST":
        flash_form_errors(form, "route_upload_file")

    return redirect(url_for("admin.route_filehandling"))
