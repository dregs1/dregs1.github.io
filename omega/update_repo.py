#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# *
# *  Copyright (C) 2012-2013 Garrett Brown
# *  Copyright (C) 2010      j48antialias
# *
# *  This Program is free software; you can redistribute it and/or modify
# *  it under the terms of the GNU General Public License as published by
# *  the Free Software Foundation; either version 2, or (at your option)
# *  any later version.
# *
# *  This Program is distributed in the hope that it will be useful,
# *  but WITHOUT ANY WARRANTY; without even the implied warranty of
# *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *  GNU General Public License for more details.
# *
# *  You should have received a copy of the GNU General Public License
# *  along with XBMC; see the file COPYING.  If not, write to
# *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *  http://www.gnu.org/copyleft/gpl.html
# *
# *  Based on code by j48antialias:
# *  https://anarchintosh-projects.googlecode.com/files/addons_xml_generator.py

"""
addons.xml generator – bereinigte Version
"""

import os
import sys
import hashlib

# Pfade festlegen
dir_path = os.path.dirname(os.path.realpath(__file__))
addonsxml_file = os.path.join(dir_path, "addons.xml")
addons_md5 = os.path.join(dir_path, "addons.xml.md5")

def u(x):
    return x  # Für Python 3 keine Umwandlung nötig

class Generator:
    """
    Generiert eine neue addons.xml-Datei aus allen addon.xml-Dateien im Ordner
    und erstellt eine passende MD5-Hashdatei dazu.
    """

    def __init__(self):
        self._generate_addons_file()
        self._generate_md5_file()
        print("✔ Fertig: addons.xml und addons.xml.md5 wurden aktualisiert.")

    def _generate_addons_file(self):
        addons = os.listdir(dir_path)
        addons_xml = u('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n')

        for addon in addons:
            addon_path = os.path.join(dir_path, addon)
            try:
                if (not os.path.isdir(addon_path) or addon.endswith(".svn") or addon.endswith(".git")):
                    continue

                addon_xml_path = os.path.join(addon_path, "addon.xml")
                with open(addon_xml_path, "r", encoding="utf-8") as f:
                    xml_lines = f.read().splitlines()

                addon_xml = ""
                for line in xml_lines:
                    if "<?xml" in line:
                        continue
                    addon_xml += line.rstrip() + "\n"

                addons_xml += addon_xml.rstrip() + "\n\n"

            except Exception as e:
                print(f"⚠ Ausschluss von {addon_path} wegen Fehler: {e}")

        addons_xml = addons_xml.strip() + u("\n</addons>\n")
        self._save_file(addons_xml.encode("utf-8"), file=addonsxml_file)

    def _generate_md5_file(self):
        try:
            with open(addonsxml_file, "r", encoding="utf-8") as f:
                content = f.read().encode("utf-8")
            m = hashlib.md5(content).hexdigest()
            self._save_file(m.encode("utf-8"), file=addons_md5)
        except Exception as e:
            print(f"❌ Fehler beim Erstellen von addons.xml.md5: {e}")

    def _save_file(self, data, file):
        try:
            with open(file, "wb") as f:
                f.write(data)
        except Exception as e:
            print(f"❌ Fehler beim Speichern von {file}: {e}")

if __name__ == "__main__":
    Generator()
