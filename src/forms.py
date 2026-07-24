# ------------------------------------------------------------------------------
#  FORMULARE
# ------------------------------------------------------------------------------

import re

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed
from wtforms import (
    BooleanField,
    EmailField,
    FileField,
    HiddenField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional


# ------------------------------------------------------------------------------
# Konstanten
# ------------------------------------------------------------------------------

EMAIL_VALIDATORS = [
    DataRequired(message="Bitte geben Sie eine E-Mail-Adresse ein."),
    Email(message="Bitte geben Sie eine gültige E-Mail-Adresse ein."),
    Length(max=255),
]

ALLOWED_UPLOAD_EXTENSIONS = ["csv", "pdf"]

PASSWORD_LENGTH = Length(min=4, max=15)
NAME_LENGTH = Length(max=255)
EMAIL_LENGTH = Length(max=320)


# ------------------------------------------------------------------------------
# Filter
# ------------------------------------------------------------------------------


def normalize_whitespace(value: str | None) -> str | None:
    """Bereinigt einen String: trimmt Ränder und reduziert Leerzeichen auf eines.

    Args:
        value: Eingabewert aus dem Formularfeld.

    Returns:
        Bereinigter String oder None, wenn der Eingabewert None war.
    """
    if value is None:
        return None
    return re.sub(r"\s+", " ", str(value).strip())


# ------------------------------------------------------------------------------
# Formulare
# ------------------------------------------------------------------------------


class AusbilderAktionForm(FlaskForm):
    """Aktionen auf der Ausbilderliste auslösen (z. B. Bestätigen, Löschen)."""

    ausbilder_email = HiddenField(
        "Email",
        filters=[normalize_whitespace],
        validators=EMAIL_VALIDATORS,
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
            FileAllowed(ALLOWED_UPLOAD_EXTENSIONS, "Nur CSV- und PDF-Dateien sind erlaubt!"),
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
        validators=EMAIL_VALIDATORS,
        render_kw={"placeholder": "max.mustermann@musterfirma.com"},
    )
    anzahl_schueler = SelectField(
        "Wieviele Schüler möchten Sie anmelden",
        choices=[("", "Bitte wählen...")] + [(str(i), str(i)) for i in range(1, 16)],
        filters=[normalize_whitespace],
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
    admin_login = StringField("Admin Login", validators=[Optional(), PASSWORD_LENGTH])
    admin_password = PasswordField("Admin Passwort", validators=[Optional(), PASSWORD_LENGTH])

    # Ausbilder
    tss_password = PasswordField("Ausbilder Passwort", validators=[Optional(), PASSWORD_LENGTH])

    # Mail-Server
    mail_server = StringField("Mail Server", validators=[Optional(), NAME_LENGTH])
    mail_port = IntegerField("Mail Port", validators=[Optional(), NumberRange(min=1, max=65535)])
    mail_use_ssl = BooleanField("Nutze SSL", validators=[Optional()])
    mail_use_tls = BooleanField("Nutze TLS", validators=[Optional()])
    mail_username = StringField("Mail Benutzername", validators=[Optional(), NAME_LENGTH])
    mail_password = PasswordField("Mail Passwort", validators=[Optional(), NAME_LENGTH])
    mail_default_sender = StringField("Standard Absender (E-Mail)", validators=[Optional(), EMAIL_LENGTH])

    # Sonstiges
    timetowait = IntegerField(
        "Wartezeit (Minuten)",
        validators=[Optional(), NumberRange(min=60, max=3600)],
    )
    submit = SubmitField("Einstellungen speichern")
