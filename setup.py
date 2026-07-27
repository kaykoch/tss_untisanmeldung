#!/usr/bin/env python3

# ------------------------------------------------------------------------------
# Überprüft durch Claude 4
# ------------------------------------------------------------------------------

import os
import platform
import shutil
import subprocess
import sys


# --- KONFIGURATION ---
VENV_DIR = ".venv"
REQUIREMENTS_FILE = "requirements.txt"
MIN_PY_MAJOR = 3
MIN_PY_MINOR = 11


# --- FARBEN FÜR DIE AUSGABE ---
def info(msg):
    print(f"\033[1;34m[INFO]\033[0m {msg}")


def warn(msg):
    print(f"\033[1;33m[WARN]\033[0m {msg}")


def error(msg):
    print(f"\033[1;31m[ERROR]\033[0m {msg}")


def okay(msg):
    print(f"\033[1;32m[OK]\033[0m {msg}")


def check_python_version():
    """Prüft, ob die aktuelle Python-Version ausreicht (>= 3.11)."""
    info("Prüfe erforderliche Python-Version...")
    major = sys.version_info.major
    minor = sys.version_info.minor

    if major < MIN_PY_MAJOR or (major == MIN_PY_MAJOR and minor < MIN_PY_MINOR):
        error(f"Python >= {MIN_PY_MAJOR}.{MIN_PY_MINOR} erforderlich. Gefunden: {major}.{minor}")
        sys.exit(2)
    okay(f"Gefundene Python-Version: {major}.{minor}")


def check_www_data_user():
    """Prüft, ob der Systembenutzer 'www-data' existiert (nur auf Linux)."""
    if platform.system() != "Linux":
        warn("Kein Linux-System erkannt. Überspringe Prüfung für 'www-data'.")
        return

    info("Prüfe, ob Benutzer 'www-data' existiert...")
    try:
        import pwd

        pwd.getpwnam("www-data")
        okay("Benutzer 'www-data' existiert.")
    except KeyError:
        warn("Benutzer 'www-data' existiert nicht. Für Produktiveinsatz (systemd) erforderlich.")


def handle_venv():
    """Erstellt das virtuelle Environment, falls nicht vorhanden oder gewünscht."""
    if os.path.exists(VENV_DIR):
        warn(f"Venv-Ordner '{VENV_DIR}' existiert bereits.")
        yn = input("Soll das bestehende venv gelöscht und neu erstellt werden? [y/N]: ").strip().lower()
        if yn.startswith("y"):
            info(f"Lösche vorhandenes venv: {VENV_DIR}")
            shutil.rmtree(VENV_DIR)
        else:
            info("Verwende vorhandenes venv.")
            return

    info(f"Erstelle virtuelle Umgebung in '{VENV_DIR}'...")
    try:
        import venv

        venv.create(VENV_DIR, with_pip=True)
        okay("Virtuelle Umgebung erstellt.")
    except ImportError:
        # Fallback falls venv-Modul im OS-Python fehlt
        error("Das Python-Modul 'venv' ist nicht installiert.")
        warn("Bitte installiere es nach (z.B. sudo apt install python3-venv) und starte erneut.")
        sys.exit(2)


def create_env_file():
    """Erstellt eine sichere .env-Datei mit automatisch generierten Schlüsseln."""
    env_path = ".env"
    if os.path.exists(env_path):
        info(".env-Datei existiert bereits. Überspringe Generierung.")
        return

    info("Erstelle neue .env-Datei und generiere kryptografische Schlüssel...")

    # Da cryptography im globalen System vielleicht fehlt, nutzen wir secrets für Flask
    # und generieren den Fernet-Key händisch im passenden Format über Standard-Pakete.
    import base64
    import secrets

    flask_secret = secrets.token_hex(24)
    # Fernet benötigt exakt 32 kryptografisch sichere Bytes, Base64 kodiert
    fernet_bytes = secrets.token_bytes(32)
    encryption_key = base64.urlsafe_b64encode(fernet_bytes).decode()
    # 5MB als max. Upload sollte reichen
    max_length = 5 * 1024 * 1024

    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"SECRET_KEY={flask_secret}\n")
            f.write(f"ENCRYPTION_KEY={encryption_key}\n")
            f.write(f"MAX_CONTENT_LENGTH={max_length}\n")
            f.write("# Hier bei Bedarf weitere Variablen eintragen (z.B. MAIL_PASSWORD)\n")
        okay(".env-Datei wurde erfolgreich mit sicheren Keys generiert!")
    except OSError as e:
        error(f"Konnte .env-Datei nicht schreiben: {e}")


def install_requirements():
    """Aktiviert das venv im Subprozess und installiert die Pakete."""
    if not os.path.exists(REQUIREMENTS_FILE):
        warn(f"Datei '{REQUIREMENTS_FILE}' wurde nicht gefunden.")
        return

    info("Aktualisiere Core-Pakete und installiere Requirements im venv...")

    # Pfad zum Pip-Binary im venv bestimmen
    if platform.system() == "Windows":
        pip_cmd = os.path.join(VENV_DIR, "Scripts", "pip.exe")
    else:
        pip_cmd = os.path.join(VENV_DIR, "bin", "pip")

    try:
        # Pip upgraden
        subprocess.run([pip_cmd, "install", "--upgrade", "pip", "setuptools", "wheel"], check=True)
        # Requirements installieren
        subprocess.run([pip_cmd, "install", "-r", REQUIREMENTS_FILE], check=True)
        okay(f"Alle Pakete aus {REQUIREMENTS_FILE} wurden erfolgreich installiert.")
    except subprocess.CalledProcessError:
        error("Fehler bei der Paketinstallation im venv.")
        sys.exit(5)


def set_permissions():
    """Setzt die Ordnerberechtigungen auf www-data (nur auf Linux)."""
    if platform.system() != "Linux":
        return

    info("Setze Berechtigungen für das Verzeichnis auf www-data:www-data...")
    project_dir = os.getcwd()

    try:
        # Entspricht chown -R www-data:www-data
        subprocess.run(["chown", "-R", "www-data:www-data", project_dir], check=True)
        okay("Berechtigungen erfolgreich gesetzt.")
    except subprocess.CalledProcessError:
        error("Berechtigungen konnten nicht gesetzt werden. (Hast du das Skript mit sudo ausgeführt?)")
        sys.exit(1)


def print_usage_hints():
    """Gibt Hinweise zur Nutzung am Ende aus."""
    print("\n" + "=" * 60)
    okay("Setup abgeschlossen.")
    info("Um die virtuelle Umgebung zu aktivieren, führe aus:")
    print(f"\n  source {VENV_DIR}/bin/activate\n")

    print("Hinweis: Anwendung starten / stoppen mit startGunicorn.py")
    print("Verwendung von startGunicorn.py (NUR IM LOKALEN NETZ):")
    print("  - Starten (Standardverhalten): ./startGunicorn.py")
    print("  - Nur beenden (kein Neustart): ./startGunicorn.py kill")

    print()
    warn("=" * 60 + "\n")
    error("Für Produktiveinsatz unbedingt systemd nutzen --> README.md")
    warn("=" * 60 + "\n")


if __name__ == "__main__":
    check_python_version()
    check_www_data_user()
    handle_venv()
    create_env_file()
    install_requirements()
    set_permissions()
    print_usage_hints()
