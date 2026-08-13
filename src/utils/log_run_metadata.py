"""
src/utils/log_run_metadata.py

Reusable helper for logging reproducibility metadata to a run log file.
Called at the start and end of every experiment entry point.
"""

import sys
import logging
import importlib.metadata
from datetime import datetime


def log_run_metadata(logger: logging.Logger, seeds: list, phase: str = "start") -> str:
    """
    Write reproducibility metadata to the provided logger.

    Parameters
    ----------
    logger : logging.Logger
        A configured logger that writes to the experiment's run.log.
    seeds : list
        The list of random seeds used in this experiment run.
    phase : str
        Either "start" or "end". Controls which metadata is logged.

    Returns
    -------
    str
        ISO-format timestamp string at the moment of the call.
    """
    timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    if phase == "start":
        logger.info("=" * 60)
        logger.info("EXPERIMENT RUN START")
        logger.info(f"Timestamp (UTC): {timestamp}")
        logger.info(f"Python version:  {sys.version}")

        packages = ["numpy", "pandas", "scipy", "statsmodels", "matplotlib"]
        for pkg in packages:
            try:
                version = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                version = "not installed"
            logger.info(f"  {pkg}: {version}")

        logger.info(f"Seeds: {seeds}")
        logger.info("=" * 60)

    elif phase == "end":
        logger.info("=" * 60)
        logger.info("EXPERIMENT RUN END")
        logger.info(f"Timestamp (UTC): {timestamp}")
        logger.info("=" * 60)

    return timestamp
