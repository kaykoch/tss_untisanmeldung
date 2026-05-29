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


class AusbilderAktionForm(FlaskForm):
    """Aktionen auf der Ausbilderliste auslösen."""

    ausbilder_email = HiddenField(
        "Email",
        validators=[DataRequired(), Email(message="Bitte geben Sie eine gültige E-Mail-Adresse ein.")],
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
    action = HiddenField(
        "Action",
        validators=[DataRequired()],
    )
    upload_file = FileField(
        "Datei auswählen",
        validators=[
            Optional(),
            FileAllowed(["csv", "pdf"], "Nur CSV- und PDF-Dateien sind erlaubt!"),
        ],
        render_kw={"accept": ".csv,.pdf"},
    )


class AzubiAuswahlForm(FlaskForm):
    """Klasse auswählen für Anzeige/Download."""

    klassen = SelectField(
        "Welche Klasse soll angezeigt werden / wollen Sie herunterladen?",
        validators=[
            DataRequired(message="Bitte wählen Sie eine Klasse aus."),
        ],
        choices=[],
        render_kw={"class": "form-select"},
    )
    submit = SubmitField(
        "Download",
        render_kw={"class": "btn btn-primary midi"},
    )


class AnmeldungForm(FlaskForm):
    ausbilder_betrieb = StringField(
        "Ihr Firmenname:",
        validators=[DataRequired(), Length(max=255)],
        render_kw={"placeholder": "Musterfirma"},
    )

    ausbilder_name = StringField(
        "Ihr Nachname:",
        validators=[DataRequired(), Length(max=255)],
        render_kw={"placeholder": "Mustermann"},
    )

    ausbilder_vorname = StringField(
        "Ihr Vorname:",
        validators=[DataRequired(), Length(max=255)],
        render_kw={"placeholder": "Max"},
    )

    ausbilder_email = EmailField(
        "Ihre Mailadresse:",
        validators=[
            DataRequired(message="Bitte geben Sie eine E-Mail-Adresse ein."),
            Email(message="Bitte geben Sie eine gültige E-Mail-Adresse ein."),
            Length(max=255),
        ],
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
    # Admin
    admin_login = StringField(
        "Admin Login",
        validators=[DataRequired(), Length(max=150)],
    )
    admin_password = PasswordField(
        "Admin Passwort",
        validators=[Optional()],
    )

    # Kontakt
    kontakt_person_name = StringField(
        "Kontaktperson Name",
        validators=[Optional(), Length(max=255)],
    )
    kontakt_person_mail = StringField(
        "Kontaktperson E-Mail",
        validators=[
            Optional(),
            Email(message="Bitte geben Sie eine gültige E-Mail-Adresse ein."),
            Length(max=320),
        ],
    )

    # Mail
    mail_server = StringField("Mail Server", validators=[Optional(), Length(max=255)])
    mail_port = IntegerField("Mail Port", validators=[Optional(), NumberRange(min=1, max=65535)])
    mail_use_ssl = BooleanField("Nutze SSL", validators=[Optional()])
    mail_use_tls = BooleanField("Nutze TLS", validators=[Optional()])
    mail_username = StringField("Mail Benutzername", validators=[Optional(), Length(max=255)])
    mail_password = PasswordField("Mail Passwort", validators=[Optional()])
    mail_default_sender = StringField("Standard Absender (E-Mail)", validators=[Optional(), Length(max=320)])

    # Sonstiges
    timetowait = IntegerField("Wartezeit (Minuten)", validators=[Optional(), NumberRange(min=0, max=3600)])

    submit = SubmitField("Einstellungen speichern")
