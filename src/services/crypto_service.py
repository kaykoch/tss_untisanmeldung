# ------------------------------------------------------------------------------
# Überprüft durch Claude 4
# ------------------------------------------------------------------------------

import logging

from cryptography.fernet import Fernet, InvalidToken

from src.extensions import state


logger = logging.getLogger(__name__)


def get_decrypted_mail_password(mail_password: str | None) -> str:
    """Entschlüsselt das Mail-Passwort.

    Bei fehlendem Key/mail_password oder bei Fehlern wird "" zurückgegeben
    (Fehler werden geloggt).
    """
    if not mail_password:
        return ""

    app = getattr(state, "app", None)
    if app is None:
        logger.warning("App-Kontext nicht gesetzt: kann Mail-Passwort nicht entschlüsseln.")
        return ""

    secret_key = app.config.get("ENCRYPTION_KEY")
    if not secret_key:
        logger.warning("ENCRYPTION_KEY nicht gesetzt: kann Mail-Passwort nicht entschlüsseln.")
        return ""

    try:
        f = Fernet(secret_key.encode())
        decrypted = f.decrypt(mail_password.encode())
        return decrypted.decode()
    except InvalidToken:
        logger.exception("Mail-Passwort konnte nicht entschlüsselt werden: Ungültiges Token.")
        return ""
    except Exception:
        logger.exception("Fehler beim Entschlüsseln des Mail-Passworts.")
        return ""
