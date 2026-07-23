from functools import wraps
import logging

from flask import Response, request
from werkzeug.security import check_password_hash

from src.extensions import state
from src.models import ConfigSetting
from src.services.ausbilder_service import get_ausbilder_by_token


logger = logging.getLogger(__name__)

_AUSBILDER_USER = "tssbit"


def requires_auth(allowed_login_types: str | list | tuple, allow_token_bypass: bool = False):
    """Dekorator-Fabrik: Schützt eine Route auf bestimmte Login-Typen.

    Args:
        allowed_login_types: Erlaubter Typ oder Liste von Typen ("admin", "tss").
        allow_token_bypass:  Wenn True, wird ein gültiges URL-Token als
                             Authentifizierung akzeptiert (kein Passwort nötig).
    """
    if not isinstance(allowed_login_types, (list, tuple)):
        allowed_login_types = [allowed_login_types]

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):

            # Token-Bypass: nur wenn explizit erlaubt und Token gültig
            if allow_token_bypass:
                token = request.args.get("token")
                if token and get_ausbilder_by_token(token) is not None:
                    return f(*args, **kwargs)

            # Normaler Basic-Auth-Flow
            auth = request.authorization
            if not auth:
                return __authenticate()

            login_type = __check_auth_and_get_type(auth.username, auth.password)
            if login_type in allowed_login_types:
                return f(*args, **kwargs)

            return __authenticate()

        return decorated

    return decorator


def __check_auth_and_get_type(username: str, password: str) -> str | None:
    """Prüft Zugangsdaten gegen die Datenbank und gibt den Login-Typ zurück.

    Args:
        username: Benutzername aus der HTTP-Basic-Auth-Anfrage.
        password: Klartext-Passwort aus der HTTP-Basic-Auth-Anfrage.

    Returns:
        "admin" | "tss" bei Erfolg, None bei ungültigen Daten.
    """
    config = state.db.session.execute(state.db.select(ConfigSetting)).scalars().first()

    if not config:
        return None

    if username == config.admin_login and check_password_hash(config.admin_password, password):
        return "admin"

    if username == _AUSBILDER_USER and check_password_hash(config.tss_password, password):
        return "tss"

    return None


def __authenticate() -> Response:
    """Gibt eine 401-Response zurück, die den Browser zur Eingabe von Zugangsdaten auffordert."""
    return Response(
        "Login erforderlich",
        401,
        {"WWW-Authenticate": 'Basic realm="Login erforderlich"'},
    )
