"""
Pytest configuration for robot tests.

Forces process exit after test session completes to work around
photonlibpy's TimeSyncServer creating non-daemon threads that
prevent the process from exiting cleanly on Windows CI.
"""
import atexit
import os
import sys

_exit_code = 0


def pytest_sessionfinish(session, exitstatus):
    global _exit_code
    _exit_code = exitstatus


@atexit.register
def _force_exit():
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_code)
