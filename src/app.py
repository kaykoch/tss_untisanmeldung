import logging

from flask import Flask

from src.config import BaseConfig
from src.extensions import state
from src.helpies import _init_db, _update_app


logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Konstanten
# ------------------------------------------------------------------------------

SEPARATOR = "-" * 50

INFOFILE = "info.pdf"
PROTOTYPE_AZUBI = "prototyp_azubis.csv"
PROTOTYPE_AUSBILDER = "prototyp_ausbilder.csv"

URL_PREFIX_MAIN = ""
URL_PREFIX_ADMIN = "/admin"


# ------------------------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------------------------


def _register_blueprints(app: Flask) -> None:
    """Registriert alle Blueprints an der Flask-App.

    Blueprints werden erst hier importiert, um zirkuläre Imports zu vermeiden.
    """
    from src.routes import bp as main_bp
    from src.routes_admin import bp as admin_bp

    app.register_blueprint(main_bp, url_prefix=URL_PREFIX_MAIN)
    app.register_blueprint(admin_bp, url_prefix=URL_PREFIX_ADMIN)


def _init_state(app: Flask) -> None:
    """Setzt alle applikationsweiten Zustände und initialisiert Datenbank und Mail.

    Reihenfolge ist wichtig:
    1. state.set_data  – Pfade und App-Referenz setzen
    2. _init_db        – DB erstellen/prüfen, Config-Defaults schreiben
    3. _update_app     – Config aus DB laden (Mail-Zugangsdaten etc.)
    4. mail.init_app   – Mail erst nach _update_app binden, da Zugangsdaten benötigt
    """
    state.set_data(
        app,
        infofile=INFOFILE,
        prototypeazubi=PROTOTYPE_AZUBI,
        prototypeausbilder=PROTOTYPE_AUSBILDER,
    )
    _init_db(state)
    _update_app()
    state.mail.init_app(app)


# ------------------------------------------------------------------------------
# App-Factory
# ------------------------------------------------------------------------------


def create_app(config_object=BaseConfig) -> Flask:
    """Erstellt und konfiguriert die Flask-App (App-Factory-Pattern).

    Args:
        config_object: Konfigurationsklasse, Standard ist BaseConfig.

    Returns:
        Fertig konfigurierte Flask-App.
    """
    app = Flask(__name__)
    app.config.from_object(config_object)
    state.db.init_app(app)

    with app.app_context():
        logger.info(SEPARATOR)
        try:
            _init_state(app)
        except Exception:
            logger.exception("Fehler bei der App-Initialisierung")
            raise  # Fehler nach oben weitergeben – App nicht halbfertig starten

    _register_blueprints(app)

    logger.info("App: Azubizuordnung wurde erfolgreich gestartet")
    logger.info(SEPARATOR)

    return app


app = create_app(BaseConfig)
