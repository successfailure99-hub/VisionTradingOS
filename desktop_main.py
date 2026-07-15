"""
Vision Trading OS desktop dashboard entry point.
"""

import os

from application.desktop_live_data import DesktopLiveDataConfigurationError, create_dashboard_application


def main() -> int:
    try:
        dashboard = create_dashboard_application(environ=os.environ)
    except DesktopLiveDataConfigurationError as exc:
        print(f"Desktop startup failed: {exc}")
        return 1
    return dashboard.run()


if __name__ == "__main__":
    raise SystemExit(main())
