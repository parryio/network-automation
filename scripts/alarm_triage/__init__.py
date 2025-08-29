"""Alarm Triage package.

Provides read-only, offline-capable triage utilities used by CI and demos.

Public helper functions (imported in tests):
    triage_one: run single alarm triage
    triage_batch: run batch triage over a glob
"""

from .triage import triage_one, triage_batch  # noqa: F401
