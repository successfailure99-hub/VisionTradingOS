"""
Vision Trading OS desktop dashboard entry point.
"""

from application import ApplicationBootstrap
from dashboard.application import DashboardApplication


def main() -> int:
    lifecycle = ApplicationBootstrap().create_application()
    dashboard = DashboardApplication(lifecycle)
    return dashboard.run()


if __name__ == "__main__":
    raise SystemExit(main())
