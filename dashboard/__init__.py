"""
Vision Trading OS desktop dashboard package.
"""

from importlib import import_module

__all__ = [
    "DashboardApplication",
    "VisionMainWindow",
    "DashboardView",
    "DashboardRuntimeView",
    "DashboardLiveMarketDataView",
    "DashboardLiveSubscriptionView",
    "DashboardOptionChainView",
    "DashboardOptionChainStrikeView",
    "DashboardMarketView",
    "DashboardAIView",
    "DashboardStrategyView",
    "DashboardPositionView",
    "DashboardJournalView",
    "DashboardAnalyticsView",
    "OptionChainPanel",
    "AnalyticsPanel",
    "build_dashboard_view",
    "build_live_market_data_view",
    "build_option_chain_view",
]


def __getattr__(name):
    if name == "DashboardApplication":
        from dashboard.application import DashboardApplication

        return DashboardApplication
    if name == "VisionMainWindow":
        from dashboard.main_window import VisionMainWindow

        return VisionMainWindow
    if name == "OptionChainPanel":
        from dashboard.panels.option_chain_panel import OptionChainPanel

        return OptionChainPanel
    if name == "AnalyticsPanel":
        from dashboard.panels.analytics_panel import AnalyticsPanel

        return AnalyticsPanel
    if name == "build_dashboard_view":
        from dashboard.presenters import build_dashboard_view

        return build_dashboard_view
    if name == "build_live_market_data_view":
        from dashboard.presenters import build_live_market_data_view

        return build_live_market_data_view
    if name == "build_option_chain_view":
        from dashboard.presenters import build_option_chain_view

        return build_option_chain_view
    if name in {
        "DashboardView",
        "DashboardRuntimeView",
        "DashboardLiveMarketDataView",
        "DashboardLiveSubscriptionView",
        "DashboardOptionChainView",
        "DashboardOptionChainStrikeView",
        "DashboardMarketView",
        "DashboardAIView",
        "DashboardStrategyView",
        "DashboardPositionView",
        "DashboardJournalView",
        "DashboardAnalyticsView",
    }:
        models = import_module("dashboard.models")
        return getattr(models, name)
    raise AttributeError(name)
