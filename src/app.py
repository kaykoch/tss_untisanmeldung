# -*- coding: utf-8 -*-

from flask import flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_mail import Mail, Message
from markupsafe import Markup

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
        print(ausbilder.ausbilder_email)
        # print(msg.html)
        # mail.send(msg)
        return (f"Die Mail wurde an {ausbilder.ausbilder_email} gesendet", "success")

    except Exception as e:
        _log_message(f"Fehler beim Senden der Mail: {e}", "error")
        return ("Die Mail konnte nicht gesendet werden:", "error")


# ------------------------------------------------------------------------------
#   Ausbilder-BEREICH
# ------------------------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def index() -> str:
    """Startseite wird aufgerufen
    Enweder zu Beginn, oder wieder nach erfolgter Anmeldung

    Returns:
    str: Webseite
    """
    title = "Anmeldeseite für Ausbilderbetriebe zur Nutzung von WebUntis"
    # löscht alle Ausbilder die ihre Mail nicht bestätigt haben und ihre Vernüpfungen
    _delete_unconfirmed_ausbilder(app.config["UNTIS_TIMETOWAIT"])

    # Beispiel-Daten laden (falls vorhanden)
    ausbilder = Ausbilder.query.filter_by(token=request.args.get("token")).first()

    # Formular mit Daten des Ausbilders vorbefüllen, falls vorhanden
    form = AnmeldungForm(obj=ausbilder)

    if form.validate_on_submit():
        # Verarbeite die Daten: form.ausbilder_name.data
        return redirect(url_for("bestaetigung"))

    info = f"<p>{INFOTEXTE['index_1']}</p>\
             <p>{INFOTEXTE['index_2']}</p>"

    flash(Markup(info), "success")
    return render_template("index.html", form=form, title=title, kontakt_person=KONTAKTPERSON)


@app.route("/bestaetigung.html", methods=["GET", "POST"])
@limiter.limit("3 per minute")  # Strenges Limit für Mailversand
def bestaetigung() -> str:
    title = "Anmeldung Ausbilderbetriebe WebUntis"
    liste_erfolgreich = []
    liste_fehler = []
    ausbilder = None
    schueler_ids = []

    # 1. Formular initialisieren
    form = AnmeldungForm()

    # 2. Prüfen, ob das Formular valide abgeschickt wurde (inkl. CSRF-Check)
    if form.validate_on_submit():
        # Daten direkt aus dem Formular-Objekt gelesen (sicher, da WTForms validiert hat)
        ausbilder_name = form.ausbilder_name.data
        ausbilder_vorname = form.ausbilder_vorname.data
        ausbilder_email = form.ausbilder_email.data
        ausbilder_betrieb = form.ausbilder_betrieb.data

        # Falls schueler_ids weiterhin dynamisch per JavaScript übergeben werden,
        # kannst du sie wie gewohnt auslesen (oder als FieldList im Formular definieren)
        schueler_ids = request.form.getlist("schueler_untis_id[]")

        # Ausbilder in Datenbank suchen
        ausbilder = Ausbilder.query.filter_by(ausbilder_email=ausbilder_email).first()

        if not ausbilder and ausbilder_email:
            # Ausbilder anlegen
            ausbilder = Ausbilder(
                ausbilder_email=ausbilder_email,
                ausbilder_name=ausbilder_name,
                ausbilder_vorname=ausbilder_vorname,
                ausbilder_betrieb=ausbilder_betrieb,
                bestaetigt=False,
            )
            db.session.add(ausbilder)
            db.session.commit()  # Direkt committen, um Token zu generieren

            # Mail an neuen Ausbilder versenden
            answer, category = __send_mail_to_ausbilder(ausbilder)
            flash(answer, category)

        # 3. Transaktionssichere Aktualisierung der Azubis
        try:
            for s_id in schueler_ids:
                if not s_id:
                    continue

                schueler = Azubis.query.filter_by(schueler_untis_id=s_id).first()
                if schueler:
                    schueler.ausbilder_email = ausbilder_email
                    liste_erfolgreich.append(schueler)
                else:
                    liste_fehler.append(s_id)

            db.session.commit()

            if not liste_fehler:
                flash("Erfolgreich gespeichert.", "success")
            else:
                flash("Einige Schüler konnten nicht zugeordnet werden.", "warning")

        except Exception as e:
            db.session.rollback()
            _log_message(f"Fehler im Modul route_bestaetigung: {e}", "error")
            flash("Ein Datenbankfehler ist aufgetreten.", "error")

    elif request.method == "POST":
        # Wenn POST, aber validate_on_submit() False war, gab es ein CSRF-Problem
        # oder ein Pflichtfeld wurde im Browser manipuliert.
        print("Formular-Fehler:", form.errors)
        info = "Ungültige Eingaben (Email, Namen etc.) oder Sitzung abgelaufen.<br> Bitte Daten überprüfen und erneut versuchen."
        flash(Markup(info), "error")
        return redirect(url_for("index"))

    return render_template(
        "bestaetigung.html",
        title=title,
        liste_erfolgreich=liste_erfolgreich,
        liste_fehler=liste_fehler,
        kontakt_person=KONTAKTPERSON,
        ausbilder=ausbilder,
        form=form,  # Weitergabe an das Template (für den CSRF-Token)
    )


@app.route("/azubismitausbilder.html", methods=["GET", "POST"])
def azubismitausbilder() -> str:
    """Zeigt alle Azubis eines einzelnen Ausbilder an
    Der Ausbilder wird durch ein Token identifiziert

    Returns:
        str: Webseite
    """
    title = "Liste der zugeordneten Azubis in WebUntis"
    azubi_liste = []
    ausbilder = None

    # Übertragene Formulardaten auslesen
    token = request.args.get("token")

    # 1. Validierung: Token vorhanden?
    if not token or not _token_is_valid(token):
        flash("Kein Token angegeben oder Token ist ungültig.", "error")
        return render_template("azubismitausbilder.html", title=title, ausbilder=None)

    try:
        # 2. Suche Ausbilder mittels ORM (verhindert SQL-Injection automatisch)
        ausbilder = Ausbilder.query.filter_by(token=token).first()
        if ausbilder:
            # 3. Bestätigungs-Logik via ORM
            if not ausbilder.bestaetigt:
                ausbilder.bestaetigt = True
                db.session.commit()

            # 4. Abfrage der Azubis via ORM-Beziehung
            azubi_liste = ausbilder.accounts

            flash(Markup(INFOTEXTE["azubismitausbilder"]), "success")
        else:
            flash("Diesen Ausbilder gibt es nicht oder das Token ist ungültig.", "error")

    except Exception as e:
        _log_message(f"Fehler im Modul azubismitausbilder: {e}", "error")
        return _get_error_page()

    return render_template(
        "azubismitausbilder.html",
        title=title,
        azubi_liste=azubi_liste,
        ausbilder=ausbilder,
        kontakt_person=KONTAKTPERSON,
    )


@app.route("/api/zugeordete_schueler/<string:klasse_name>")
def zugeordete_schueler(klasse_name):
    """Diese Route wird von JavaScript aufgerufen, um alle Azubis einer Klasse anzuzeigen."""
    try:
        # Als JSON zurückgeben (das versteht JavaScript am besten)
        return jsonify(_get_azubi_list(klasse_name))

    except Exception as e:
        _log_message(f"Fehler im Modul zugeordete_schueler: {e}", "error")
        return jsonify(list())


# ------------------------------------------------------------------------------
# +   ADMIN-BEREICH
# ------------------------------------------------------------------------------
@app.route("/admin.html", methods=["GET", "POST"])
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
    config = ConfigSetting.query.first()
    try:
        form = ConfigForm(obj=config)
        if form.validate_on_submit():
            if config is None:
                config = ConfigSetting()
                db.session.add(config)

            # 1. Alle Felder außer Passwörter automatisch füllen
            # Dazu kopieren wir die Daten, aber lassen die PW-Felder aus
            for fieldname, value in form.data.items():
                if fieldname not in ["admin_password", "mail_password", "csrf_token", "submit"]:
                    setattr(config, fieldname, value)

            # 2. Passwörter nur überschreiben, wenn etwas eingegeben wurde
            if form.admin_password.data:
                config.admin_password = form.admin_password.data

            if form.mail_password.data:
                config.mail_password = form.mail_password.data
                print("admin", form.mail_password.data)
            db.session.commit()
            flash("Konfiguration erfolgreich gespeichert!")

        elif request.method == "POST":
            print("Formular-Fehler im Modul azubianzeige:", form.errors)
        return render_template("config.html", title=title, form=form)

    except Exception as e:
        print(f"Fehler im Modul config: {e}")
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

    try:
        form = AusbilderAktionForm()

        if form.validate_on_submit() and form.action.data in ["add", "resend", "delete", "download", "show"]:
            ausbilder_email = form.ausbilder_email.data
            action = form.action.data

            # gewählten Ausbilder aus der Datenbank holen
            ausbilder = Ausbilder.query.filter_by(ausbilder_email=ausbilder_email).first()

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
                        db.session.delete(ausbilder)
                        db.session.commit()
                        flash(
                            f"{ausbilder.ausbilder_email} und alle Verknüpfungen zu Azubis wurden gelöscht",
                            "success",
                        )

                case "download":
                    # CSV-Datei erstellen und Download
                    path = _export_to_csv("ausbilder", RESULTFILE)
                    return send_file(path, as_attachment=True)
                case _:
                    pass
        else:
            # Beginn: Es wurde kein Button geklickt, sondern die Seite wurde normal aufgerufen
            flash("Für weitere Informationen mit der Maus über die Kopfzeile fahren", "success")

        ausbilder_liste = Ausbilder.query.order_by(Ausbilder.ausbilder_betrieb).all()
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
    prototyp = ""
    action = ""

    form = FilehandlingAktionForm()
    if form.validate_on_submit() and form.action.data in [
        "ausbilder",
        "azubis",
        "info",
    ]:
        file = form.upload_file.data
        action = form.action.data

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
        prototyp=prototyp,
        form=form,
    )


@app.route("/download_prototyp", methods=["GET"])
@_requires_auth
def download_prototyp() -> str:
    if request.method == "GET":
        if "action" in request.args:
            action = request.args.get("action")
            if action not in ["ausbilder", "azubis", "info"]:
                # Kein Aufruf von der Adminseite
                return _get_error_page("Die Seite wurde nicht korrekt aufgerufen")
            else:
                match action:
                    case "info":
                        path = INFOFILE
                    case "ausbilder":
                        path = PROTOTYPAUSBILDER
                    case "azubis":
                        path = PROTOTYPAZUBI
                return send_file(path, as_attachment=True)


@app.route("/filehandling.html", methods=["GET", "POST"])
@_requires_auth
def filehandling() -> str:
    title = "Dateimanager - Azubis WebUntis"

    def __update_db(reset=False):
        # Alle Datien zu einer verbinden und als AZUBIFILE abspeichern
        if not _merge_csv_files(UPLOADFOLDER, AZUBIFILE):
            flash("Fehler beim zusammenfassen der einzelnen Dateien", "error")
        else:
            liste_neue_azubis = _import_azubis_from_csv(AZUBIFILE)
            # Neue Daten einlesen, und Tabelle vorher leeren, wenn reset=True
            answer, category = _update_azubis_safe(liste_neue_azubis, reset)
            flash(answer, category)

    def __delete_file(filename):
        file_path = os.path.join(UPLOADFOLDER, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            flash(f'Datei "{filename}" wurde gelöscht.', "success")
        else:
            flash("Die Datei wurde nicht gefunden.", "error")

    try:
        form = FilehandlingAktionForm()

        if form.validate_on_submit() and form.action.data in [
            "delete_single",
            "delete_all",
            "update_db",
            "reset_db",
            "upload_file",
        ]:
            filename = form.filename.data
            action = form.action.data
            print(action)

            match action:
                case "delete_single":
                    print("Einzelne Datei löschen")
                    filename = secure_filename(filename)
                    __delete_file(filename)

                case "delete_all":
                    print("Alle Dateien löschen")
                    if os.path.exists(UPLOADFOLDER):
                        for filename in os.listdir(UPLOADFOLDER):
                            filename = secure_filename(filename)
                            __delete_file(filename)

                case "update_db":
                    print("Datenbank aktualisieren")
                    __update_db(False)

                case "reset_db":
                    print("Datenbank zurücksetzen und neu erstellen")
                    __update_db(True)

                case "upload_file":
                    print("Neue Datei zum hochladen")
                    answer, category = _save_file(form.upload_file.data, UPLOADFOLDER, True)
                    flash(answer, category)

                case _:
                    pass

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
        answer, category = _save_file(file, UPLOADFOLDER, True)
        flash(answer, category)

    elif request.method == "POST":
        _log_message(f"Formular-Fehler im Modul upload_file: {form.errors}", "error")

    return redirect(url_for("filehandling"))
