# ------------------------------------------------------------------------------
# Überprüft durch Claude 4
# ------------------------------------------------------------------------------

from functools import wraps
import logging

from flask import Response, request
from werkzeug.security import check_password_hash

from src.extensions import state
from src.services.ausbilder_service import get_ausbilder_by_token


logger = logging.getLogger(__name__)

_AUSBILDER_USER = "tssbit"  # Fester Benutzername für TSS-Zugang (Ausbilder-Login)


def requires_auth(allowed_login_types: str | list | tuple | frozenset, allow_token_bypass: bool = False):
    """Dekorator-Fabrik: Schützt eine Route auf bestimmte Login-Typen.

    Args:
        allowed_login_types: Erlaubter Typ oder Liste von Typen ("admin", "tss").
        allow_token_bypass:  Wenn True, wird ein gültiges URL-Token als
                             Authentifizierung akzeptiert (kein Passwort nötig).
    """
    if not isinstance(allowed_login_types, (list, tuple, frozenset)):
        allowed_login_types = [allowed_login_types]

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):

            # Token-Bypass: nur wenn explizit erlaubt und Token gültig
            if allow_token_bypass:
                token = request.args.get("token")
                if token:
                    ausbilder = get_ausbilder_by_token(token)
                    if ausbilder is not None:
                        logger.info("Token-Bypass akzeptiert für: %s", token[:8] + "...")
                        return f(*args, **kwargs)

            # Normaler Basic-Auth-Flow
            auth = request.authorization
            if not auth:
                return _authenticate()

            # Erfolgreicher Login
            login_type = _check_auth_and_get_type(auth.username, auth.password)

            if login_type in allowed_login_types:
                return f(*args, **kwargs)

            # Fehlgeschlagener Login-Versuch
            xff = request.headers.get("X-Forwarded-For")
            client_ip = xff.split(",")[0].strip() if xff else request.remote_addr
            logger.warning("Fehlgeschlagener Login-Versuch: user=%s, ip=%s", auth.username, client_ip)
            return _authenticate()

        return decorated

    return decorator


def _check_auth_and_get_type(username: str, password: str) -> str | None:
    """Prüft Zugangsdaten gegen die app.config und gibt den Login-Typ zurück.

    Args:
        username: Benutzername aus der HTTP-Basic-Auth-Anfrage.
        password: Klartext-Passwort aus der HTTP-Basic-Auth-Anfrage.

    Returns:
        "admin" | "tss" bei Erfolg, None bei ungültigen Daten.
    """
    admin_login = state.app.config.get("ADMIN_LOGIN")
    admin_password_hash = state.app.config.get("ADMIN_PASSWORD")
    tss_password_hash = state.app.config.get("TSS_PASSWORD")

    if not admin_login or not admin_password_hash or not tss_password_hash:
        logger.warning("_check_auth_and_get_type: Passwort-Hashes nicht in app.config gefunden.")
        return None

    if username == admin_login and check_password_hash(admin_password_hash, password):
        return "admin"

    if username == _AUSBILDER_USER and check_password_hash(tss_password_hash, password):
        return "tss"

    return None


def _authenticate() -> Response:
    """Gibt eine 401-Response zurück, die den Browser zur Eingabe von Zugangsdaten auffordert."""
    return Response(
        "Login erforderlich",
        401,
        {"WWW-Authenticate": 'Basic realm="Login erforderlich"'},
    )
