from cryptography.fernet import Fernet

from src.extensions import state


def get_decrypted_mail_password(mail_password: str) -> str:
    """Entschlüsselt das Mail-Passwort für den SMTP-Versand.

    Args:
        mail_password: Verschlüsseltes Passwort aus der Datenbank.

    Returns:
        Entschlüsseltes Passwort als String, oder "" bei fehlendem Key/Passwort.
    """
    secret_key = state.app.config.get("ENCRYPTION_KEY")
    if not secret_key or not mail_password:
        return ""
    decrypted = Fernet(secret_key.encode()).decrypt(mail_password.encode())
    return decrypted.decode()
