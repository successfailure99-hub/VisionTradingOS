"""
Vision Trading OS production bootstrap entry point.
"""

from __future__ import annotations

import signal
from threading import Event

from application.bootstrap import ApplicationBootstrap


def main() -> int:
    shutdown_requested = Event()
    lifecycle = None
    previous_handlers = {}

    def request_shutdown(signum, frame):
        shutdown_requested.set()

    for signal_name in ("SIGINT", "SIGTERM"):
        signum = getattr(signal, signal_name, None)
        if signum is None:
            continue
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, request_shutdown)

    try:
        lifecycle = ApplicationBootstrap().bootstrap()
        shutdown_requested.wait()
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception:
        return 1
    finally:
        if lifecycle is not None:
            try:
                lifecycle.stop()
            except Exception:
                pass
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
