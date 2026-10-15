"""FAPT-Guard: Forensic-Aware Predictive Threat Guard.

A research framework that predicts both the future cyberattack state and the
future digital-evidence state before deciding how to respond.
"""

__version__ = "0.1.0"

from fapt_guard.config import Config, load_config  # noqa: E402

__all__ = ["Config", "load_config", "__version__"]
