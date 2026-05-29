# -*- coding: utf-8 -*-
from typing import Any, List, Optional

from flask import current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_mail import Mail, Message
from markupsafe import Markup
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

"""Import Settings"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from src.base import (
    Ausbilder,
    Azubis,
    ConfigSetting,
    _delete_unconfirmed_ausbilder,
    _get_azubi_list,
    _update_ausbilder_safe,
    _update_azubis_safe,
    app,
    db,
)
from src.config import INFOTEXTE
from src.csvfiles import (
    _export_to_csv,
    _import_ausbilder_from_csv,
    _import_azubis_from_csv,
    _merge_csv_files,
)
from src.forms import AnmeldungForm, AusbilderAktionForm, AzubiAuswahlForm, ConfigForm, FilehandlingAktionForm
from src.helpies import (
    _get_error_page,
    _get_files_from_upload,
    _initialize_app,
    _log_message,
    _requires_auth,
    _save_file,
    _set_config,
    _token_is_valid,
    os,
    secure_filename,
)

# Wenn die Datenbank nicht existiert, wird sie erstellt
_initialize_app(app, db, ConfigSetting)

# Einstellungen laden
with app.app_context():
    # Konfiguration aus Datenbank lesen
    config_data = ConfigSetting.query.first()
    # Konfigurationsdaten setzen
    _set_config(app, config_data)

# Mailzugang erstellen (Daten des Mail-Account müssen vorher eingelesen werden)
mail = Mail(app)

# Ratenbegrenzung einrichten (10 Anfragen pro Minute pro IP-Adresse)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["10 per minute"],
    storage_uri="memory://",
)

# ------------------------------------------------------------------------------
# Pfade und Funktionen zu Dateiupload
# ------------------------------------------------------------------------------
ROOT_DIR = app.root_path

DATAFOLDER = os.path.join(ROOT_DIR, "data")
UPLOADFOLDER = os.path.join(ROOT_DIR, "upload")
STATICFOLDER = os.path.join(ROOT_DIR, "static")

RESULTFILE = os.path.join(DATAFOLDER, "result.csv")
AZUBIFILE = os.path.join(DATAFOLDER, "azubis.csv")
AUSBILDERFILE = os.path.join(DATAFOLDER, "ausbilder.csv")
LOGFILE = os.path.join(DATAFOLDER, "example.log")

INFOFILE = os.path.join(STATICFOLDER, "info.pdf")
PROTOTYPAZUBI = os.path.join(STATICFOLDER, "prototyp_azubis.csv")
PROTOTYPAUSBILDER = os.path.join(STATICFOLDER, "prototyp_ausbilder.csv")


# Kontaktperson
KONTAKTPERSON = app.config["UNTIS_KONTAKTPERSON"]


# ------------------------------------------------------------------------------
#   Mail
# ------------------------------------------------------------------------------
def __send_mail_to_ausbilder(ausbilder: Ausbilder):
    """sendet eine Mail mit der Bestätigung der Anmeldung an die Firma

    Args:
        ausbilder (Ausbilder): Ziel der Mail
    """
    INFOTEXTE["mail_1"] = Markup(INFOTEXTE["mail_1"])
    INFOTEXTE["mail_2"] = Markup(INFOTEXTE["mail_2"])
    subject = "Bestätigung der Azubianmeldung für WebUntis an der TSS Bitburg"
    try:
        msg = Message(subject=subject, recipients=[ausbilder.ausbilder_email])
        msg.html = render_template(
            "mail_ausbilder.html",
            ausbilder=ausbilder,
            server_url=request.url_root,
            kontakt_person=KONTAKTPERSON,
            INFOTEXTE=INFOTEXTE,
        )

        # print(ausbilder.ausbilder_email)
        # print(msg.html)
        mail.send(msg)
        info = (
            f"Die Mail wurde an {ausbilder.ausbilder_email} gesendet<br>"
            "Bitte bestätigen Sie Ihre Daten innerhalb von 2 Stunden"
        )
        return (Markup(info), "success")

    except Exception as e:
        _log_message(f"Fehler beim Senden der Mail: {e}", "error")
        return ("Die Mail konnte nicht gesendet werden:", "error")


# ------------------------------------------------------------------------------
#   Ausbilder-BEREICH
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index() -> str:
    """Startseite wird aufgerufen
    - optionales Prefill über token
    - Löschen unbestätigter Ausbilder
    - Anzeige von Infotexten und Anmeldeformular
    """
    title = "Anmeldeseite für Ausbilderbetriebe zur Nutzung von WebUntis"

    # 1) Cleanup: unbestätigte Ausbilder entfernen
    _delete_unconfirmed_ausbilder(app.config["UNTIS_TIMETOWAIT"])

    # 2) Optionales Prefill über token
    token: Optional[str] = request.args.get("token")
    ausbilder: Optional[Ausbilder] = None

    if token:
        # Beispiel-Daten laden (falls vorhanden)
        stmt = db.select(Ausbilder).where(Ausbilder.token == token)
        ausbilder = db.session.execute(stmt).scalars().first()

    # 3) Formular initialisieren (nur mit obj befüllen, wenn vorhanden)
    form = AnmeldungForm(obj=ausbilder) if ausbilder else AnmeldungForm()

    if form.validate_on_submit():
        # Verarbeite die Daten: form.ausbilder_name.data
        return redirect(url_for("bestaetigung"))

    info = f"<p>{INFOTEXTE['index_1']}</p><p>{INFOTEXTE['index_2']}</p>"

    flash(Markup(info), "success")
    return render_template("index.html", form=form, title=title, kontakt_person=KONTAKTPERSON)


@app.route("/bestaetigung.html", methods=["GET", "POST"])
@limiter.limit("3 per minute")  # Strenges Limit für Mailversand
def bestaetigung() -> str:
    title = "Anmeldung Ausbilderbetriebe WebUntis"

    # 1. Formular initialisieren
    form = AnmeldungForm()

    # 2) Nur bei valider Submission weiterarbeiten
    if not form.validate_on_submit():
        # Initiales Rendering oder Validierungsfehler
        return render_template(
            "bestaetigung.html",
            form=form,
            title=title,
        )

    # Daten direkt aus dem Formular-Objekt gelesen (sicher, da WTForms validiert hat)
    ausbilder_name = form.ausbilder_name.data
    ausbilder_vorname = form.ausbilder_vorname.data
    ausbilder_email = form.ausbilder_email.data
    ausbilder_betrieb = form.ausbilder_betrieb.data

    # IDs einsammeln und säubern
    schueler_ids: List[str] = [s.strip() for s in request.form.getlist("schueler_untis_id[]") if s and s.strip()]

    if not ausbilder_email:
        flash("E-Mail-Adresse des Ausbilders fehlt.", "warning")
        return render_template("bestaetigung.html", form=form, title=title)

    # Ausbilder in Datenbank suchen
    stmt_ausbilder = select(Ausbilder).where(Ausbilder.ausbilder_email == ausbilder_email)
    ausbilder: Optional[Ausbilder] = db.session.execute(stmt_ausbilder).scalar_one_or_none()

    try:
        # 1) Ausbilder neu anlegen
        neu_angelegt = False
        if ausbilder is None:
            ausbilder = Ausbilder(
                ausbilder_email=ausbilder_email,
                ausbilder_name=ausbilder_name,
                ausbilder_vorname=ausbilder_vorname,
                ausbilder_betrieb=ausbilder_betrieb,
                bestaetigt=False,
            )
            db.session.add(ausbilder)
            neu_angelegt = True

        # 2) Schüler-Zuordnung in einem Schwung
        liste_fehler: List[str] = []
        if schueler_ids:
            stmt_schueler = select(Azubis).where(Azubis.schueler_untis_id.in_(schueler_ids))
            gefundene_azubis: List[Azubis] = list(db.session.execute(stmt_schueler).scalars())

            gefundene_ids = {a.schueler_untis_id for a in gefundene_azubis}
            fehlende_ids = [sid for sid in schueler_ids if sid not in gefundene_ids]

            for schueler in gefundene_azubis:
                schueler.ausbilder_email = ausbilder_email

            liste_fehler.extend(fehlende_ids)

        # 3) Alles zusammen committen wenn es mindestens einen neuen Schüler gibt
        if gefundene_azubis:
            db.session.commit()
            # 4) E-Mail nur an neu angelegte Ausbilder senden
            if neu_angelegt:
                answer, category = __send_mail_to_ausbilder(ausbilder)
                flash(answer, category)

        # 5) Feedback
        if schueler_ids:
            if not liste_fehler:
                flash("Alle Schüler wurden erfolgreich zugeordnet.", "success")
            elif len(liste_fehler) < len(schueler_ids):
                flash("Einige Schüler konnten nicht zugeordnet werden", "warning")
            else:
                flash("Keine der angegebenen Schüler-IDs konnte gefunden werden.", "warning")
        else:
            flash("Es wurden keine Schüler-IDs übermittelt.", "info")

        return render_template(
            "bestaetigung.html",
            form=form,
            title=title,
            liste_erfolgreich=gefundene_azubis,
            liste_fehler=liste_fehler,
            ausbilder=ausbilder,
        )

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception("DB-Fehler in bestaetigung")
        _log_message(f"Fehler im Modul route_bestaetigung: {e}", "error")
        flash("Ein Datenbankfehler ist aufgetreten.", "error")
        return render_template("bestaetigung.html", form=form, title=title)


@app.route("/azubismitausbilder.html", methods=["GET", "POST"])
def azubismitausbilder() -> str:
    """Zeigt alle Azubis eines einzelnen Ausbilder an
    Der Ausbilder wird durch ein Token identifiziert

    Returns:
        str: Webseite
    """
    title = "Liste der zugeordneten Azubis in WebUntis"
    token: Optional[str] = request.args.get("token")

    # 1) Validierung: Token vorhanden und formal gültig?
    if not token or not _token_is_valid(token):
        flash("Kein Token angegeben oder Token ist ungültig.", "error")
        return render_template("azubismitausbilder.html", title=title, ausbilder=None)

    try:
        # 2) Ausbilder per 2.0-Select laden
        stmt = select(Ausbilder).where(Ausbilder.token == token)
        ausbilder: Optional[Ausbilder] = db.session.execute(stmt).scalar_one_or_none()

        if ausbilder is None:
            flash("Diesen Ausbilder gibt es nicht oder das Token ist ungültig.", "error")
            return render_template("azubismitausbilder.html", title=title, ausbilder=None)

        # 3) Bestätigen (idempotent) und Commit nur bei Änderung
        if not ausbilder.bestaetigt:
            ausbilder.bestaetigt = True
            db.session.commit()

        # 4) Zugeordnete Azubis laden
        azubi_liste: List[Azubis] = list(ausbilder.accounts)

        flash(Markup(INFOTEXTE["azubismitausbilder"]), "success")
        return render_template(
            "azubismitausbilder.html",
            title=title,
            azubi_liste=azubi_liste,
            ausbilder=ausbilder,
            kontakt_person=KONTAKTPERSON,
        )

    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception("DB-Fehler in azubismitausbilder")
        _log_message(f"Fehler im Modul azubismitausbilder (DB): {e}", "error")
        return _get_error_page()
    except Exception as e:
        current_app.logger.exception("Allg. Fehler in azubismitausbilder")
        _log_message(f"Fehler im Modul azubismitausbilder: {e}", "error")
        return _get_error_page()


@app.route("/api/zugeordete_schueler/<string:klasse_name>")
def zugeordete_schueler(klasse_name):
    """Diese Route wird von JavaScript aufgerufen, um alle Azubis einer Klasse anzuzeigen."""
    try:
        # Als JSON zurückgeben (das versteht JavaScript am besten)
        data: List[Any] = _get_azubi_list(klasse_name)
        return jsonify(data)

    except Exception as e:
        _log_message(f"Fehler im Modul zugeordete_schueler: {e}", "error")
        return jsonify([])


# ------------------------------------------------------------------------------
# +   ADMIN-BEREICH
# ------------------------------------------------------------------------------
@app.route("/admin.html", methods=["GET"])
@_requires_auth
def admin() -> str:
    """zeigt alle administrativen Aufgaben auf einer Webseite"""
    title = "Administration - Ausbilderbetriebe WebUntis"
    info = "<p>Hier finden Sie Links zu allen administrativen Aufgabe: </p>\
            <p>Eine Dokumentation finden Sie <a href='/static/Dokumentation.pdf') target='_blank' >HIER</a></p>"
    flash(Markup(info), "success")
    return render_template("admin.html", title=title)


@app.route("/config.html", methods=["GET", "POST"])
@_requires_auth
def config() -> str:
    """Zeigt die Webseite zur Eingabe der Konfigurtionsdaten an

    Returns:
        str: Webseite
    """
    title = "Einstellungen - Ausbilderbetriebe WebUntis"
    # Konfiguration laden (ersten Datensatz)
    cfg: Optional[ConfigSetting] = db.session.execute(select(ConfigSetting).limit(1)).scalar_one_or_none()
    try:
        form = ConfigForm(obj=cfg)
        if form.validate_on_submit():
            # Neu anlegen, falls noch keine Config vorhanden
            if cfg is None:
                cfg = ConfigSetting()
                db.session.add(cfg)

            # 1. Alle Felder außer Passwörter automatisch füllen
            # Dazu kopieren wir die Daten, aber lassen die PW-Felder aus
            for fieldname, value in form.data.items():
                if fieldname not in ["admin_password", "mail_password", "csrf_token", "submit"]:
                    setattr(cfg, fieldname, value)

            # 2) Passwörter nur setzen, wenn eingegeben
            if form.admin_password.data:
                cfg.admin_password = form.admin_password.data  # TODO: ggf. hashen
            if form.mail_password.data:
                cfg.mail_password = form.mail_password.data  # TODO: ggf. verschlüsseln

            try:
                # Daten in DB eintragen
                db.session.commit()
                flash("Konfiguration erfolgreich gespeichert.", "success")
                # Konfigurationsdaten aktualisieren
                _set_config(app, cfg)

            except SQLAlchemyError:
                db.session.rollback()
                current_app.logger.exception("DB-Fehler beim Speichern der Config")
                flash("Datenbankfehler beim Speichern der Konfiguration.", "error")
                return render_template("config.html", title=title, form=form), 500

        elif request.method == "POST":
            print("Formular-Fehler im Modul azubianzeige:", form.errors)

        return render_template(
            "config.html",
            title=title,
            form=form,
        )

    except Exception as e:
        current_app.logger.exception("Fehler im Modul config")
        _log_message(f"Fehler im Modul config: {e}", "error")
        return _get_error_page()


@app.route("/ausbilderanzeige.html", methods=["GET", "POST"])
@_requires_auth
def ausbilderanzeige() -> str:
    """Zeigt alle Ausbilder an

    Returns:
        str: Webseite
    """
    title = "Anzeige und Download der Ausbilderbetriebe"
    form = AusbilderAktionForm()
    ALLOWED_ACTIONS = ["add", "resend", "delete", "download", "show"]

    try:
        if form.validate_on_submit() and form.action.data in ALLOWED_ACTIONS:
            ausbilder_email: Optional[str] = form.ausbilder_email.data
            action: Optional[str] = form.action.data

            # gewählten Ausbilder aus der Datenbank holen
            stmt = select(Ausbilder).where(Ausbilder.ausbilder_email == ausbilder_email)
            ausbilder: Optional[Ausbilder] = db.session.execute(stmt).scalar_one_or_none()

            match action:
                case "show":
                    return redirect(url_for("azubismitausbilder", token=ausbilder.token))

                case "add":
                    return redirect(url_for("index", token=ausbilder.token))

                case "resend":
                    if ausbilder:
                        answer, category = __send_mail_to_ausbilder(ausbilder)
                        flash(answer, category)

                case "delete":
                    if ausbilder:
                        try:
                            db.session.delete(ausbilder)
                            db.session.commit()
                            flash(
                                f"{ausbilder.ausbilder_email} und alle Verknüpfungen zu Azubis wurden gelöscht",
                                "success",
                            )
                        except SQLAlchemyError:
                            db.session.rollback()
                            current_app.logger.exception("DB-Fehler beim Löschen in ausbilderanzeige")
                            flash("Datenbankfehler beim Löschen.", "error")

                case "download":
                    # CSV-Datei erstellen und Download
                    try:
                        path = _export_to_csv("ausbilder", RESULTFILE)
                        return send_file(path, as_attachment=True)
                    except Exception:
                        current_app.logger.exception("Fehler beim CSV-Export in ausbilderanzeige")
                        flash("Fehler beim Erstellen der CSV-Datei.", "error")
                        return redirect(url_for("ausbilderanzeige"))

                case _:
                    pass
        else:
            # Beginn: Es wurde kein Button geklickt, sondern die Seite wurde normal aufgerufen
            flash("Für weitere Informationen mit der Maus über die Kopfzeile fahren", "success")
        stmt = db.select(Ausbilder).order_by(Ausbilder.ausbilder_betrieb.asc())
        ausbilder_liste = db.session.execute(stmt).scalars().all()

        return render_template(
            "ausbilderanzeige.html",
            title=title,
            ausbilder_liste=ausbilder_liste,
            form=form,
        )

    except Exception as e:
        _log_message(f"Fehler im Modul ausbilderanzeige: {e}", "error")
        return _get_error_page()


@app.route("/azubianzeige.html", methods=["GET", "POST"])
@_requires_auth
def azubianzeige() -> str:
    """Anzeige und Download der Azubis einer Klasse oder allen.

    Returns:
    str: Webseite
    """
    title = "Anzeige und Download der Azubis"
    try:
        form = AzubiAuswahlForm()
        # 1. Alle Klassen eindeutig aus der DB holen
        klassen_liste = db.session.query(Azubis.klasse).distinct().order_by(Azubis.klasse.asc()).all()

        # 2. Choices dynamisch zusammenbauen (Standardoptionen + DB-Einträge)
        form.klassen.choices = [("", "Bitte wählen..."), ("all", "Alle Klassen")] + [
            (k.klasse, k.klasse) for k in klassen_liste if k.klasse
        ]

        if form.validate_on_submit():
            klasse = form.klassen.data
            # CSV-Datei erstellen und Download
            path = _export_to_csv(klasse, RESULTFILE)
            return send_file(path, as_attachment=True)
        elif request.method == "POST":
            print("Formular-Fehler im Modul azubianzeige:", form.errors)

        info = "Nach der Auswahl einer Klasse werden alle Azubis mit der verknüpften Mailadresse angezeigt.<br> \
                Auf Wunsch kann die Liste anschließend heruntergeladen werden."
        flash(Markup(info), "success")
        return render_template("azubianzeige.html", title=title, azubi_liste=klassen_liste, form=form)

    except Exception as e:
        _log_message(f"Fehler im Modul azubianzeige: {e}", "error")
        return _get_error_page()


@app.route("/upload.html", methods=["GET", "POST"])
@_requires_auth
def upload() -> str:
    """Bietet die Möglichkeit die Azubi oder Ausbilderdatei direkt zu überschreiben

    Returns:
        str: Webseite
    """

    try:
        form = FilehandlingAktionForm()

        if "action" in request.args:
            action = request.args.get("action")
            if action not in ["ausbilder", "azubis", "info"]:
                # Kein Aufruf von der Adminseite
                return "Die Seite wurde nicht korrekt aufgerufen"

            else:
                # Startseite zur Auswahl der Datei wird zurückgesendet
                title = f"Upload {action.title()} - WebUntis"
                flash(
                    f"!! WICHTIG !! - Die bisherige Datei mit {action.title()}daten wird überschrieben",
                    "warning",
                )
                confirmmsg = f"Möchtest du wirklich ALLE {action.title()} löschen, und mit Neuen überschreiben?"
                return render_template(
                    "upload.html",
                    title=title,
                    action=action,
                    confirmmsg=confirmmsg,
                    form=form,
                )

        return _get_error_page("Die Seite wurde nicht korrekt aufgerufen")
    except Exception as e:
        _log_message(f"Fehler im Modul upload: {e}", "error")
        return _get_error_page()


@app.route("/upload_direkt", methods=["POST"])
@_requires_auth
def upload_direkt() -> str:
    title = ""
    action = ""
    ALLOWED_ACTIONS = ["ausbilder", "azubis", "info"]

    form = FilehandlingAktionForm()
    if form.validate_on_submit() and form.action.data in ALLOWED_ACTIONS:
        file = form.upload_file.data
        if not file:
            flash("Keine Datei ausgewählt.", "warning")
            return redirect(url_for("upload_direkt", action=action))

        action: Optional[str] = form.action.data

        title = f"Upload {action.title()} - WebUntis"
        (answer, category) = ("", "")

        match action:
            case "ausbilder":
                kind_of_data = "Ausbilderdaten"
                answer, category = _save_file(file, AUSBILDERFILE)
                flash(answer, category)
                answer, category = _update_ausbilder_safe(_import_ausbilder_from_csv(AUSBILDERFILE))

            case "azubis":
                kind_of_data = "Azubidaten"
                answer, category = _save_file(file, AZUBIFILE)
                flash(answer, category)
                answer, category = _update_azubis_safe(_import_azubis_from_csv(AZUBIFILE))

            case "info":
                kind_of_data = "Informationen"
                answer, category = _save_file(file, INFOFILE)

            case _:
                return _get_error_page("Die Seite wurde nicht korrekt aufgerufen")

        flash(answer, category)

        if action != "info":
            if category == "success":
                flash(f"Die Datenbank wurde mit {kind_of_data} überschrieben", "success")
            else:
                flash("Es gab einen Fehler bei der Erstellung der Datenbank", "error")

    elif request.method == "POST":
        _log_message(f"Formular-Fehler im Modul filehandling: {form.errors}", "error")
        info = "Ungültige Eingaben  oder Sitzung abgelaufen."
        flash(Markup(info), "error")

    return render_template(
        "upload.html",
        title=title,
        action=action,
        prototyp="",
        form=form,
    )


@app.route("/download_prototyp", methods=["GET"])
@_requires_auth
def download_prototyp() -> str:
    ALLOWED_ACTIONS = {
        "info": INFOFILE,
        "ausbilder": PROTOTYPAUSBILDER,
        "azubis": PROTOTYPAZUBI,
    }
    try:
        action: Optional[str] = request.args.get("action")
        if not action:
            return _get_error_page("Die Seite wurde nicht korrekt aufgerufen")

        path = ALLOWED_ACTIONS.get(action)
        if not path:
            return _get_error_page("Die Seite wurde nicht korrekt aufgerufen")

        # Sicherstellen, dass Datei existiert
        if not os.path.isfile(path):
            # send_file würde NotFound werfen; wir geben eine klare Antwort
            return "Datei nicht gefunden", 404

        filename = os.path.basename(path)
        return send_file(
            path,
            as_attachment=True,
            download_name=filename,  # Flask ≥ 2.0
            conditional=True,  # ETag/Range unterstützen
        )
    except FileNotFoundError:
        return "Datei nicht gefunden", 404
    except Exception as e:
        _log_message(f"Fehler beim Download des Prototyps: {e}", "error")
        return _get_error_page()


@app.route("/filehandling.html", methods=["GET", "POST"])
@_requires_auth
def filehandling() -> str:
    title = "Dateimanager - Azubis WebUntis"
    form = FilehandlingAktionForm()
    ALLOWED_ACTIONS = [
        "delete_single",
        "delete_all",
        "update_db",
        "reset_db",
        "upload_file",
    ]

    def __update_db(reset=False):
        """CSV-Dateien zusammenführen und DB aktualisieren (optional reset)."""
        # Alle Datien zu einer verbinden und als AZUBIFILE abspeichern
        if not _merge_csv_files(UPLOADFOLDER, AZUBIFILE):
            flash("Fehler beim zusammenfassen der einzelnen Dateien", "error")
            return
        try:
            liste_neue_azubis = _import_azubis_from_csv(AZUBIFILE)
            # Neue Daten einlesen, und Tabelle vorher leeren, wenn reset=True
            answer, category = _update_azubis_safe(liste_neue_azubis, reset)
            flash(answer, category)
        except Exception:
            current_app.logger.exception("Allg. Fehler bei update_db")
            flash("Fehler beim Aktualisieren der Daten.", "error")

    def __delete_file_safe(filename):
        """Sicheres Löschen einer einzelnen Datei mit Feedback."""

        if not filename:
            flash("Kein Dateiname angegeben.", "error")
            return
        safe_name = secure_filename(filename)
        file_path = os.path.join(UPLOADFOLDER, safe_name)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                flash(f'Datei "{filename}" wurde gelöscht.', "success")
            except OSError:
                current_app.logger.exception("Fehler beim Löschen der Datei %s", file_path)
                flash(f'Datei "{safe_name}" konnte nicht gelöscht werden.', "error")
        else:
            flash("Die Datei wurde nicht gefunden.", "error")

    try:
        if form.validate_on_submit() and form.action.data in ALLOWED_ACTIONS:
            action: Optional[str] = form.action.data

            match action:
                case "delete_single":
                    __delete_file_safe(form.filename.data)

                case "delete_all":
                    if os.path.exists(UPLOADFOLDER):
                        for name in os.listdir(UPLOADFOLDER):
                            __delete_file_safe(name)

                case "update_db":
                    __update_db(False)

                case "reset_db":
                    print("Datenbank zurücksetzen und neu erstellen")
                    __update_db(True)

                case "upload_file":
                    file = form.upload_file.data
                    if not file:
                        flash("Keine Datei ausgewählt.", "warning")
                    else:
                        answer, category = _save_file(file, UPLOADFOLDER, True)
                        flash(answer, category)

                case _:
                    flash("Unbekannte Aktion.", "error")

        elif request.method == "POST":
            _log_message(f"Formular-Fehler im Modul filehandling: {form.errors}", "error")
            info = "Ungültige Eingaben  oder Sitzung abgelaufen."
            flash(Markup(info), "error")

        files = _get_files_from_upload(UPLOADFOLDER)
        return render_template(
            "filehandling.html",
            title=title,
            files=files,
            folder=UPLOADFOLDER,
            form=form,
        )

    except Exception as e:
        _log_message(f"Fehler im Modul filehandling: {e}", "error")
        return _get_error_page()


@app.route("/upload", methods=["POST"])
@_requires_auth
def upload_file() -> str:
    form = FilehandlingAktionForm()
    if form.validate_on_submit():
        file = form.filename.data
        if not file:
            flash("Keine Datei ausgewählt.", "warning")
            return redirect(url_for("filehandling"))
        try:
            answer, category = _save_file(file, UPLOADFOLDER, True)
            flash(answer, category)

        except Exception as e:
            current_app.logger.exception("Fehler beim Datei-Upload")
            _log_message(f"Fehler im Modul upload_file: {e}", "error")
            flash("Beim Upload ist ein Fehler aufgetreten.", "error")
    else:
        # Formular- oder CSRF-Fehler
        if request.method == "POST":
            _log_message(f"Formular-Fehler im Modul upload_file: {form.errors}", "error")

    return redirect(url_for("filehandling"))
