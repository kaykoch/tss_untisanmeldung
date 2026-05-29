#!/usr/bin/python3
import os
import signal
import subprocess
import time

# --- Konfiguration ---
APP_NAME = "untis"
APP_DIR = os.path.abspath(os.path.dirname(__file__))

VENV_DIR = os.path.join(APP_DIR, ".venv")
BIND_ADDRESS = "0.0.0.0:8081"
WORKERS = 3

# Pfad zum Gunicorn-Executable im venv
GUNICORN_BIN = os.path.join(VENV_DIR, "bin", "gunicorn")

print(f"--- Starte Deployment für {APP_NAME} ---")

# 1. In das Projektverzeichnis wechseln
os.chdir(APP_DIR)

# 2. Bestehenden Gunicorn-Prozess finden und beenden
try:
    # pgrep liefert die PIDs als Byte-String
    pgrep_output = subprocess.check_output(["pgrep", "-f", f"gunicorn.*{APP_NAME}"])
    #pgrep_output = subprocess.check_output(["pgrep", "-f", f"gunicorn"])
    pids = pgrep_output.decode().strip().split("\n")

    for pid in pids:
        print(f"Stoppe Gunicorn (PID: {pid})...")
        os.kill(int(pid), signal.SIGKILL)

    time.sleep(2)
except subprocess.CalledProcessError:
    # pgrep gibt einen Fehlercode zurück, wenn nichts gefunden wird
    print("Kein laufender Gunicorn-Prozess gefunden.")

# 3. & 4. Gunicorn im Hintergrund neu starten
# Wir nutzen den absoluten Pfad aus dem venv, was das manuelle "source activate" ersetzt
print("Starte Gunicorn neu...")

cmd = [GUNICORN_BIN, "--workers", str(WORKERS), "--bind", BIND_ADDRESS, "--daemon", f"{APP_NAME}:app"]
try:
    subprocess.run(cmd, check=True)
    print("--- Neustart erfolgreich! ---")
except subprocess.CalledProcessError as e:
    print(f"Fehler beim Starten von Gunicorn: {e}")
