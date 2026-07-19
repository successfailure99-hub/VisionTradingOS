"""
Desktop live market-data composition helpers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from application.bootstrap import ApplicationBootstrap
from application.enums import RuntimeInstrument
from application.lifecycle_manager import ApplicationLifecycleManager
from application.live_market_data import LiveMarketDataConfiguration, LiveMarketDataRuntime, LiveMarketDataRuntimeFactory
from application.models import RuntimeConfiguration
from application.reference_data_bootstrap import run_reference_data_bootstrap
from application.futures_vwap import DesktopFuturesVWAPRuntimeManager
from engines.risk.models import InstrumentLotSize, RiskConfiguration
from engines.paper_trading import PaperIntrabarPolicy, PaperTradingConfiguration
from application.desktop_option_chain import (
    DesktopOptionChainConfigurationError,
    DesktopOptionChainRuntimeManager,
    DesktopOptionChainSettings,
    InstrumentClientFactory,
    create_instrument_client,
)
from brokers.zerodha.auth import KiteConnectAuthClient, ZerodhaCredentials, ZerodhaSessionManager
from brokers.zerodha.historical import KiteHistoricalClient
from brokers.zerodha.market_data import KiteTickerClient, ZerodhaInstrumentSubscription, ZerodhaSubscriptionMode
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from dashboard.application import DashboardApplication


class DesktopLiveDataConfigurationError(RuntimeError):
    """Raised for sanitized desktop live-data startup configuration failures."""


class AuthClientFactory(Protocol):
    def __call__(self, api_key: str):
        ...


class SessionManagerFactory(Protocol):
    def __call__(self, credentials: ZerodhaCredentials, *, client, clock):
        ...


class HistoricalClientFactory(Protocol):
    def __call__(self, *, api_key: str, access_token: str):
        ...


ENV_ZERODHA_API_KEY = "ZERODHA_API_KEY"
ENV_ZERODHA_API_SECRET = "ZERODHA_API_SECRET"
ENV_ZERODHA_ACCESS_TOKEN = "ZERODHA_ACCESS_TOKEN"
ENV_LIVE_MARKET_DATA_ENABLED = "LIVE_MARKET_DATA_ENABLED"
ENV_LIVE_MARKET_DATA_AUTO_CONNECT = "LIVE_MARKET_DATA_AUTO_CONNECT"
ENV_LIVE_OPTION_CHAIN_ENABLED = "LIVE_OPTION_CHAIN_ENABLED"
ENV_LIVE_OPTION_CHAIN_AUTO_START = "LIVE_OPTION_CHAIN_AUTO_START"
ENV_LIVE_FUTURES_VWAP_ENABLED = "LIVE_FUTURES_VWAP_ENABLED"
ENV_OPTION_CHAIN_STRIKES_EACH_SIDE = "OPTION_CHAIN_STRIKES_EACH_SIDE"
ENV_REFERENCE_DATA_BOOTSTRAP_ENABLED = "REFERENCE_DATA_BOOTSTRAP_ENABLED"
ENV_RISK_ENABLED = "RISK_ENABLED"
ENV_RISK_CAPITAL = "RISK_CAPITAL"
ENV_RISK_PER_TRADE_PERCENT = "RISK_PER_TRADE_PERCENT"
ENV_RISK_MAX_AMOUNT_PER_TRADE = "RISK_MAX_AMOUNT_PER_TRADE"
ENV_RISK_MAX_LOTS = "RISK_MAX_LOTS"
ENV_RISK_MIN_REWARD_RISK = "RISK_MIN_REWARD_RISK"
ENV_RISK_MAX_STOP_PERCENT = "RISK_MAX_STOP_PERCENT"
ENV_RISK_MAX_TRADES_PER_DAY = "RISK_MAX_TRADES_PER_DAY"
ENV_RISK_MAX_DAILY_LOSS = "RISK_MAX_DAILY_LOSS"
ENV_RISK_ALLOW_LOW_CONFIDENCE = "RISK_ALLOW_LOW_CONFIDENCE"
ENV_RISK_ALLOW_MIXED_SIGNALS = "RISK_ALLOW_MIXED_SIGNALS"
ENV_TRADE_PLAN_VALIDITY_MINUTES = "TRADE_PLAN_VALIDITY_MINUTES"
ENV_PAPER_TRADING_ENABLED = "PAPER_TRADING_ENABLED"
ENV_PAPER_AUTO_CREATE_ORDER = "PAPER_AUTO_CREATE_ORDER"
ENV_PAPER_SLIPPAGE_POINTS = "PAPER_SLIPPAGE_POINTS"
ENV_PAPER_FIXED_FEE_PER_TRADE = "PAPER_FIXED_FEE_PER_TRADE"
ENV_PAPER_FEE_PERCENTAGE = "PAPER_FEE_PERCENTAGE"
ENV_PAPER_INTRABAR_POLICY = "PAPER_INTRABAR_POLICY"
ENV_PAPER_EXIT_ON_STRATEGY_INVALIDATION = "PAPER_EXIT_ON_STRATEGY_INVALIDATION"
ENV_PAPER_CLOSE_AT_SESSION_END = "PAPER_CLOSE_AT_SESSION_END"
ENV_PAPER_CANCEL_PENDING_AT_SESSION_END = "PAPER_CANCEL_PENDING_AT_SESSION_END"
ENV_PAPER_MAX_ACTIVE_POSITIONS_PER_INSTRUMENT = "PAPER_MAX_ACTIVE_POSITIONS_PER_INSTRUMENT"
ENV_PAPER_STALE_DATA_SECONDS = "PAPER_STALE_DATA_SECONDS"

INSTRUMENT_TOKEN_ENV = (
    (Instrument.NIFTY, "NIFTY_INSTRUMENT_TOKEN", Exchange.NSE),
    (Instrument.BANKNIFTY, "BANKNIFTY_INSTRUMENT_TOKEN", Exchange.NSE),
    (Instrument.SENSEX, "SENSEX_INSTRUMENT_TOKEN", Exchange.BSE),
)


@dataclass(frozen=True, slots=True, repr=False)
class DesktopLiveDataSettings:
    enabled: bool
    auto_connect: bool
    api_key: str | None
    api_secret: str | None
    access_token: str | None
    subscriptions: tuple[ZerodhaInstrumentSubscription, ...]
    option_chain: DesktopOptionChainSettings
    reference_data_bootstrap_enabled: bool
    futures_vwap_enabled: bool
    risk_configuration: RiskConfiguration | None
    paper_trading_configuration: PaperTradingConfiguration

    def __repr__(self) -> str:
        return (
            "DesktopLiveDataSettings("
            f"enabled={self.enabled}, "
            f"auto_connect={self.auto_connect}, "
            f"subscriptions={len(self.subscriptions)}, "
            f"option_chain_enabled={self.option_chain.enabled}, "
            f"reference_data_bootstrap_enabled={self.reference_data_bootstrap_enabled}, "
            f"futures_vwap_enabled={self.futures_vwap_enabled}, "
            f"risk_enabled={self.risk_configuration is not None}, "
            f"paper_trading_enabled={self.paper_trading_configuration.enabled})"
        )

    __str__ = __repr__


def load_desktop_live_configuration(
    environ: Mapping[str, str],
) -> DesktopLiveDataSettings:
    enabled = _parse_bool(environ.get(ENV_LIVE_MARKET_DATA_ENABLED, "false"), ENV_LIVE_MARKET_DATA_ENABLED)
    auto_connect = _parse_bool(environ.get(ENV_LIVE_MARKET_DATA_AUTO_CONNECT, "true"), ENV_LIVE_MARKET_DATA_AUTO_CONNECT)
    option_chain = _load_option_chain_settings(environ)
    risk_configuration = _load_risk_configuration(environ)
    paper_trading_configuration = _load_paper_trading_configuration(environ)
    futures_vwap_enabled = _parse_bool(
        environ.get(ENV_LIVE_FUTURES_VWAP_ENABLED, "true"),
        ENV_LIVE_FUTURES_VWAP_ENABLED,
    )
    reference_bootstrap = _parse_bool(
        environ.get(ENV_REFERENCE_DATA_BOOTSTRAP_ENABLED, "true"),
        ENV_REFERENCE_DATA_BOOTSTRAP_ENABLED,
    )
    if not enabled:
        if option_chain.enabled:
            raise DesktopLiveDataConfigurationError("LIVE_OPTION_CHAIN_ENABLED requires LIVE_MARKET_DATA_ENABLED")
        return DesktopLiveDataSettings(
            enabled=False,
            auto_connect=auto_connect,
            api_key=None,
            api_secret=None,
            access_token=None,
            subscriptions=(),
            option_chain=option_chain,
            reference_data_bootstrap_enabled=False,
            futures_vwap_enabled=False,
            risk_configuration=None,
            paper_trading_configuration=paper_trading_configuration,
        )

    missing = [
        name
        for name in (
            ENV_ZERODHA_API_KEY,
            ENV_ZERODHA_API_SECRET,
            ENV_ZERODHA_ACCESS_TOKEN,
            *(name for _, name, _ in INSTRUMENT_TOKEN_ENV),
        )
        if not _text(environ.get(name))
    ]
    if missing:
        raise DesktopLiveDataConfigurationError("Missing environment variables: " + ", ".join(missing))

    subscriptions = tuple(
        ZerodhaInstrumentSubscription(
            instrument_token=_parse_token(environ[name], name),
            instrument=instrument,
            exchange=exchange,
            mode=ZerodhaSubscriptionMode.FULL,
        )
        for instrument, name, exchange in INSTRUMENT_TOKEN_ENV
    )
    _ensure_unique_tokens(subscriptions)

    return DesktopLiveDataSettings(
        enabled=True,
        auto_connect=auto_connect,
        api_key=_text(environ[ENV_ZERODHA_API_KEY]),
        api_secret=_text(environ[ENV_ZERODHA_API_SECRET]),
        access_token=_text(environ[ENV_ZERODHA_ACCESS_TOKEN]),
        subscriptions=subscriptions,
        option_chain=option_chain,
        reference_data_bootstrap_enabled=reference_bootstrap,
        futures_vwap_enabled=futures_vwap_enabled,
        risk_configuration=risk_configuration,
        paper_trading_configuration=paper_trading_configuration,
    )


def create_zerodha_session_manager(
    settings: DesktopLiveDataSettings,
    *,
    auth_client_factory: AuthClientFactory | None = None,
    session_manager_factory: SessionManagerFactory | None = None,
    clock=None,
) -> ZerodhaSessionManager | None:
    if not isinstance(settings, DesktopLiveDataSettings):
        raise TypeError("settings must be DesktopLiveDataSettings")
    if not settings.enabled:
        return None
    now = clock or _default_clock
    credentials = ZerodhaCredentials(settings.api_key, settings.api_secret)
    client_factory = auth_client_factory or KiteConnectAuthClient
    client = client_factory(credentials.api_key)
    manager_factory = session_manager_factory or ZerodhaSessionManager
    manager = manager_factory(credentials, client=client, clock=now)
    try:
        client.set_access_token(settings.access_token)
        profile = client.profile()
        user_id = _profile_user_id(profile)
        manager.restore_session(
            user_id=user_id,
            access_token=settings.access_token,
            authenticated_at=now(),
            expires_at=None,
            validate_profile=True,
        )
        manager.validate_session()
    except Exception as exc:
        raise DesktopLiveDataConfigurationError(f"Zerodha authentication failed: {_safe_message(exc, settings)}") from exc
    return manager


def create_desktop_live_runtime(
    *,
    lifecycle: ApplicationLifecycleManager,
    settings: DesktopLiveDataSettings,
    session_manager: ZerodhaSessionManager | None,
    runtime_factory: LiveMarketDataRuntimeFactory | None = None,
    ticker_client=None,
) -> LiveMarketDataRuntime | None:
    if not isinstance(settings, DesktopLiveDataSettings):
        raise TypeError("settings must be DesktopLiveDataSettings")
    if not settings.enabled:
        return None
    if session_manager is None:
        raise DesktopLiveDataConfigurationError("authenticated Zerodha session is required")
    if not lifecycle.is_running():
        lifecycle.start()
    configuration = LiveMarketDataConfiguration(
        api_key=settings.api_key,
        subscriptions=settings.subscriptions,
        auto_connect=settings.auto_connect,
    )
    factory = runtime_factory or LiveMarketDataRuntimeFactory()
    try:
        kwargs = {
            "lifecycle": lifecycle,
            "session_manager": session_manager,
            "configuration": configuration,
        }
        if ticker_client is not None:
            kwargs["ticker_client"] = ticker_client
        runtime = factory.create(**kwargs)
        if not settings.auto_connect:
            runtime.validate()
        return runtime
    except Exception as exc:
        raise DesktopLiveDataConfigurationError(f"Live market data startup failed: {_safe_message(exc, settings)}") from exc


def create_dashboard_application(
    *,
    environ: Mapping[str, str],
    auth_client_factory: AuthClientFactory | None = None,
    session_manager_factory: SessionManagerFactory | None = None,
    instrument_client_factory: InstrumentClientFactory | None = None,
    runtime_factory: LiveMarketDataRuntimeFactory | None = None,
    historical_client_factory: HistoricalClientFactory | None = None,
    ticker_client=None,
    clock=None,
) -> DashboardApplication:
    settings = load_desktop_live_configuration(environ)
    lifecycle = ApplicationBootstrap(
        RuntimeConfiguration(
            instruments=(
                RuntimeInstrument.NIFTY,
                RuntimeInstrument.BANKNIFTY,
                RuntimeInstrument.SENSEX,
            ),
            risk_configuration=settings.risk_configuration,
            paper_trading_configuration=settings.paper_trading_configuration,
        )
    ).create_application()
    session_manager = create_zerodha_session_manager(
        settings,
        auth_client_factory=auth_client_factory,
        session_manager_factory=session_manager_factory,
        clock=clock,
    )
    if settings.enabled and session_manager is not None:
        session = session_manager.session
        if session is None:
            raise DesktopLiveDataConfigurationError("authenticated Zerodha session is required")
        shared_ticker = ticker_client or KiteTickerClient(api_key=settings.api_key, access_token=session.access_token)
        ticker_router = _DesktopTickerRouter(
            shared_ticker,
            spot_tokens=tuple(subscription.instrument_token for subscription in settings.subscriptions),
        )
    else:
        ticker_router = ticker_client
    runtime = create_desktop_live_runtime(
        lifecycle=lifecycle,
        settings=settings,
        session_manager=session_manager,
        runtime_factory=runtime_factory,
        ticker_client=ticker_router,
    )
    if settings.reference_data_bootstrap_enabled and settings.enabled and session_manager is not None:
        _try_reference_data_bootstrap(
            lifecycle=lifecycle,
            settings=settings,
            session_manager=session_manager,
            historical_client_factory=historical_client_factory,
            clock=clock or _default_clock,
        )
    futures_vwap_manager = None
    if settings.futures_vwap_enabled and session_manager is not None and ticker_router is not None:
        try:
            futures_vwap_manager = _create_desktop_futures_vwap_manager(
                lifecycle=lifecycle,
                settings=settings,
                session_manager=session_manager,
                ticker_router=ticker_router,
                instrument_client_factory=instrument_client_factory,
                historical_client_factory=historical_client_factory,
                clock=clock,
            )
            ticker_router.set_futures_vwap_manager(futures_vwap_manager)
            futures_vwap_manager.start()
        except Exception:
            futures_vwap_manager = None
    option_chain_manager = None
    if settings.option_chain.enabled and session_manager is not None and ticker_router is not None:
        option_chain_manager = _create_desktop_option_chain_manager(
            lifecycle=lifecycle,
            settings=settings,
            session_manager=session_manager,
            live_market_data_runtime=runtime,
            ticker_router=ticker_router,
            instrument_client_factory=instrument_client_factory,
            clock=clock,
        )
        if settings.option_chain.auto_start:
            option_chain_manager.start()
    return DashboardApplication(
        lifecycle,
        live_market_data_runtime=runtime,
        live_option_chain_runtime=option_chain_manager,
        live_futures_vwap_runtime=futures_vwap_manager,
        clock=clock,
    )


def _try_reference_data_bootstrap(
    *,
    lifecycle: ApplicationLifecycleManager,
    settings: DesktopLiveDataSettings,
    session_manager: ZerodhaSessionManager,
    historical_client_factory: HistoricalClientFactory | None,
    clock,
) -> None:
    session = session_manager.session
    if session is None:
        return
    try:
        factory = historical_client_factory or KiteHistoricalClient
        client = factory(api_key=settings.api_key, access_token=session.access_token)
        run_reference_data_bootstrap(
            lifecycle=lifecycle,
            historical_client=client,
            subscriptions=settings.subscriptions,
            clock=clock,
        )
    except Exception:
        return


def _create_desktop_option_chain_manager(
    *,
    lifecycle: ApplicationLifecycleManager,
    settings: DesktopLiveDataSettings,
    session_manager: ZerodhaSessionManager,
    live_market_data_runtime: LiveMarketDataRuntime | None,
    ticker_router,
    instrument_client_factory: InstrumentClientFactory | None,
    clock=None,
) -> DesktopOptionChainRuntimeManager:
    session = session_manager.session
    if session is None or not session_manager.is_authenticated():
        raise DesktopLiveDataConfigurationError("authenticated Zerodha session is required")
    factory = instrument_client_factory or create_instrument_client
    try:
        instrument_client = factory(api_key=settings.api_key, access_token=session.access_token)
        manager = DesktopOptionChainRuntimeManager(
            lifecycle=lifecycle,
            live_market_data_runtime=live_market_data_runtime,
            ticker_client=ticker_router,
            instrument_client=instrument_client,
            settings=settings.option_chain,
            spot_subscriptions=settings.subscriptions,
            redactions=(settings.api_key, settings.api_secret, settings.access_token),
            clock=clock,
        )
    except Exception as exc:
        raise DesktopLiveDataConfigurationError(f"Live option-chain startup failed: {_safe_message(exc, settings)}") from exc
    ticker_router.set_option_chain_manager(manager)
    return manager


def _create_desktop_futures_vwap_manager(
    *,
    lifecycle: ApplicationLifecycleManager,
    settings: DesktopLiveDataSettings,
    session_manager: ZerodhaSessionManager,
    ticker_router,
    instrument_client_factory: InstrumentClientFactory | None,
    historical_client_factory: HistoricalClientFactory | None,
    clock=None,
) -> DesktopFuturesVWAPRuntimeManager:
    session = session_manager.session
    if session is None or not session_manager.is_authenticated():
        raise DesktopLiveDataConfigurationError("authenticated Zerodha session is required")
    instrument_factory = instrument_client_factory or create_instrument_client
    historical_factory = historical_client_factory or KiteHistoricalClient
    try:
        instrument_client = instrument_factory(api_key=settings.api_key, access_token=session.access_token)
        historical_client = historical_factory(api_key=settings.api_key, access_token=session.access_token)
        return DesktopFuturesVWAPRuntimeManager(
            lifecycle=lifecycle,
            ticker_client=ticker_router,
            instrument_client=instrument_client,
            historical_client=historical_client,
            redactions=(settings.api_key, settings.api_secret, settings.access_token),
            clock=clock or _default_clock,
        )
    except Exception as exc:
        raise DesktopLiveDataConfigurationError(f"Futures VWAP startup failed: {_safe_message(exc, settings)}") from exc


def _parse_bool(value: str | None, variable_name: str) -> bool:
    normalized = _text(value).lower() if value is not None else ""
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise DesktopLiveDataConfigurationError(f"{variable_name} must be 'true' or 'false'")


def _parse_token(value: str, variable_name: str) -> int:
    try:
        token = int(value.strip())
    except Exception as exc:
        raise DesktopLiveDataConfigurationError(f"{variable_name} must be a positive integer") from exc
    if token <= 0:
        raise DesktopLiveDataConfigurationError(f"{variable_name} must be a positive integer")
    return token


def _load_option_chain_settings(environ: Mapping[str, str]) -> DesktopOptionChainSettings:
    enabled = _parse_bool(environ.get(ENV_LIVE_OPTION_CHAIN_ENABLED, "false"), ENV_LIVE_OPTION_CHAIN_ENABLED)
    auto_start = _parse_bool(environ.get(ENV_LIVE_OPTION_CHAIN_AUTO_START, "true"), ENV_LIVE_OPTION_CHAIN_AUTO_START)
    strikes_each_side = _parse_bounded_int(
        environ.get(ENV_OPTION_CHAIN_STRIKES_EACH_SIDE, "5"),
        ENV_OPTION_CHAIN_STRIKES_EACH_SIDE,
        minimum=1,
        maximum=20,
    )
    return DesktopOptionChainSettings(
        enabled=enabled,
        auto_start=auto_start,
        strikes_each_side=strikes_each_side,
    )


def _load_risk_configuration(environ: Mapping[str, str]) -> RiskConfiguration | None:
    enabled = _parse_bool(environ.get(ENV_RISK_ENABLED, "false"), ENV_RISK_ENABLED)
    if not enabled:
        return None
    lot_sizes = []
    missing = []
    for instrument, _, _ in INSTRUMENT_TOKEN_ENV:
        name = f"{instrument.value}_LOT_SIZE"
        if not _text(environ.get(name)):
            missing.append(name)
        else:
            lot_sizes.append(InstrumentLotSize(instrument.value, _parse_bounded_int(environ.get(name), name, minimum=1, maximum=10000)))
    if not _text(environ.get(ENV_RISK_CAPITAL)):
        missing.append(ENV_RISK_CAPITAL)
    if missing:
        raise DesktopLiveDataConfigurationError("Missing risk environment variables: " + ", ".join(missing))
    return RiskConfiguration(
        capital=_parse_positive_float(environ.get(ENV_RISK_CAPITAL), ENV_RISK_CAPITAL),
        risk_per_trade_percentage=_parse_positive_float(environ.get(ENV_RISK_PER_TRADE_PERCENT, "1.0"), ENV_RISK_PER_TRADE_PERCENT),
        maximum_risk_per_trade_amount=_parse_optional_positive_float(environ.get(ENV_RISK_MAX_AMOUNT_PER_TRADE), ENV_RISK_MAX_AMOUNT_PER_TRADE),
        maximum_lots=_parse_bounded_int(environ.get(ENV_RISK_MAX_LOTS, "2"), ENV_RISK_MAX_LOTS, minimum=1, maximum=1000),
        minimum_reward_risk=_parse_positive_float(environ.get(ENV_RISK_MIN_REWARD_RISK, "1.5"), ENV_RISK_MIN_REWARD_RISK),
        maximum_stop_distance_percentage=_parse_positive_float(environ.get(ENV_RISK_MAX_STOP_PERCENT, "1.0"), ENV_RISK_MAX_STOP_PERCENT),
        maximum_trades_per_day=_parse_bounded_int(environ.get(ENV_RISK_MAX_TRADES_PER_DAY, "3"), ENV_RISK_MAX_TRADES_PER_DAY, minimum=1, maximum=100),
        maximum_daily_loss=_parse_non_negative_float(environ.get(ENV_RISK_MAX_DAILY_LOSS, "0"), ENV_RISK_MAX_DAILY_LOSS),
        allow_low_confidence=_parse_bool(environ.get(ENV_RISK_ALLOW_LOW_CONFIDENCE, "false"), ENV_RISK_ALLOW_LOW_CONFIDENCE),
        allow_mixed_signals=_parse_bool(environ.get(ENV_RISK_ALLOW_MIXED_SIGNALS, "false"), ENV_RISK_ALLOW_MIXED_SIGNALS),
        trade_plan_validity_minutes=_parse_bounded_int(environ.get(ENV_TRADE_PLAN_VALIDITY_MINUTES, "15"), ENV_TRADE_PLAN_VALIDITY_MINUTES, minimum=1, maximum=240),
        lot_sizes=tuple(lot_sizes),
    )


def _load_paper_trading_configuration(environ: Mapping[str, str]) -> PaperTradingConfiguration:
    policy = _text(environ.get(ENV_PAPER_INTRABAR_POLICY, "STOP_FIRST")).upper()
    if policy != "STOP_FIRST":
        raise DesktopLiveDataConfigurationError("PAPER_INTRABAR_POLICY must be STOP_FIRST")
    return PaperTradingConfiguration(
        enabled=_parse_bool(environ.get(ENV_PAPER_TRADING_ENABLED, "true"), ENV_PAPER_TRADING_ENABLED),
        auto_create_order=_parse_bool(environ.get(ENV_PAPER_AUTO_CREATE_ORDER, "true"), ENV_PAPER_AUTO_CREATE_ORDER),
        slippage_points=_parse_non_negative_float(environ.get(ENV_PAPER_SLIPPAGE_POINTS, "0"), ENV_PAPER_SLIPPAGE_POINTS),
        fixed_fee_per_trade=_parse_non_negative_float(environ.get(ENV_PAPER_FIXED_FEE_PER_TRADE, "0"), ENV_PAPER_FIXED_FEE_PER_TRADE),
        fee_percentage=_parse_non_negative_float(environ.get(ENV_PAPER_FEE_PERCENTAGE, "0"), ENV_PAPER_FEE_PERCENTAGE),
        intrabar_policy=PaperIntrabarPolicy.STOP_FIRST,
        exit_on_strategy_invalidation=_parse_bool(environ.get(ENV_PAPER_EXIT_ON_STRATEGY_INVALIDATION, "false"), ENV_PAPER_EXIT_ON_STRATEGY_INVALIDATION),
        close_at_session_end=_parse_bool(environ.get(ENV_PAPER_CLOSE_AT_SESSION_END, "true"), ENV_PAPER_CLOSE_AT_SESSION_END),
        cancel_pending_at_session_end=_parse_bool(environ.get(ENV_PAPER_CANCEL_PENDING_AT_SESSION_END, "true"), ENV_PAPER_CANCEL_PENDING_AT_SESSION_END),
        max_active_positions_per_instrument=_parse_bounded_int(environ.get(ENV_PAPER_MAX_ACTIVE_POSITIONS_PER_INSTRUMENT, "1"), ENV_PAPER_MAX_ACTIVE_POSITIONS_PER_INSTRUMENT, minimum=1, maximum=1),
        stale_data_seconds=_parse_bounded_int(environ.get(ENV_PAPER_STALE_DATA_SECONDS, "300"), ENV_PAPER_STALE_DATA_SECONDS, minimum=1, maximum=86400),
    )
def _parse_bounded_int(value: str | None, variable_name: str, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(_text(value))
    except Exception as exc:
        raise DesktopLiveDataConfigurationError(f"{variable_name} must be between {minimum} and {maximum}") from exc
    if parsed < minimum or parsed > maximum:
        raise DesktopLiveDataConfigurationError(f"{variable_name} must be between {minimum} and {maximum}")
    return parsed


def _parse_positive_float(value: str | None, variable_name: str) -> float:
    try:
        parsed = float(_text(value))
    except Exception as exc:
        raise DesktopLiveDataConfigurationError(f"{variable_name} must be positive") from exc
    if parsed <= 0:
        raise DesktopLiveDataConfigurationError(f"{variable_name} must be positive")
    return parsed


def _parse_optional_positive_float(value: str | None, variable_name: str) -> float | None:
    if not _text(value):
        return None
    return _parse_positive_float(value, variable_name)


def _parse_non_negative_float(value: str | None, variable_name: str) -> float:
    try:
        parsed = float(_text(value))
    except Exception as exc:
        raise DesktopLiveDataConfigurationError(f"{variable_name} must be non-negative") from exc
    if parsed < 0:
        raise DesktopLiveDataConfigurationError(f"{variable_name} must be non-negative")
    return parsed


def _ensure_unique_tokens(subscriptions: tuple[ZerodhaInstrumentSubscription, ...]) -> None:
    tokens = [subscription.instrument_token for subscription in subscriptions]
    if len(tokens) != len(set(tokens)):
        raise DesktopLiveDataConfigurationError("Instrument tokens must be unique")


def _profile_user_id(profile) -> str:
    value = profile.get("user_id") if hasattr(profile, "get") else None
    user_id = _text(value)
    if not user_id:
        raise DesktopLiveDataConfigurationError("Zerodha profile user_id is required")
    return user_id


def _safe_message(exc: Exception, settings: DesktopLiveDataSettings) -> str:
    message = str(exc) or exc.__class__.__name__
    for secret in (settings.api_key, settings.api_secret, settings.access_token):
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _default_clock() -> datetime:
    return datetime.now(UTC)


class _DesktopTickerRouter:
    def __init__(self, client, *, spot_tokens: tuple[int, ...]):
        self._client = client
        self._spot_tokens = set(spot_tokens)
        self._option_chain_manager = None
        self._futures_vwap_manager = None
        self._callbacks = {}
        self._callback_error_count = 0
        self._last_callback_error = None

    def set_option_chain_manager(self, manager: DesktopOptionChainRuntimeManager) -> None:
        self._option_chain_manager = manager

    def set_futures_vwap_manager(self, manager: DesktopFuturesVWAPRuntimeManager) -> None:
        self._futures_vwap_manager = manager

    def set_callbacks(self, **callbacks):
        self._callbacks = callbacks
        self._client.set_callbacks(
            **{
                **callbacks,
                "on_ticks": self._on_ticks,
            }
        )

    def connect(self, *, threaded=True):
        self._client.connect(threaded=threaded)

    def close(self):
        self._client.close()

    def subscribe(self, instrument_tokens):
        self._client.subscribe(instrument_tokens)

    def unsubscribe(self, instrument_tokens):
        self._client.unsubscribe(instrument_tokens)

    def set_mode(self, mode, instrument_tokens):
        self._client.set_mode(mode, instrument_tokens)

    def _on_ticks(self, ws, ticks) -> None:
        rows = tuple(ticks)
        spot_rows = tuple(row for row in rows if _tick_token(row) in self._spot_tokens)
        if self._option_chain_manager is not None:
            if spot_rows:
                try:
                    self._option_chain_manager.deliver_spot_ticks(spot_rows)
                except Exception as exc:
                    self._record_callback_error(exc)
            option_tokens = self._option_chain_manager.option_tokens()
        else:
            option_tokens = set()
        if self._futures_vwap_manager is not None:
            futures_tokens = self._futures_vwap_manager.futures_tokens()
        else:
            futures_tokens = set()
        option_rows = tuple(row for row in rows if _tick_token(row) in option_tokens)
        futures_rows = tuple(row for row in rows if _tick_token(row) in futures_tokens)
        unknown_rows = tuple(
            row
            for row in rows
            if _tick_token(row) not in self._spot_tokens
            and _tick_token(row) not in option_tokens
            and _tick_token(row) not in futures_tokens
        )
        spot_callback = self._callbacks.get("on_ticks")
        if spot_callback is not None and (spot_rows or unknown_rows):
            try:
                spot_callback(ws, spot_rows + unknown_rows)
            except Exception as exc:
                self._record_callback_error(exc)
        if self._futures_vwap_manager is not None and futures_rows:
            try:
                self._futures_vwap_manager.deliver_futures_ticks(futures_rows)
            except Exception as exc:
                self._record_callback_error(exc)
        if self._option_chain_manager is not None:
            if option_rows:
                try:
                    self._option_chain_manager.deliver_option_ticks(option_rows)
                except Exception as exc:
                    self._record_callback_error(exc)

    def _record_callback_error(self, exc: Exception) -> None:
        self._callback_error_count += 1
        self._last_callback_error = f"{exc.__class__.__name__}: live tick callback isolated"


def _tick_token(row) -> int | None:
    token = row.get("instrument_token") if hasattr(row, "get") else None
    return token if isinstance(token, int) and not isinstance(token, bool) else None
