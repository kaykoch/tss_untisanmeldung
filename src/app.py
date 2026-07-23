# ------------------------------------------------------------------------------
#  APP-FACTORY
# ------------------------------------------------------------------------------

import locale
import logging
from pathlib import Path

from flask import Flask
from sqlalchemy.exc import SQLAlchemyError

from src.config import BaseConfig
from src.extensions import state
from src.routes import register_routes
from src.services.config_service import load_defaults


logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Konstanten
# ------------------------------------------------------------------------------

_SEPARATOR = "-" * 50

INFOFILE = "info.pdf"
PROTOTYPE_AZUBI = "prototyp_azubis.csv"
PROTOTYPE_AUSBILDER = "prototyp_ausbilder.csv"


# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
logging.basicConfig(
    filename=state.logfile,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    encoding="utf-8",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def create_app(config_object=BaseConfig) -> Flask:
    """Erstellt und konfiguriert die Flask-Applikation (App-Factory-Pattern).

    Ablauf:
        1. Flask-App erstellen und Basiskonfiguration laden.
        2. Datenbank-Extension initialisieren.
        3. Im App-Context: DB anlegen, Konfiguration aus DB laden, Mail binden.
        4. Blueprints registrieren.

    Args:
        config_object: Konfigurationsklasse (Standard: BaseConfig).

    Returns:
        Fertig konfigurierte Flask-App.
    """
    app = Flask(__name__)
    app.config.from_object(config_object)
    state.db.init_app(app)

    with app.app_context():
        _bootstrap(app)

    # _register_blueprints(app)
    register_routes(app)

    logger.info("%s", _SEPARATOR)
    logger.info("  --> !! App: Untisanmeldung wurde erfolgreich gestartet !!")
    logger.info("%s", _SEPARATOR)

    return app


def _bootstrap(app: Flask) -> None:
    """Führt alle Initialisierungsschritte innerhalb des App-Contexts aus.

    Args:
        app: Die laufende Flask-App.
    """
    try:
        logger.info("%s", _SEPARATOR)
        state.set_data(
            app,
            infofile=INFOFILE,
            prototypeazubi=PROTOTYPE_AZUBI,
            prototypeausbilder=PROTOTYPE_AUSBILDER,
        )
        _init_db()
        load_defaults()
        state.mail.init_app(app)
    except Exception as e:
        logger.exception("Fehler bei der App-Initialisierung: %s", e)


def _init_db() -> None:
    """Initialisiert die SQLite-Datenbank beim App-Start.

    Erstellt alle Tabellen, legt einen Standard-ConfigSetting-Eintrag an
    und befüllt die Berater-Tabelle mit Beispieldaten, falls sie leer ist.

    Args:
        state: Appstate-Objekt mit db, app und weiteren Laufzeit-Variablen.
    """
    try:
        Path(state.app.instance_path).mkdir(parents=True, exist_ok=True)

        # Import hier, damit Modelle registriert sind, bevor create_all() aufgerufen wird
        import src.models  # noqa: F401

        # Locale für Datumsformatierung setzen (Fallback auf C.UTF-8)
        locale.setlocale(locale.LC_TIME, "C.UTF-8")

        state.db.create_all()

        _seed_defaults(src.models)
        state.db.session.commit()

        logger.info("Datenbanktabellen erstellt/überprüft.")

    except SQLAlchemyError as e:
        logger.exception("Fehler beim Erstellen der Datenbanktabellen: %s", e)
        raise
    except Exception as e:
        logger.exception("_init_db -> Fehler bei der Datenbankinitialisierung: %s", e)


def _seed_defaults(models) -> None:
    """Legt Standard-Datenbankeinträge an, falls die Tabellen noch leer sind.

    Args:
        models: Das src.models-Modul (nach dem Import in _init_db).
    """
    if not models.ConfigSetting.query.first():
        state.db.session.add(models.ConfigSetting())


app = create_app(BaseConfig)
