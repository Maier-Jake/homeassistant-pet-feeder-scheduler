"""Make the integration's HA-free modules importable without Home Assistant.

Importing ``custom_components.pet_feeder_scheduler`` normally runs its
``__init__.py``, which needs Home Assistant installed. ``schedule.py`` and
``zigbee.py`` don't need it, so this registers an empty package object for the
integration folder. Tests can then import those two modules without running
``__init__.py``.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

PACKAGE = "pet_feeder_scheduler"
PACKAGE_DIR = Path(__file__).parent.parent / "custom_components" / PACKAGE

if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(PACKAGE_DIR)]
    sys.modules[PACKAGE] = package
