"""Bridge Python logging -> wpilib DataLogManager.

Call ``setup_logging()`` once at robot init to:
  1. Forward all Python ``logging`` output into .wpilog files
  2. Create a persistent NT entry at ``/robot/logLevel`` that allows
     the dashboard to change the log level at runtime

Accepted level strings (case-insensitive): debug, info, warn, warning,
error, critical, fatal, off.  WPILib-style k-prefixed names (kDebug,
kInfo, etc.) are also accepted.
"""

import logging

import ntcore
import wpilib


class _WPILogHandler(logging.Handler):
    """Forwards Python log records into the wpilog 'messages' entry."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            wpilib.DataLogManager.log(msg)
        except Exception:
            self.handleError(record)


# Normalized string -> Python logging level
_LOG_LEVEL_MAP: dict[str, int] = {
    "debug": logging.DEBUG,
    "kdebug": logging.DEBUG,
    "info": logging.INFO,
    "kinfo": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "kwarning": logging.WARNING,
    "error": logging.ERROR,
    "kerror": logging.ERROR,
    "critical": logging.CRITICAL,
    "kcritical": logging.CRITICAL,
    "fatal": logging.CRITICAL,
    "off": logging.CRITICAL + 10,
    "koff": logging.CRITICAL + 10,
}

# References kept alive to prevent GC of NT subscribers/publishers
_nt_refs: list = []


def _on_log_level_changed(event: ntcore.Event) -> None:
    """NT listener callback — updates root logger level."""
    value = event.data.value.getString()
    level = _LOG_LEVEL_MAP.get(value.strip().lower())
    if level is not None:
        logging.getLogger().setLevel(level)
        logging.info("Log level changed to %s (%d)", value.strip(), level)


def setup_logging(default_level: int = logging.INFO) -> None:
    """Initialize the Python logging -> wpilog bridge.

    - Attaches a handler to the root logger that forwards all records
      to ``DataLogManager.log()``.
    - Sets the root logger to *default_level*.
    - Creates a persistent NT string entry at ``/robot/logLevel``
      with a listener that updates the root level on change.

    Safe to call once at robot init.  Calling multiple times will add
    duplicate handlers — avoid that.
    """
    # Attach wpilog handler to root logger
    handler = _WPILogHandler()
    handler.setFormatter(logging.Formatter(
        "%(name)s [%(levelname)s] %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(default_level)

    # NT-controlled log level (persistent, callback-driven)
    inst = ntcore.NetworkTableInstance.getDefault()
    topic = inst.getStringTopic("/robot/logLevel")

    publisher = topic.publish(
        ntcore.PubSubOptions(keepDuplicates=False))
    publisher.setDefault("INFO")
    inst.getTable("/robot").getEntry("logLevel").setPersistent()

    subscriber = topic.subscribe("INFO")
    inst.addListener(
        subscriber,
        ntcore.EventFlags.kValueRemote | ntcore.EventFlags.kImmediate,
        _on_log_level_changed,
    )

    # Prevent GC from collecting the publisher/subscriber
    _nt_refs.extend([publisher, subscriber])
