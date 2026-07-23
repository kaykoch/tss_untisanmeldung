# ------------------------------------------------------------------------------
#     ADMIN-BEREICH
# ------------------------------------------------------------------------------

import logging
import os

from cryptography.fernet import Fernet
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
from werkzeug.security import generate_password_hash

from src.extensions import state
from src.forms import AusbilderAktionForm, AzubiAuswahlForm, ConfigForm, FilehandlingAktionForm
from src.models import (
    Ausbilder,
    Azubis,
    ConfigSetting,
)
from src.services.ausbilder_service import (
    delete_ausbilder,
    get_ausbilder_by_email,
    get_ausbilder_by_klasse,
    update_ausbilder_safe,
)
from src.services.azubi_service import build_klassen_choices, update_azubis_safe
from src.services.config_service import load_defaults
from src.services.csv_service import (
    export_to_csv,
    import_ausbilder_from_bytesio,
    import_azubis_from_bytesio,
    merge_csv_to_bytesio,
)
from src.services.file_service import delete_file_safe, get_files_from_upload, save_file, uploaded_file_to_bytesio
from src.services.mail_service import send_mail_to_ausbilder, send_mail_to_kontaktperson, send_untisinfo_to_ausbilder
from src.utils.auth import requires_auth
from src.utils.helpers import flash_form_errors


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

ALLOWED_UPLOAD_ACTIONS = ["ausbilder", "azubis", "info"]
ALLOWED_AUSBILDER_ACTIONS = ["add", "resend", "delete", "download", "show"]
ALLOWED_FILE_ACTIONS = ["delete_single", "delete_all", "update_db", "reset_db", "upload_file"]

_HASH_PASSWORD_FIELDS: frozenset[str] = frozenset({"admin_password", "tss_password"})
_SYSTEM_FIELDS: frozenset[str] = frozenset({"csrf_token", "submit"})
_EXCLUDED_FIELDS: frozenset[str] = _HASH_PASSWORD_FIELDS | _SYSTEM_FIELDS

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
    return send_file(
        file_io,
        mimetype="text/csv; charset='utf-8'",
        as_attachment=True,
        download_name=download_name,
        conditional=False,
    )


# ------------------------------------------------------------------------------
# Hilfsfunktionen – route_config
# ------------------------------------------------------------------------------


def _apply_non_password_fields(form: ConfigForm, cfg: ConfigSetting) -> None:
    """Schreibt alle Nicht-Passwort- und Nicht-Systemfelder in das Config-Objekt."""
    for fieldname, value in form.data.items():
        if fieldname not in _EXCLUDED_FIELDS:
            setattr(cfg, fieldname, value)


def _apply_password_fields(form: ConfigForm, cfg: ConfigSetting) -> None:
    """Verarbeitet Passwörter: Admin/TSS werden gehasht, Mail wird verschlüsselt."""
    print(1111)

    # 1. Admin & TSS Passwörter HASHTEN (One-Way)
    for field in _HASH_PASSWORD_FIELDS:
        if form[field].data:
            hashed_password = generate_password_hash(form[field].data)
            setattr(cfg, field, hashed_password)

    # 2. Mail-Passwort VERSCHLÜSSELN (Two-Way)
    if form.mail_password.data:
        # Hole den Master-Key aus den Umgebungsvariablen der app (config.py)
        secret_key = state.app.config["ENCRYPTION_KEY"]

        if secret_key:
            fernet = Fernet(secret_key.encode())
            # Passwort in Bytes umwandeln, verschlüsseln und als String in DB speichern
            encrypted_password = fernet.encrypt(form.mail_password.data.encode()).decode()
            cfg.mail_password = encrypted_password
        else:
            # Sicherheits-Fallback, falls du den Key vergessen hast einzurichten
            logger.error("E-Mail-Passwort konnte nicht verschlüsselt werden: ENCRYPTION_KEY fehlt!")
            flash("Fehler: Verschlüsselungs-Key nicht konfiguriert.", "error")


# ------------------------------------------------------------------------------
# Hilfsfunktionen – route_filehandling
# ------------------------------------------------------------------------------


def _update_db_from_upload(reset: bool = False) -> None:
    """Fasst alle CSV-Dateien im Upload-Ordner zusammen und aktualisiert die Azubi-Datenbank.

    Mit reset=True werden alle bestehenden Einträge vorher gelöscht.

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
        logger.error("Allg. Fehler bei _update_db_from_upload")
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
    stmt = state.db.select(ConfigSetting).limit(1)
    cfg: ConfigSetting | None = state.db.session.execute(stmt).scalar_one_or_none()

    try:
        form = ConfigForm(obj=cfg)

        if form.validate_on_submit():
            if cfg is None:
                cfg = ConfigSetting()
                state.db.session.add(cfg)

            _apply_non_password_fields(form, cfg)
            _apply_password_fields(form, cfg)

            try:
                state.db.session.commit()
                flash("Konfiguration erfolgreich gespeichert.", "success")
                load_defaults()

            except SQLAlchemyError:
                state.db.session.rollback()
                logger.error("DB-Fehler beim Speichern der Config")
                flash("Datenbankfehler beim Speichern der Konfiguration.", "error")
                return render_template(TEMPLATE_CONFIG, title=TITLE_CONFIG, form=form), 500

        elif request.method == "POST":
            logger.error("Formular-Fehler in route_config: %s", form.errors)

        return render_template(TEMPLATE_CONFIG, title=TITLE_CONFIG, form=form)

    except Exception as e:
        logger.error("Fehler in route_config: %s", e)
        abort(500)


@admin_bp.route("/ausbilderanzeige.html", methods=["GET", "POST"])
@requires_auth("admin")
def route_ausbilderanzeige() -> ResponseReturnValue:
    """Zeigt alle Ausbilder an und erlaubt Aktionen (anzeigen, hinzufügen, Mail, löschen, Download)."""
    form = AusbilderAktionForm()

    try:
        if form.validate_on_submit() and form.action.data in ALLOWED_AUSBILDER_ACTIONS:
            ausbilder_email: str | None = form.ausbilder_email.data
            action: str = form.action.data
            ausbilder = get_ausbilder_by_email(ausbilder_email)

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
                        flash(answer, category)
                case "delete":
                    if ausbilder:
                        delete_ausbilder(ausbilder)
                case "download":
                    try:
                        return _send_csv_file(export_to_csv("ausbilder"), "ausbilder.csv")
                    except Exception:
                        logger.error("Fehler beim CSV-Export in route_ausbilderanzeige")
                        flash("Fehler beim Erstellen der CSV-Datei.", "error")
                        return redirect(url_for("admin.route_ausbilderanzeige"))
        else:
            if request.method == "GET":
                flash("Für weitere Informationen mit der Maus über die Kopfzeile fahren.", "success")

        stmt = state.db.select(Ausbilder).order_by(Ausbilder.ausbilder_betrieb.asc())
        ausbilder_liste = state.db.session.execute(stmt).scalars().all()

        return render_template(
            TEMPLATE_AUSBILDER,
            title=TITLE_AUSBILDER,
            ausbilder_liste=ausbilder_liste,
            form=form,
        )

    except Exception as e:
        logger.error("Fehler in route_ausbilderanzeige: %s", e)
        abort(500)


@admin_bp.route("/azubianzeige.html", methods=["GET", "POST"])
@requires_auth("admin")
def route_azubianzeige() -> ResponseReturnValue:
    """Anzeige und Download der Azubis einer Klasse oder aller Klassen."""
    form = AzubiAuswahlForm()
    build_klassen_choices(form)

    try:
        if form.validate_on_submit():
            klasse: str = form.klassen.data

            if getattr(form, "submit_csv", None) and form.submit_csv.data:
                return _send_csv_file(export_to_csv(klasse), "azubis.csv")

            if getattr(form, "submit_mail_tss", None) and form.submit_mail_tss.data:
                send_mail_to_kontaktperson(export_to_csv(klasse), klasse)

            elif getattr(form, "submit_mail_untis", None) and form.submit_mail_untis.data:
                send_untisinfo_to_ausbilder(get_ausbilder_by_klasse(klasse))

            else:
                return "Aktion nicht gefunden", 404

        elif request.method == "POST":
            logger.error("Formular-Fehler in route_azubianzeige: %s", form.errors)

        info = Markup(
            "Nach der Auswahl einer Klasse werden alle Azubis mit der verknüpften Mailadresse angezeigt.<br>"
            "Auf Wunsch kann:<br>"
            "- die Liste anschließend heruntergeladen werden<br>"
            f" - die Liste direkt per Mail an die Kontaktperson versendet werden → {state.kontaktperson.komplett}<br>"
            " - alle Ausbilder per Mail über den angelegten Untis-Account informiert werden"
        )
        flash(info, "success")

        klassen_liste = state.db.session.query(Azubis.klasse).distinct().order_by(Azubis.klasse.asc()).all()
        return render_template(
            TEMPLATE_AZUBIANZEIGE,
            title=TITLE_AZUBIS,
            azubi_liste=klassen_liste,
            form=form,
        )

    except Exception as e:
        logger.error("Fehler in route_azubianzeige: %s", e)
        abort(500)


@admin_bp.route("/upload.html", methods=["GET", "POST"])
@requires_auth("admin")
def route_upload() -> ResponseReturnValue:
    """Einstiegsseite für den direkten Datei-Upload (Azubis, Ausbilder, Info)."""
    form = FilehandlingAktionForm()

    try:
        action = request.args.get("action")
        if action not in ALLOWED_UPLOAD_ACTIONS:
            abort(500)

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

    except Exception as e:
        logger.error("Fehler in route_upload: %s", e)
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
            flash_form_errors(form, "route_upload_direkt")
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
    PROTOTYPE_FILES = {
        "info": state.infofile,
        "ausbilder": state.prototypeausbilder,
        "azubis": state.prototypeazubi,
    }

    try:
        action = request.args.get("action")
        if not action:
            abort(500)

        prototype_path = PROTOTYPE_FILES.get(action)
        if not prototype_path:
            abort(500)

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
    except Exception as e:
        logger.error("Fehler beim Download des Prototyps: %s", e)
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
                    delete_file_safe(form.filename.data)
                case "delete_all":
                    if os.path.exists(state.uploadfolder):
                        for name in os.listdir(state.uploadfolder):
                            delete_file_safe(name)
                case "update_db":
                    _update_db_from_upload(reset=False)
                case "reset_db":
                    _update_db_from_upload(reset=True)
                case "upload_file":
                    file = form.upload_file.data
                    if not file:
                        flash("Keine Datei ausgewählt.", "warning")
                    else:
                        answer, category = save_file(file, state.uploadfolder, True)
                        flash(answer, category)
                case _:
                    flash("Unbekannte Aktion.", "error")

        elif request.method == "POST":
            flash_form_errors(form, "route_filehandling")

        files = get_files_from_upload(state.uploadfolder)
        return render_template(
            TEMPLATE_FILEHANDLING,
            title=TITLE_FILEHANDLING,
            files=files,
            folder=state.uploadfolder,
            form=form,
        )

    except Exception as e:
        logger.error("Fehler in route_filehandling: %s", e)
        abort(500)


@admin_bp.route("/upload", methods=["POST"])
@requires_auth("admin")
def route_upload_file() -> ResponseReturnValue:
    """Datei-Upload-Endpunkt für den Filehandling-Bereich."""
    form = FilehandlingAktionForm()

    if form.validate_on_submit():
        file = form.filename.data
        if not file:
            flash("Keine Datei ausgewählt.", "warning")
            return redirect(url_for("admin.route_filehandling"))
        try:
            answer, category = save_file(file, state.uploadfolder, True)
            flash(answer, category)
        except Exception as e:
            logger.error("Fehler beim Datei-Upload: %s", e)
            flash("Beim Upload ist ein Fehler aufgetreten.", "error")

    elif request.method == "POST":
        flash_form_errors(form, "route_upload_file")

    return redirect(url_for("admin.route_filehandling"))
