from io import BytesIO
import logging
from re import match as re_match
from smtplib import SMTPAuthenticationError, SMTPException
from time import sleep

from flask import flash, render_template, request
from flask_mail import Message
from markupsafe import Markup

from src.extensions import state


logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)
_EMAIL_REGEX = r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*$"
_MAIL_LIMIT = 30  # Maximale Anzahl Mails pro Versandaufruf
_MAIL_DELAY = 1  # Sekunden Pause zwischen Mails

_SUBJECT_UNTIS = "Ihr WebUntis-Zugang – Zugriff auf Fehlzeiten Ihrer Auszubildenden"
_SUBJECT_CONFIRM = "Bestätigung der Azubianmeldung für WebUntis an der TSS Bitburg"


def __send_mail(msg: Message) -> bool:
    """Sendet eine Flask-Mail-Message.

    Returns:
        True bei erfolgreichem Versand, sonst False.
    """
    try:
        print(state.app.config)
        print(msg.recipients)
        # state.mail.send(msg)
        logger.debug("Mail gesendet an: %s", msg.recipients)
        return True

    except SMTPAuthenticationError:
        logger.error("Mail-Fehler: Authentifizierung am SMTP-Server fehlgeschlagen.")
    except SMTPException as e:
        logger.error("Allgemeiner SMTP-Fehler beim Mailversand: %s", e)
    except Exception as e:
        logger.exception("Unerwarteter Fehler beim E-Mail-Versand: %s", e)

    return False


def __build_flash_result(success: bool, ok_msg: str, err_msg: str) -> tuple[str, str]:
    """Gibt ein (Nachricht, Kategorie)-Tuple zurück.

    Verwendet von: send_untisinfo_to_ausbilder, send_mail_to_ausbilder
    """
    return (ok_msg, "success") if success else (err_msg, "error")


def send_untisinfo_to_ausbilder(ausbilder_liste: list) -> None:
    """Sendet WebUntis-Zugangsinformationen an bis zu `_MAIL_LIMIT` Ausbilder.

    Args:
        ausbilder_liste: Liste von Ausbilder-Objekten.
    """
    for ausbilder in ausbilder_liste[:_MAIL_LIMIT]:
        html = render_template(
            "mail/mail_untis_ausbilder.html",
            server_url=f"https://{request.host}/",
            ausbilder=ausbilder,
        )
        msg = Message(subject=_SUBJECT_UNTIS, recipients=[ausbilder.ausbilder_email], html=html)
        sent = __send_mail(msg)

        recipient = f"{ausbilder.ausbilder_betrieb} ({ausbilder.ausbilder_email})"
        info, result = __build_flash_result(
            sent,
            ok_msg=f"OK: An {recipient} gesendet.<br>",
            err_msg=f"FEHLER: An {recipient} konnte nicht versandt werden.",
        )

        logger.info(info)
        flash(Markup(info), result)
        sleep(_MAIL_DELAY)


def send_mail_to_ausbilder(ausbilder) -> tuple[Markup, str]:
    """Sendet eine Bestätigungsmail an einen Ausbilder nach der Anmeldung.

    Args:
        ausbilder: Ausbilder-Objekt mit E-Mail und Betriebsdaten.

    Returns:
        Tuple (Markup-Nachricht, Kategorie).
    """
    html = render_template(
        "mail/mail_confirm_ausbilder.html",
        ausbilder=ausbilder,
        server_url=f"https://{request.host}/",
        kontaktperson=state.kontaktperson,
    )
    msg = Message(subject=_SUBJECT_CONFIRM, recipients=[ausbilder.ausbilder_email], html=html)
    sent = __send_mail(msg)

    if sent:
        logger.info(
            "Mail verschickt an: %s, %s (%s)",
            ausbilder.ausbilder_name,
            ausbilder.ausbilder_vorname,
            ausbilder.ausbilder_email,
        )

    return __build_flash_result(
        sent,
        ok_msg=(
            f"Die Mail wurde an {ausbilder.ausbilder_email} gesendet<br>"
            "Bitte bestätigen Sie Ihre Daten innerhalb von 2 Stunden"
        ),
        err_msg=f"Die Mail an {ausbilder.ausbilder_email} konnte nicht versandt werden.",
    )


def send_mail_to_kontaktperson(file_io: BytesIO, klasse: str) -> None:
    """Erstellt eine CSV-Datei für die Klasse und versendet sie per Mail an die Kontaktperson.

    Verwendet von: route_azubianzeige
    """
    recipients = [state.kontaktperson.mail]
    subject = "Bestätigung der Azubianmeldung für WebUntis an der TSS Bitburg"
    html = (
        f"Hallo {state.kontaktperson.name},<br>"
        f"im Anhang befindet sich die Datei mit Ausbildern für die Klasse: {klasse}."
    )
    msg = Message(subject=subject, recipients=recipients, html=html)
    msg.attach(
        filename=f"untis_ausbilder_{klasse}.csv",
        content_type="text/csv",
        data=file_io.getvalue(),
    )

    if __send_mail(msg):
        info = f"Die CSV-Datei der Klasse {klasse} wurde an {state.kontaktperson.komplett} versandt."
        logger.info("Mail mit Azubis (%s) verschickt an: %s", klasse, state.kontaktperson.komplett)
        flash(Markup(info), "success")
    else:
        flash(
            Markup(f"Die Mail an {state.kontaktperson.komplett} konnte nicht versandt werden."),
            "error",
        )


def _is_not_valid_mail(email: str) -> bool:
    """Gibt True zurück, wenn die E-Mail-Adresse NICHT valide ist."""
    return re_match(_EMAIL_REGEX, email) is None
