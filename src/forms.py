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
from wtforms.validators import DataRequired, Email, NumberRange, Optional


class AusbilderAktionForm(FlaskForm):
    """_summary_

    Args:
        FlaskForm (_type_): _description_
    """

    ausbilder_email = HiddenField(
        "Email",
        validators=[DataRequired(), Email()],
        render_kw={"id": "form_email"},
    )
    action = HiddenField(
        "Action",
        validators=[DataRequired()],
        render_kw={"id": "form_action"},
    )


class FilehandlingAktionForm(FlaskForm):
    filename = HiddenField("Filename", validators=[DataRequired()])
    action = HiddenField("Action", validators=[DataRequired()])
    upload_file = FileField(
        "Datei auswählen",
        validators=[
            FileAllowed(["csv", "pdf"], "Nur CSV- und PDF-Dateien sind erlaubt!"),
        ],
    )


class AzubiAuswahlForm(FlaskForm):
    klassen = SelectField(
        "Welche Klasse soll angezeigt werden / wollen Sie herunterladen?",
        validators=[DataRequired(message="Bitte wählen Sie eine Klasse aus.")],
    )
    submit = SubmitField("Download", render_kw={"class": "btn btn-primary small"})


class AnmeldungForm(FlaskForm):
    ausbilder_betrieb = StringField(
        "Ihr Firmenname:", validators=[DataRequired()], render_kw={"placeholder": "Musterfirma"}
    )

    ausbilder_name = StringField("Ihr Nachname:", validators=[DataRequired()], render_kw={"placeholder": "Mustermann"})

    ausbilder_vorname = StringField("Ihr Vorname:", validators=[DataRequired()], render_kw={"placeholder": "Max"})

    ausbilder_email = EmailField(
        "Ihre Mailadresse:",
        validators=[
            DataRequired(message="Bitte geben Sie eine E-Mail-Adresse ein."),
            Email(message="Bitte geben Sie eine gültige E-Mail-Adresse ein."),
        ],
        render_kw={"placeholder": "max.mustermann@musterfirma.com"},
    )

    anzahl_schueler = SelectField(
        "Wieviele Schüler möchten Sie anmelden",
        choices=[("", "Bitte wählen...")] + [(str(i), str(i)) for i in range(1, 16)],
        validators=[DataRequired()],
    )

    submit = SubmitField("Schüler eintragen", id="add_pupils", render_kw={"class": "btn btn-primary"})


class ConfigForm(FlaskForm):
    # Admin
    admin_login = StringField("Admin Login", validators=[DataRequired()])
    admin_password = PasswordField("Admin Passwort", validators=[Optional()])

    # Kontakt
    kontakt_person_name = StringField("Kontaktperson Name")
    kontakt_person_mail = StringField("Kontaktperson E-Mail", validators=[Optional(), Email()])

    # Mail
    mail_server = StringField("Mail Server")
    mail_port = IntegerField("Mail Port", validators=[Optional(), NumberRange(min=1, max=65535)])
    mail_use_ssl = BooleanField("Nutze SSL")
    mail_use_tls = BooleanField("Nutze TLS")
    mail_username = StringField("Mail Benutzername")
    mail_password = PasswordField("Mail Passwort", validators=[Optional()])
    mail_default_sender = StringField("Standard Absender (E-Mail)")

    # Sonstiges
    timetowait = IntegerField("Wartezeit (Minuten)", validators=[Optional()])

    submit = SubmitField("Einstellungen speichern")
