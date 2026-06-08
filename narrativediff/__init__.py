"""NARRATIVEDIFF - News bias & framing diff across many outlets per event.

A zero-dependency, standard-library-only engine that compares how different
news outlets cover the SAME event. It surfaces:

  * Bias / loaded language (intensity + direction) per outlet
  * Framing fingerprints (which sub-topics / angles each outlet emphasizes)
  * Selective omission (facts present in some outlets, missing in others)
  * Headline-vs-body sensationalism
  * Cross-outlet divergence ranking

Spirit of the Media-Bias-Group/MBIB project, but offline and deterministic.
"""
from .core import (
    Article,
    EventCorpus,
    OutletReport,
    DiffResult,
    analyze_event,
    load_corpus,
)

TOOL_NAME = "narrativediff"
TOOL_VERSION = "1.0.0"

__all__ = [
    "Article",
    "EventCorpus",
    "OutletReport",
    "DiffResult",
    "analyze_event",
    "load_corpus",
    "TOOL_NAME",
    "TOOL_VERSION",
]
