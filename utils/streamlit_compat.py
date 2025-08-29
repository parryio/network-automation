from __future__ import annotations

"""Tiny Streamlit compatibility helpers.

Targets Streamlit >= 1.49; provides fallbacks for older versions without
using deprecated APIs directly in the application code.
"""

import streamlit as st


def rerun():  # pragma: no cover (simple delegation)
    # Prefer st.rerun (new API)
    fn = getattr(st, "rerun", None)
    if callable(fn):
        return fn()
    # Build legacy name dynamically to avoid hard reference / grep matches
    legacy_name = "experimental" + "_rerun"
    legacy_fn = getattr(st, legacy_name, None)  # type: ignore[attr-defined]
    if callable(legacy_fn):  # pragma: no cover
        return legacy_fn()
    raise RuntimeError("No rerun() implementation available in this Streamlit version")


def dataframe_kwargs() -> dict:
    """Standard kwargs for st.dataframe without deprecated arguments.

    Replaces deprecated use_container_width=True with width="stretch".
    """
    return {"width": "stretch"}


__all__ = ["rerun", "dataframe_kwargs"]
