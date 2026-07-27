# Startoptionen für tss_untisanmeldung

Es gibt drei Möglichkeiten, die Anwendung zu starten.
Lies die Hinweise zu den Risiken, bevor du eine Variante wählst.

---

## Voraussetzungen

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

---

## Variante 1 — Direkt mit Python

    source .venv/bin/activate
    python untis.py

**Geeignet für:** Lokale Entwicklung, schnelle Tests.

> ⚠️ **Risiken:**
> - Läuft im Flask-Entwicklungsserver — **nicht produktionstauglich**
> - `debug=True` gibt Stacktraces im Browser aus
> - Kein automatischer Neustart bei Absturz
> - Kein Load-Balancing / mehrere Worker

---

## Variante 2 — Manueller Gunicorn-Start

    # Starten
    python deploy/startGunicorn.py

    # Stoppen
    python deploy/startGunicorn.py kill

**Geeignet für:** Tests auf dem Server ohne systemd.

> ⚠️ **Risiken:**
> - Läuft auf Port **8081** und ist unter `0.0.0.0` von außen erreichbar
> - Kein automatischer Neustart bei Absturz oder Serverneustart
> - Logs landen unter `/tmp/` — gehen bei Serverneustart verloren
> - Prozessverwaltung über PID-File `/tmp/gunicorn-untis-test.pid`

---

## Variante 3 — systemd (Empfohlen für Produktion)

### Einmalige Einrichtung

    sudo cp deploy/tss_untisanmeldung.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable tss_untisanmeldung

### Starten / Stoppen / Status

    sudo systemctl start tss_untisanmeldung
    sudo systemctl stop tss_untisanmeldung
    sudo systemctl status tss_untisanmeldung

### Logs

    sudo journalctl -u tss_untisanmeldung -f

**Geeignet für:** Dauerhafter Betrieb auf einem Linux-Server.

> ℹ️ **Hinweise:**
> - Läuft auf Port **8082** unter Benutzer `www-data`
> - Startet automatisch nach einem Serverneustart
> - Automatischer Neustart bei Absturz
> - Pfade in der `.service`-Datei ggf. anpassen

---

## Vergleich

|                       | Variante 1  | Variante 2  | Variante 3 |
|-----------------------|-------------|-------------|------------|
| Geeignet für          | Entwicklung | Servertest  | Produktion |
| Port                  | 5000        | 8081        | 8082       |
| Automatischer Neustart| ❌          | ❌          | ✅         |
| Mehrere Worker        | ❌          | ✅          | ✅         |
| Produktionstauglich   | ❌          | ⚠️          | ✅         |
| Externer Zugriff      | ❌          | ⚠️          | ✅         |
