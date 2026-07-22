#!./.venv/bin/python3
"""
* Copyright (C) 2026  [Kay Koch]
*
* This program is free software: you can redistribute it and/or modify
* it under the terms of the GNU General Public License as published by
* the Free Software Foundation, either version 3 of the License, or
* (at your option) any later version.
*
* This program is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
* GNU General Public License for more details.
*
* You should have received a copy of the GNU General Public License
* along with this program.  If not, see <https://www.gnu.org/licenses/>.
*
"""

import logging
from pathlib import Path


__author__ = "Kay Koch"
__copyright__ = "Copyright 2026, TSS-Bitburg"
__credits__ = ["Gemini"]
__license__ = "GPL"
__version__ = "2.6.0"
__maintainer__ = "Kay Koch"
__email__ = "koch@tssbit.de"
__status__ = "Production"

logger = logging.getLogger(__name__)

# Logging definieren
logging.basicConfig(
    filename=Path(__file__).resolve().parent / "src/data/logfile.log",
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    encoding="utf-8",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ------------------------------------------------------------------------------

from src.app import app  # noqa: E402


if __name__ == "__main__":
    app.run(debug=True)
