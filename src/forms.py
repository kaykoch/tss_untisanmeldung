# ------------------------------------------------------------------------------
# Überprüft durch Claude 4
# ------------------------------------------------------------------------------

import re

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed
from wtforms import (
    EmailField,
    FileField,
    HiddenField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.validators import AnyOf, DataRequired, Email, Length, NumberRange, Optional


# ------------------------------------------------------------------------------
# Konstanten
# ------------------------------------------------------------------------------

_ALLOWED_UPLOAD_EXTENSIONS = frozenset({"csv", "pdf"})

PASSWORD_LENGTH = Length(min=4, max=15)
NAME_LENGTH = Length(max=255)
EMAIL_LENGTH = Length(max=320)


# ------------------------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------------------------
def email_validators() -> list:
    """Gibt eine neue Liste mit Standard-E-Mail-Validatoren zurück.

    Jeder Aufruf erzeugt eine eigene Instanz, um mutable shared state zu vermeiden.

    Returns:
        Liste mit DataRequired, Email und Length-Validator.
    """
    return [
        DataRequired(message="Bitte geben Sie eine E-Mail-Adresse ein."),
        Email(message="Bitte geben Sie eine gültige E-Mail-Adresse ein."),
        Length(max=255),
    ]


def normalize_whitespace(value: str | None) -> str | None:
    """Bereinigt einen String: trimmt Ränder und reduziert Leerzeichen auf eines.

    Args:
        value: Eingabewert aus dem Formularfeld.

    Returns:
        Bereinigter String oder None, wenn der Eingabewert None war.
    """
    if value is None:
        return None
    result = re.sub(r"\s+", " ", str(value).strip())
    return result or None  # "" → None → DataRequired() schlägt an


# ------------------------------------------------------------------------------
# Formulare
# ------------------------------------------------------------------------------


class AusbilderAktionForm(FlaskForm):
    """Aktionen auf der Ausbilderliste auslösen (z. B. Bestätigen, Löschen)."""

    ausbilder_email = HiddenField(
        "Email",
        filters=[normalize_whitespace],
        validators=email_validators(),
        render_kw={"id": "form_email"},
    )
    action = HiddenField(
        "Action",
        validators=[DataRequired()],
        render_kw={"id": "form_action"},
    )


class FilehandlingAktionForm(FlaskForm):
    """Dateiverwaltung: Löschen, Importieren, Zusammenführen, etc."""

    filename = HiddenField("Filename", validators=[Optional()])
    action = HiddenField("Action", validators=[DataRequired()])
    upload_file = FileField(
        "Datei auswählen",
        validators=[
            Optional(),
            FileAllowed(_ALLOWED_UPLOAD_EXTENSIONS, "Nur CSV- und PDF-Dateien sind erlaubt!"),
        ],
        render_kw={"accept": ".csv,.pdf"},
    )


class AzubiAuswahlForm(FlaskForm):
    """Klasse auswählen für Anzeige oder Download."""

    klassen = SelectField(
        "Welche Klasse soll angezeigt werden / wollen Sie herunterladen?",
        validators=[DataRequired(message="Bitte wählen Sie eine Klasse aus.")],
        choices=[],
        render_kw={"class": "form-select"},
    )
    submit_csv = SubmitField("Download-CSV", render_kw={"class": "btn btn-primary midi"})
    submit_mail_tss = SubmitField("Mailversand-CSV", render_kw={"class": "btn btn-primary midi"})
    submit_mail_untis = SubmitField("Mailversand-Untis", render_kw={"class": "btn btn-warning midi"})


class AnmeldungForm(FlaskForm):
    """Anmeldeformular für Ausbilder zur Schülerzuordnung."""

    ausbilder_betrieb = StringField(
        "Ihr Firmenname:",
        filters=[normalize_whitespace],
        validators=[DataRequired(), NAME_LENGTH],
        render_kw={"placeholder": "Musterfirma"},
    )
    ausbilder_name = StringField(
        "Ihr Nachname:",
        filters=[normalize_whitespace],
        validators=[DataRequired(), NAME_LENGTH],
        render_kw={"placeholder": "Mustermann"},
    )
    ausbilder_vorname = StringField(
        "Ihr Vorname:",
        filters=[normalize_whitespace],
        validators=[DataRequired(), NAME_LENGTH],
        render_kw={"placeholder": "Max"},
    )
    ausbilder_email = EmailField(
        "Ihre Mailadresse:",
        filters=[normalize_whitespace],
        validators=email_validators(),
        render_kw={"placeholder": "max.mustermann@musterfirma.com"},
    )
    anzahl_schueler = SelectField(
        "Wieviele Schüler möchten Sie anmelden",
        choices=[("", "Bitte wählen...")] + [(str(i), str(i)) for i in range(1, 16)],
        validators=[DataRequired()],
        render_kw={"class": "form-select"},
    )
    submit = SubmitField(
        "Schüler eintragen",
        id="add_pupils",
        render_kw={"class": "btn btn-primary big"},
    )


class ConfigForm(FlaskForm):
    """Konfigurationsformular für Admin-Einstellungen, Kontakt und Mail-Server."""

    # Admin
    admin_login = StringField("Admin Login", validators=[Optional(), Length(min=3, max=100)])
    admin_password = PasswordField("Admin Passwort", validators=[Optional(), PASSWORD_LENGTH])

    # Ausbilder
    tss_password = PasswordField("Ausbilder Passwort", validators=[Optional(), PASSWORD_LENGTH])

    # Mail-Server
    mail_server = StringField("Mail Server", validators=[Optional(), NAME_LENGTH])
    mail_port = IntegerField("Mail Port", validators=[Optional(), NumberRange(min=1, max=65535)])
    mail_encryption = SelectField(
        "Verschlüsselung",
        choices=[
            ("none", "Keine Verschlüsselung (Port 25)"),
            ("tls", "STARTTLS (Empfohlen, z. B. Port 587)"),
            ("ssl", "SSL / Implicit TLS (z. B. Port 465)"),
        ],
        validators=[AnyOf(["none", "tls", "ssl"])],
        default="tls",
    )
    mail_username = StringField("Mail Benutzername", validators=[Optional(), NAME_LENGTH])
    mail_password = PasswordField("Mail Passwort", validators=[Optional(), PASSWORD_LENGTH])
    mail_default_sender = StringField("Standard Absender (E-Mail)", validators=[Optional(), EMAIL_LENGTH])

    # Sonstiges
    timetowait = IntegerField(
        "Wartezeit (Minuten)",
        validators=[Optional(), NumberRange(min=60, max=3600)],
    )
    submit = SubmitField("Einstellungen speichern")
