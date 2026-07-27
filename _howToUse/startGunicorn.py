#!/usr/bin/python3
import os
import signal
import subprocess
import sys
import time


# --- Konfiguration ---
APP_NAME = "untis"
APP_DIR = os.path.abspath(os.path.dirname(__file__))
PID_FILE = f"/tmp/gunicorn-{APP_NAME}.pid"

VENV_DIR = os.path.join(APP_DIR, ".venv")
BIND_ADDRESS = "0.0.0.0:8081"
WORKERS = 3

# Pfad zum Gunicorn-Executable im venv
GUNICORN_BIN = os.path.join(VENV_DIR, "bin", "gunicorn")

# 1. In das Projektverzeichnis wechseln
os.chdir(APP_DIR)


def stop():
    print("Stoppe Gunicorn ...")
    if os.path.exists(PID_FILE):
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        print(f"Sende SIGTERM an PID {pid} ...")
        os.kill(pid, signal.SIGTERM)
        time.sleep(2)
        print("Gunicorn gestoppt.")
    else:
        print("Kein laufender Gunicorn-Prozess gefunden (kein PID-File).")


def start():
    print("Starte Gunicorn ...")

    cmd = [
        GUNICORN_BIN,
        "--pid",
        PID_FILE,
        "--workers",
        str(WORKERS),
        "--bind",
        BIND_ADDRESS,
        "--daemon",
        f"{APP_NAME}:app",
    ]

    try:
        subprocess.run(cmd, check=True)
        print("--- Start erfolgreich! ---")
    except subprocess.CalledProcessError as e:
        print(f"Fehler beim Starten von Gunicorn: {e}")


# --- Einstiegspunkt ---
if __name__ == "__main__":
    print(f"--- Starte Deployment für {APP_NAME} ---")
    command = sys.argv[1] if len(sys.argv) > 1 else None

    if command == "kill":
        stop()
    elif command is None:
        stop()
        start()
    else:
        print(f"Unbekannter Parameter: '{command}'")
        print("Verwendung: python gunicorn.py [kill]")
        sys.exit(1)
