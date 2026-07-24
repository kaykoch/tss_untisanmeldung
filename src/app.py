# ------------------------------------------------------------------------------
# Überprüft durch Claude 4
# ------------------------------------------------------------------------------

import locale
import logging
from pathlib import Path

from flask import Flask
from sqlalchemy.exc import SQLAlchemyError

from src.config import ProductionConfig
from src.extensions import state
from src.routes import register_routes
from src.services.config_service import load_defaults


# ------------------------------------------------------------------------------
# Konstanten
# ------------------------------------------------------------------------------

_SEPARATOR = "-" * 50

INFOFILE = "info.pdf"
PROTOTYPE_AZUBI = "prototyp_azubis.csv"
PROTOTYPE_AUSBILDER = "prototyp_ausbilder.csv"
TOMLFILE = "texts.toml"


logger = logging.getLogger(__name__)


def create_app(config_object=ProductionConfig) -> Flask:
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
    _setup_logging()
    app = Flask(__name__)
    app.config.from_object(config_object)
    state.db.init_app(app)

    with app.app_context():
        _bootstrap(app)

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
            tomlfile=TOMLFILE,
            prototypeazubi=PROTOTYPE_AZUBI,
            prototypeausbilder=PROTOTYPE_AUSBILDER,
        )
        _init_db()
        load_defaults()
        state.mail.init_app(app)
    except Exception as e:
        logger.exception("Fehler bei der App-Initialisierung: %s", e)
        raise


def _init_db() -> None:
    """Initialisiert die SQLite-Datenbank beim App-Start.

    Erstellt alle Tabellen, legt einen Standard-ConfigSetting-Eintrag an
    und befüllt die Berater-Tabelle mit Beispieldaten, falls sie leer ist.
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

    except SQLAlchemyError:
        logger.exception("Fehler beim Erstellen der Datenbanktabellen")
        raise
    except Exception:
        logger.exception("Fehler beim Erstellen der Datenbanktabellen")
        raise


def _seed_defaults(models) -> None:
    """Legt Standard-Datenbankeinträge an, falls die Tabellen noch leer sind.

    Args:
        models: Das src.models-Modul (nach dem Import in _init_db).
    """
    stmt = state.db.select(models.ConfigSetting).limit(1)
    if not state.db.session.execute(stmt).scalar_one_or_none():
        state.db.session.add(models.ConfigSetting())


def _setup_logging() -> None:
    logging.basicConfig(
        filename=state.logfile,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )
