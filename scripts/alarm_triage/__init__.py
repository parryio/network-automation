"""Alarm Triage package.

Provides read-only, offline-capable triage utilities used by CI and demos.

Public helper functions (imported in tests):
    process_alarm: run single alarm triage
    process_batch: run batch triage over a glob
"""

from .triage import process_alarm  # noqa: F401
from .batch import process_batch  # noqa: F401
