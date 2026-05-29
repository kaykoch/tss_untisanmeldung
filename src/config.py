"""Config Datei - zu aktualisierende Daten

Alle notwendigen Daten müssen hier eingetragen werden.
Im Programm bitte keine Änderungen durchführen
"""

""" erlaubte Endungen für einen Upload von neuen Accounts
    Bsp.:
      ALLOWDEXTENSIONS = {"csv"}
"""
ALLOWD_EXTENSIONS = ["csv", "pdf"]


""" Liste mit möglichen Codecs
    Bsp.:
      CODECS = ["UTF-8", "ISO-8859-1"]
"""
CODECS = ["UTF-8", "ISO-8859-1"]


""" Texte, die auf den einzelnen Webseiten als Info angezwigt werden (HTML-Tags sind möglich)
"""
# Startseite der Anmeldung
text_index_1 = "<p>Bitte tragen Sie die Daten der verantwortlichen Person ein und  \
              wählen die Anzahl der Schüler aus, die sie dieser Mailadresse zuordnen wollen. \
              Geben Sie anschließend die Untis-Profilnamen der Azubis ein.<br>  \
              (Diese erhalten Sie von ihren Auszubildenden.) </p>\
              <p>Sollten Sie weitere Schüler dieser Mailadresse zuordnen wollen, \
              rufen Sie diese Seite später mit dem Link in der Bestätigungsmail auf.</p>"

text_index_2 = "Weitere Informationen finden Sie <a href='/static/info.pdf') target='_blank' >HIER</a>"

# Anzeigeseite der mit einer Mailadresse verknüpften Azubis
text_azubismitausbilder = "Für Ihren Betrieb sind die folgenden Schüler mit Ihrer Mailadresse verbunden.<br> \
                           Bitte überprüfen Sie ihre Namen."

# Oberer Text der Bestätigungsmail (Über: WICHTIG)
text_mail_1 = "Sie haben einen oder mehrere Azubis für WebUntis mit Ihrer EMail-Adresse verknüpft.<br>  \
               Bitte bestätigen Sie Ihre Mail-Adresse innerhalb von 2 Stunden, \
               da diese und alle Verknüpfungen sonst gelöscht werden.<br> \
               Diese BESTÄTIGUNG ist nur bei der ersten Eingabe notwendig."

# Unterer Text der Bestätigungsmail (Unter: WICHTIG)
text_mail_2 = "Mit den unten aufgeführten Links können Sie sich bis zum Ende der Anmeldezeit \
               alle Azubis anzeigen lassen, die mit Ihrer Mail-Adresse verknüpft sind und WEITERE AZUBIS eintragen, \
               ohne ihre Daten erneut eingeben zu müssen.<br>"

# ------------------------------------------------------------------------------
#   Ab hier nichts mehr ändern
# ------------------------------------------------------------------------------


INFOTEXTE = {
    "index_1": text_index_1,
    "index_2": text_index_2,
    "azubismitausbilder": text_azubismitausbilder,
    "mail_1": text_mail_1,
    "mail_2": text_mail_2,
}
