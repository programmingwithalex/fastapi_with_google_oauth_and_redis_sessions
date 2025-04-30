import logging
import sys


def setup_logging(level: str = "WARNING") -> None:
    """
    Configure root logger with a StreamHandler to stdout,
    a simple formatter, and the given log level.
    """
    # parse level
    try:
        log_level = getattr(logging, level.upper())
    except AttributeError:
        log_level = logging.WARNING

    # clear existing handlers
    root = logging.getLogger()
    root.setLevel(log_level)
    for h in list(root.handlers):
        root.removeHandler(h)

    # create new handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    fmt = "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    handler.setFormatter(logging.Formatter(fmt))

    # attach
    root.addHandler(handler)
