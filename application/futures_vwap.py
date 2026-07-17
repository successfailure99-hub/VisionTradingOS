"""
Futures-backed VWAP source for desktop live analysis.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from enum import Enum
from math import isfinite
from numbers import Real
from zoneinfo import ZoneInfo

from application.enums import RuntimeInstrument
from application.lifecycle_manager import ApplicationLifecycleManager
from brokers.zerodha.historical.manager import ZerodhaHistoricalDataManager
from brokers.zerodha.historical.models import ZerodhaHistoricalRequest
from brokers.zerodha.market_data import ZerodhaSubscriptionMode
from brokers.zerodha.market_data.timestamps import normalize_zerodha_tick_timestamp
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.enums.timeframe import TimeFrame
from core.models.tick import Tick


IST = ZoneInfo("Asia/Kolkata")
SUPPORTED_FUTURES_UNDERLYINGS = (Instrument.NIFTY, Instrument.BANKNIFTY, Instrument.SENSEX)
DERIVATIVE_VENUE_BY_UNDERLYING = {
    Instrument.NIFTY: "NFO",
    Instrument.BANKNIFTY: "NFO",
    Instrument.SENSEX: "BFO",
}
ANALYSIS_EXCHANGE_BY_UNDERLYING = {
    Instrument.NIFTY: Exchange.NSE,
    Instrument.BANKNIFTY: Exchange.NSE,
    Instrument.SENSEX: Exchange.BSE,
}


class FuturesVWAPRuntimeState(str, Enum):
    DISABLED = "Disabled"
    STARTING = "Starting"
    DISCOVERING = "Discovering Future"
    RESOLVED = "Future Resolved"
    LOADING_HISTORY = "Loading History"
    SUBSCRIBING = "Subscribing"
    WAITING_FOR_TICK = "Waiting For Futures Tick"
    RECEIVING = "Receiving"
    READY = "Ready"
    PARTIAL = "Partial"
    ERROR = "Error"
    STOPPED = "Stopped"


@dataclass(frozen=True, slots=True)
class FuturesVWAPContract:
    underlying: Instrument
    instrument_token: int
    exchange_token: int
    trading_symbol: str
    source_exchange: str
    segment: str
    expiry: date


@dataclass(frozen=True, slots=True)
class FuturesVWAPInstrumentSnapshot:
    underlying: Instrument
    enabled: bool
    configured: bool
    started: bool
    state: FuturesVWAPRuntimeState
    message: str
    analysis_instrument: Instrument
    source_exchange: str
    source_trading_symbol: str
    source_token: int | None
    source_expiry: date | None
    contracts_examined: int
    contracts_matched: int
    subscription_active: bool
    ready: bool
    contract: FuturesVWAPContract | None
    warmed_candles: int
    historical_volume: int
    historical_seed_complete: bool
    bootstrap_time: datetime | None
    live_ticks: int
    last_live_volume: int
    last_delta_volume: int
    last_source_price: float | None
    cumulative_volume: int
    vwap_ready: bool
    vwap_value: float | None
    last_updated_at: datetime | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class FuturesVWAPRuntimeSnapshot:
    enabled: bool
    started: bool
    state: FuturesVWAPRuntimeState
    futures_token_count: int
    ready_underlyings: tuple[Instrument, ...]
    last_updated_at: datetime | None
    last_error: str | None
    instruments: tuple[FuturesVWAPInstrumentSnapshot, ...]


@dataclass(slots=True)
class _MutableFuturesState:
    underlying: Instrument
    contract: FuturesVWAPContract | None = None
    started: bool = False
    state: FuturesVWAPRuntimeState = FuturesVWAPRuntimeState.DISABLED
    message: str = "Disabled"
    contracts_examined: int = 0
    contracts_matched: int = 0
    subscription_active: bool = False
    warmed_candles: int = 0
    historical_volume: int = 0
    historical_seed_complete: bool = False
    historical_bootstrap_attempted: bool = False
    bootstrap_time: datetime | None = None
    live_ticks: int = 0
    last_live_volume: int = 0
    last_delta_volume: int = 0
    last_cumulative_live_volume: int | None = None
    last_source_price: float | None = None
    last_updated_at: datetime | None = None
    cumulative_volume: int = 0
    vwap_value: float | None = None
    last_error: str | None = None

    @property
    def ready(self) -> bool:
        return self.contract is not None and self.last_error is None and self.cumulative_volume > 0 and self.vwap_value is not None


class DesktopFuturesVWAPRuntimeManager:
    def __init__(
        self,
        *,
        lifecycle: ApplicationLifecycleManager,
        ticker_client,
        instrument_client,
        historical_client=None,
        redactions: tuple[str | None, ...] = (),
        clock=None,
    ):
        if not isinstance(lifecycle, ApplicationLifecycleManager):
            raise TypeError("lifecycle must be ApplicationLifecycleManager")
        self._lifecycle = lifecycle
        self._ticker_client = ticker_client
        self._instrument_client = instrument_client
        self._historical_client = historical_client
        self._redactions = tuple(value for value in redactions if value)
        self._clock = clock or _default_clock
        self._states = {
            underlying: _MutableFuturesState(underlying=underlying)
            for underlying in SUPPORTED_FUTURES_UNDERLYINGS
        }
        self._token_owner: dict[int, Instrument] = {}
        self._started = False
        self._stopped = False
        self._last_error: str | None = None
        self._last_updated_at: datetime | None = None
        self._start_count = 0
        self._stop_count = 0

    def futures_tokens(self) -> set[int]:
        return set(self._token_owner)

    def snapshot(self) -> FuturesVWAPRuntimeSnapshot:
        instruments = tuple(self._snapshot_for(underlying) for underlying in SUPPORTED_FUTURES_UNDERLYINGS)
        ready = tuple(item.underlying for item in instruments if item.ready)
        if not self._started:
            state = FuturesVWAPRuntimeState.DISABLED
        elif len(ready) == len(SUPPORTED_FUTURES_UNDERLYINGS):
            state = FuturesVWAPRuntimeState.READY
        elif ready:
            state = FuturesVWAPRuntimeState.PARTIAL
        elif self._stopped:
            state = FuturesVWAPRuntimeState.STOPPED
        else:
            state = FuturesVWAPRuntimeState.ERROR
        return FuturesVWAPRuntimeSnapshot(
            enabled=True,
            started=self._started,
            state=state,
            futures_token_count=len(self._token_owner),
            ready_underlyings=ready,
            last_updated_at=self._last_updated_at,
            last_error=self._last_error,
            instruments=instruments,
        )

    def start(self) -> FuturesVWAPRuntimeSnapshot:
        if self._started:
            return self.snapshot()
        self._started = True
        self._start_count += 1
        self._stopped = False
        self._last_error = None
        for state in self._states.values():
            state.started = True
            state.state = FuturesVWAPRuntimeState.DISCOVERING
            state.message = f"Resolving nearest {state.underlying.value} futures contract"
        contracts = self._discover_contracts()
        for underlying, state in self._states.items():
            contract = contracts.get(underlying)
            if contract is None:
                state.last_error = state.last_error or f"No valid {underlying.value} futures contract was discovered."
                state.state = FuturesVWAPRuntimeState.ERROR
                state.message = state.last_error
                self._mark_runtime_vwap_unavailable(underlying, state.last_error, state=state.state)
                continue
            state.contract = contract
            state.state = FuturesVWAPRuntimeState.RESOLVED
            state.message = f"Resolved {contract.trading_symbol}"
            self._token_owner[contract.instrument_token] = underlying
            try:
                state.state = FuturesVWAPRuntimeState.LOADING_HISTORY
                state.message = f"Loading completed {contract.trading_symbol} history"
                state.warmed_candles = self._try_bootstrap_contract(contract)
            except Exception as exc:
                state.last_error = _safe_error(exc, self._redactions)
                state.state = FuturesVWAPRuntimeState.ERROR
                state.message = state.last_error
                self._mark_runtime_vwap_unavailable(underlying, state.last_error, contract=contract, state=state.state)
                continue
            state.last_error = None
            state.state = FuturesVWAPRuntimeState.WAITING_FOR_TICK if state.cumulative_volume == 0 else FuturesVWAPRuntimeState.READY
            state.message = "Waiting for first futures tick" if state.cumulative_volume == 0 else "Futures proxy VWAP ready"
        if self._token_owner:
            tokens = tuple(sorted(self._token_owner))
            for state in self._states.values():
                if state.contract is not None and state.contract.instrument_token in self._token_owner:
                    state.state = FuturesVWAPRuntimeState.SUBSCRIBING
                    state.message = f"Subscribing {state.contract.trading_symbol}"
            try:
                self._ticker_client.subscribe(tokens)
                self._ticker_client.set_mode(ZerodhaSubscriptionMode.FULL.value, tokens)
            except Exception as exc:
                error = _safe_error(exc, self._redactions)
                owners = dict(self._token_owner)
                self._token_owner.clear()
                for token, underlying in owners.items():
                    state = self._states[underlying]
                    state.subscription_active = False
                    state.state = FuturesVWAPRuntimeState.ERROR
                    state.last_error = error
                    state.message = error
                    self._mark_runtime_vwap_unavailable(underlying, error, contract=state.contract, state=state.state)
                self._last_error = error
                self._last_updated_at = _safe_now(self._clock)
                return self.snapshot()
            for underlying in set(self._token_owner.values()):
                state = self._states[underlying]
                state.subscription_active = True
                if state.cumulative_volume > 0:
                    state.state = FuturesVWAPRuntimeState.READY
                    state.message = "Futures proxy VWAP ready"
                else:
                    state.state = FuturesVWAPRuntimeState.WAITING_FOR_TICK
                    state.message = "Waiting for first futures tick"
                self._mark_runtime_vwap_unavailable(
                    underlying,
                    "Waiting for first futures tick" if state.cumulative_volume == 0 else "Futures proxy VWAP ready",
                    contract=state.contract,
                    state=state.state,
                    subscription_active=True,
                )
        self._last_updated_at = _safe_now(self._clock)
        self._last_error = next((state.last_error for state in self._states.values() if state.last_error), None)
        return self.snapshot()

    def stop(self) -> FuturesVWAPRuntimeSnapshot:
        if self._stopped:
            return self.snapshot()
        if self._token_owner:
            self._ticker_client.unsubscribe(tuple(sorted(self._token_owner)))
        self._stop_count += 1
        self._stopped = True
        self._last_updated_at = _safe_now(self._clock)
        return self.snapshot()

    def deliver_futures_ticks(self, raw_ticks) -> None:
        if not self._started or self._stopped:
            return
        for raw_tick in tuple(raw_ticks):
            token = _raw_token(raw_tick)
            underlying = self._token_owner.get(token)
            if underlying is None:
                continue
            state = self._states[underlying]
            contract = state.contract
            if contract is None:
                continue
            try:
                self._bootstrap_before_first_live_tick(state, contract)
                price = _raw_price(raw_tick)
                cumulative_volume = _raw_volume(raw_tick)
                volume = self._incremental_live_volume(state, cumulative_volume)
                if volume <= 0:
                    continue
                timestamp = normalize_zerodha_tick_timestamp(raw_tick, clock=self._clock).timestamp
                state.live_ticks += 1
                state.last_live_volume = cumulative_volume
                state.last_delta_volume = volume
                state.last_source_price = price
                state.last_updated_at = timestamp
                state.state = FuturesVWAPRuntimeState.RECEIVING
                state.message = "Receiving futures ticks"
                self._process_vwap_tick(contract, price=price, volume=volume, timestamp=timestamp)
            except Exception as exc:
                state.last_error = _safe_error(exc, self._redactions)
                self._last_error = state.last_error
                self._mark_runtime_vwap_unavailable(underlying, state.last_error)
                continue
            state.last_error = None
            self._last_updated_at = timestamp

    def _discover_contracts(self) -> dict[Instrument, FuturesVWAPContract]:
        contracts: dict[Instrument, FuturesVWAPContract] = {}
        for underlying in SUPPORTED_FUTURES_UNDERLYINGS:
            venue = DERIVATIVE_VENUE_BY_UNDERLYING[underlying]
            state = self._states[underlying]
            try:
                raw_records = tuple(self._instrument_client.instruments(venue))
                state.contracts_examined = len(raw_records)
                candidates = []
                for record in raw_records:
                    if not _is_requested_future_record(record, underlying, venue):
                        continue
                    try:
                        candidates.append(_contract_from_record(record, underlying, venue))
                    except Exception as exc:
                        state.last_error = _rejected_contract_message(record, exc)
                today = _trading_date(self._clock)
                valid = tuple(contract for contract in candidates if contract.expiry >= today)
                state.contracts_matched = len(valid)
                if not valid:
                    state.last_error = state.last_error or f"No valid {underlying.value} futures contract was discovered."
                    continue
                contracts[underlying] = sorted(valid, key=lambda item: (item.expiry, item.trading_symbol))[0]
            except Exception as exc:
                state.last_error = f"Discovery Failed: {_safe_error(exc, self._redactions)}"
        return contracts

    def _try_bootstrap_contract(self, contract: FuturesVWAPContract) -> int:
        state = self._states[contract.underlying]
        if state.historical_bootstrap_attempted or state.cumulative_volume > 0:
            return state.warmed_candles
        if self._historical_client is None:
            return 0
        bounds = _current_completed_minute_bounds(self._clock)
        if bounds is None:
            return 0
        state.historical_bootstrap_attempted = True
        state.bootstrap_time = _safe_now(self._clock)
        manager = ZerodhaHistoricalDataManager(client=self._historical_client, clock=self._clock)
        result = manager.fetch(
            ZerodhaHistoricalRequest(
                instrument_token=contract.instrument_token,
                instrument=contract.underlying,
                exchange=ANALYSIS_EXCHANGE_BY_UNDERLYING[contract.underlying],
                timeframe=TimeFrame.ONE_MINUTE,
                start_at=bounds[0],
                end_at=bounds[1],
                continuous=False,
                include_open_interest=False,
            )
        )
        state.historical_seed_complete = True
        accepted = state.warmed_candles
        for candle in result.candles:
            if candle.volume <= 0:
                continue
            accepted += 1
            state.warmed_candles = accepted
            state.historical_volume += candle.volume
            state.last_cumulative_live_volume = state.historical_volume
            self._process_vwap_tick(
                contract,
                price=candle.close,
                volume=candle.volume,
                timestamp=candle.end_time,
            )
        return accepted

    def _bootstrap_before_first_live_tick(self, state: _MutableFuturesState, contract: FuturesVWAPContract) -> None:
        if state.cumulative_volume > 0 or state.historical_bootstrap_attempted:
            return
        try:
            self._try_bootstrap_contract(contract)
        except Exception as exc:
            state.historical_bootstrap_attempted = True
            state.last_error = _safe_error(exc, self._redactions)
            state.message = state.last_error

    def _process_vwap_tick(
        self,
        contract: FuturesVWAPContract,
        *,
        price: float,
        volume: int,
        timestamp: datetime,
    ) -> None:
        runtime = self._runtime_for(contract.underlying)
        state = self._states[contract.underlying]
        projected_accumulated_volume = state.cumulative_volume + volume
        runtime.process_vwap_tick(
            Tick(
                symbol=contract.underlying,
                exchange=ANALYSIS_EXCHANGE_BY_UNDERLYING[contract.underlying],
                timestamp=timestamp,
                last_price=price,
                volume=volume,
                bid_price=0.0,
                ask_price=0.0,
                open_interest=0,
            ),
            source_type="Futures Proxy",
            source_exchange=contract.source_exchange,
            trading_symbol=contract.trading_symbol,
            instrument_token=contract.instrument_token,
            expiry=contract.expiry,
            state="Ready",
            message="Futures proxy VWAP ready",
            subscription_active=state.subscription_active,
            historical_candles_loaded=state.warmed_candles,
            historical_volume=state.historical_volume,
            historical_seed_complete=state.historical_seed_complete,
            bootstrap_time=state.bootstrap_time,
            live_tick_count=state.live_ticks,
            last_live_volume=state.last_live_volume,
            last_delta_volume=state.last_delta_volume,
            last_live_tick=state.last_updated_at,
            current_accumulated_volume=projected_accumulated_volume,
        )
        levels = runtime.vwap_engine.get_latest(contract.underlying)
        if levels is not None:
            state = self._states[contract.underlying]
            state.cumulative_volume = levels.cumulative_volume
            state.vwap_value = levels.vwap

    def _mark_runtime_vwap_unavailable(
        self,
        underlying: Instrument,
        reason: str,
        *,
        contract: FuturesVWAPContract | None = None,
        state: FuturesVWAPRuntimeState = FuturesVWAPRuntimeState.ERROR,
        subscription_active: bool = False,
    ) -> None:
        try:
            source = contract or self._states[underlying].contract
            self._runtime_for(underlying).mark_vwap_unavailable(
                reason,
                source_type="Futures Proxy" if source is not None else "-",
                source_exchange=source.source_exchange if source is not None else "-",
                trading_symbol=source.trading_symbol if source is not None else "-",
                instrument_token=source.instrument_token if source is not None else None,
                expiry=source.expiry if source is not None else None,
                state=state.value,
                message=reason,
                subscription_active=subscription_active,
                last_error=reason if state is FuturesVWAPRuntimeState.ERROR else None,
            )
        except Exception:
            return

    def _runtime_for(self, underlying: Instrument):
        return self._lifecycle.orchestrator.get_runtime(RuntimeInstrument(underlying.value))

    def _snapshot_for(self, underlying: Instrument) -> FuturesVWAPInstrumentSnapshot:
        state = self._states[underlying]
        return FuturesVWAPInstrumentSnapshot(
            underlying=underlying,
            enabled=True,
            configured=True,
            started=state.started,
            state=state.state,
            message=state.message,
            analysis_instrument=underlying,
            source_exchange=state.contract.source_exchange if state.contract is not None else "-",
            source_trading_symbol=state.contract.trading_symbol if state.contract is not None else "-",
            source_token=state.contract.instrument_token if state.contract is not None else None,
            source_expiry=state.contract.expiry if state.contract is not None else None,
            contracts_examined=state.contracts_examined,
            contracts_matched=state.contracts_matched,
            subscription_active=state.subscription_active,
            ready=state.ready,
            contract=state.contract,
            warmed_candles=state.warmed_candles,
            historical_volume=state.historical_volume,
            historical_seed_complete=state.historical_seed_complete,
            bootstrap_time=state.bootstrap_time,
            live_ticks=state.live_ticks,
            last_live_volume=state.last_live_volume,
            last_delta_volume=state.last_delta_volume,
            last_source_price=state.last_source_price,
            cumulative_volume=state.cumulative_volume,
            vwap_ready=state.vwap_value is not None and state.cumulative_volume > 0,
            vwap_value=state.vwap_value,
            last_updated_at=state.last_updated_at,
            last_error=state.last_error,
        )

    def _incremental_live_volume(self, state: _MutableFuturesState, cumulative_volume: int) -> int:
        previous = state.last_cumulative_live_volume
        if previous is None:
            state.last_cumulative_live_volume = cumulative_volume
            return cumulative_volume
        if cumulative_volume <= previous:
            return 0
        state.last_cumulative_live_volume = cumulative_volume
        return cumulative_volume - previous


def _is_requested_future_record(record: object, underlying: Instrument, venue: str) -> bool:
    if not isinstance(record, Mapping):
        return False
    exchange = _text(record.get("exchange")).upper()
    segment = _text(record.get("segment")).upper()
    instrument_type = _text(record.get("instrument_type")).upper()
    if exchange != venue or segment != f"{venue}-FUT" or instrument_type != "FUT":
        return False
    name = _text(record.get("name")).upper()
    symbol = _text(record.get("tradingsymbol")).upper()
    roots = {
        Instrument.NIFTY: ("NIFTY",),
        Instrument.BANKNIFTY: ("BANKNIFTY", "NIFTY BANK"),
        Instrument.SENSEX: ("SENSEX",),
    }
    return name in roots[underlying] or any(symbol.startswith(root.replace(" ", "")) for root in roots[underlying])


def _contract_from_record(record: Mapping[str, object], underlying: Instrument, venue: str) -> FuturesVWAPContract:
    exchange_token = _positive_int(record.get("exchange_token"), "exchange_token")
    instrument_token = _positive_int(record.get("instrument_token"), "instrument_token")
    expiry = _expiry(record.get("expiry"))
    return FuturesVWAPContract(
        underlying=underlying,
        instrument_token=instrument_token,
        exchange_token=exchange_token,
        trading_symbol=_required_text(record.get("tradingsymbol"), "tradingsymbol"),
        source_exchange=venue,
        segment=f"{venue}-FUT",
        expiry=expiry,
    )


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            value = int(text)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _expiry(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value.strip())
    raise TypeError("expiry must be a date")


def _required_text(value: object, field_name: str) -> str:
    text = _text(value)
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _raw_token(row) -> int | None:
    token = row.get("instrument_token") if hasattr(row, "get") else None
    return token if isinstance(token, int) and not isinstance(token, bool) else None


def _raw_price(row) -> float:
    value = row.get("last_price") if hasattr(row, "get") else None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("last_price must be numeric")
    price = float(value)
    if not isfinite(price) or price <= 0:
        raise ValueError("last_price must be positive and finite")
    return price


def _raw_volume(row) -> int:
    value = row.get("volume_traded") if hasattr(row, "get") else None
    if value is None and hasattr(row, "get"):
        value = row.get("volume")
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            value = int(text)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("volume must be a positive integer")
    return value


def _current_completed_minute_bounds(clock) -> tuple[datetime, datetime] | None:
    now = _safe_now(clock).astimezone(IST)
    session_start = datetime.combine(now.date(), time(9, 15), tzinfo=IST)
    completed_end = now.replace(second=0, microsecond=0)
    if completed_end <= session_start:
        return None
    return session_start.astimezone(UTC), completed_end.astimezone(UTC)


def _trading_date(clock) -> date:
    return _safe_now(clock).astimezone(IST).date()


def _safe_now(clock) -> datetime:
    value = clock()
    if not isinstance(value, datetime):
        raise TypeError("clock result must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock result must be timezone-aware")
    return value


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _safe_error(exc: Exception, redactions: tuple[str | None, ...]) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    for secret in redactions:
        if secret:
            message = message.replace(secret, "[REDACTED]")
    if "{" in message or "}" in message:
        return message.split("{", 1)[0].strip()
    return message


def _rejected_contract_message(record: Mapping[str, object], exc: Exception) -> str:
    return (
        "Rejected contract: "
        f"reason={exc}; "
        f"tradingsymbol={_safe_field(record.get('tradingsymbol'))}; "
        f"instrument_token={_safe_field(record.get('instrument_token'))}; "
        f"exchange_token={_safe_field(record.get('exchange_token'))}"
    )


def _safe_field(value: object) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return text or "-"
