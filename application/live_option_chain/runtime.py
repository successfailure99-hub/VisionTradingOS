"""
Live Option Chain Runtime V1.
"""

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from threading import RLock

from application.live_option_chain.assembler import (
    IncompleteLiveOptionChainError,
    LiveOptionChainAssembler,
    StaleLiveOptionQuoteError,
)
from application.live_option_chain.configuration import LiveOptionChainConfiguration
from application.live_option_chain.enums import LiveOptionChainStatus, LiveOptionQuoteUpdateResult
from application.live_option_chain.models import LiveOptionChainSnapshot, LiveOptionQuoteBatchResult
from application.live_option_chain.normalizer import ZerodhaLiveOptionQuoteNormalizer
from application.live_option_chain.quote_store import LiveOptionQuoteStore
from brokers.zerodha.option_market_data import (
    ZerodhaOptionMarketDataSubscriptionManager,
    entries_from_universe,
)
from brokers.zerodha.options import ZerodhaOptionUniverse
from engines.option_chain.option_chain_engine import OptionChainEngine


class LiveOptionChainRuntime:
    def __init__(
        self,
        *,
        universe: ZerodhaOptionUniverse,
        subscription_manager: ZerodhaOptionMarketDataSubscriptionManager,
        option_chain_engine: OptionChainEngine,
        configuration: LiveOptionChainConfiguration | None = None,
        normalizer: ZerodhaLiveOptionQuoteNormalizer | None = None,
        quote_store: LiveOptionQuoteStore | None = None,
        assembler: LiveOptionChainAssembler | None = None,
        clock=None,
    ):
        if not isinstance(universe, ZerodhaOptionUniverse):
            raise TypeError("universe must be ZerodhaOptionUniverse")
        if not isinstance(subscription_manager, ZerodhaOptionMarketDataSubscriptionManager):
            raise TypeError("subscription_manager must be ZerodhaOptionMarketDataSubscriptionManager")
        if not isinstance(option_chain_engine, OptionChainEngine):
            raise TypeError("option_chain_engine must be OptionChainEngine")
        self._lock = RLock()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._universe = universe
        self._subscription_manager = subscription_manager
        self._option_chain_engine = option_chain_engine
        self._configuration = configuration or LiveOptionChainConfiguration()
        if not isinstance(self._configuration, LiveOptionChainConfiguration):
            raise TypeError("configuration must be LiveOptionChainConfiguration")
        entries = self._active_entries(require_active=False)
        self._validate_entries(universe, entries)
        self._normalizer = normalizer or ZerodhaLiveOptionQuoteNormalizer(
            entries=entries,
            clock=self._clock,
            reject_crossed_market=self._configuration.reject_crossed_market,
        )
        self._quote_store = quote_store or LiveOptionQuoteStore(entries, clock=self._clock)
        self._assembler = assembler or LiveOptionChainAssembler(
            universe=universe,
            configuration=self._configuration,
        )
        self._status = LiveOptionChainStatus.CREATED
        self._received_tick_count = 0
        self._accepted_tick_count = 0
        self._duplicate_tick_count = 0
        self._stale_tick_count = 0
        self._rejected_tick_count = 0
        self._assembly_count = 0
        self._engine_update_count = 0
        self._last_batch_result: LiveOptionQuoteBatchResult | None = None
        self._last_received_at: datetime | None = None
        self._last_assembled_at: datetime | None = None
        self._last_error: str | None = None
        self._latest_option_chain_snapshot = None
        self._latest_option_chain_analysis = None

    def start(self) -> LiveOptionChainSnapshot:
        with self._lock:
            self._validate_entries(self._universe, self._active_entries(require_active=True))
            self._status = (
                LiveOptionChainStatus.READY
                if self._latest_option_chain_snapshot is not None
                else LiveOptionChainStatus.COLLECTING
            )
            return self.snapshot()

    def stop(self) -> LiveOptionChainSnapshot:
        with self._lock:
            self._status = LiveOptionChainStatus.STOPPED
            return self.snapshot()

    def set_underlying_price(
        self,
        price: float,
        *,
        timestamp: datetime | None = None,
    ) -> LiveOptionChainSnapshot:
        with self._lock:
            self._quote_store.set_underlying_price(price, timestamp=timestamp or self._now())
            return self.snapshot()

    def seed_open_interest_baselines(
        self,
        baselines: Mapping[int, int],
    ) -> LiveOptionChainSnapshot:
        with self._lock:
            self._quote_store.seed_open_interest_baselines(baselines)
            return self.snapshot()

    def process_raw_ticks(
        self,
        raw_ticks: Iterable[Mapping[str, object]],
    ) -> LiveOptionQuoteBatchResult:
        if isinstance(raw_ticks, (str, bytes, Mapping)):
            raise TypeError("raw_ticks must be an iterable of mappings")
        rows = tuple(raw_ticks)
        with self._lock:
            if self._status not in (
                LiveOptionChainStatus.COLLECTING,
                LiveOptionChainStatus.PARTIAL,
                LiveOptionChainStatus.READY,
                LiveOptionChainStatus.STALE,
            ):
                raise RuntimeError("LiveOptionChainRuntime must be started")
            self._active_entries(require_active=True)
            accepted = []
            duplicate = stale = rejected = 0
            for row in rows:
                self._received_tick_count += 1
                try:
                    token = _raw_token(row)
                    oi = _raw_oi(row)
                    baseline = self._quote_store.baseline_for(token, current_open_interest=oi)
                    quote = self._normalizer.normalize(row, baseline_open_interest=baseline)
                    result = self._quote_store.update(quote)
                    self._last_received_at = quote.received_at
                    if result is LiveOptionQuoteUpdateResult.ACCEPTED:
                        self._accepted_tick_count += 1
                        accepted.append(quote)
                    elif result is LiveOptionQuoteUpdateResult.DUPLICATE:
                        self._duplicate_tick_count += 1
                        duplicate += 1
                    else:
                        self._stale_tick_count += 1
                        stale += 1
                except Exception as exc:
                    self._rejected_tick_count += 1
                    rejected += 1
                    if self._last_error is None:
                        self._last_error = _safe_error(exc)
            assembled = False
            engine_updated = False
            if accepted:
                assembled, engine_updated = self._try_assemble()
            elif self._latest_option_chain_snapshot is None:
                self._status = LiveOptionChainStatus.COLLECTING
            result = LiveOptionQuoteBatchResult(
                received_count=len(rows),
                accepted_quotes=tuple(accepted),
                duplicate_count=duplicate,
                stale_count=stale,
                rejected_count=rejected,
                assembled=assembled,
                engine_updated=engine_updated,
            )
            self._last_batch_result = result
            return result

    def replace_universe(
        self,
        universe: ZerodhaOptionUniverse,
    ) -> LiveOptionChainSnapshot:
        if not isinstance(universe, ZerodhaOptionUniverse):
            raise TypeError("universe must be ZerodhaOptionUniverse")
        with self._lock:
            old_state = (
                self._universe,
                self._normalizer,
                self._quote_store,
                self._assembler,
                self._latest_option_chain_snapshot,
                self._latest_option_chain_analysis,
                self._status,
            )
            try:
                entries = self._active_entries(require_active=True)
                self._validate_entries(universe, entries)
                self._universe = universe
                self._normalizer = ZerodhaLiveOptionQuoteNormalizer(
                    entries=entries,
                    clock=self._clock,
                    reject_crossed_market=self._configuration.reject_crossed_market,
                )
                self._quote_store.reset(entries)
                self._assembler = LiveOptionChainAssembler(
                    universe=universe,
                    configuration=self._configuration,
                )
                self._option_chain_engine.reset()
                self._latest_option_chain_snapshot = None
                self._latest_option_chain_analysis = None
                self._status = LiveOptionChainStatus.COLLECTING
                return self.snapshot()
            except Exception as exc:
                (
                    self._universe,
                    self._normalizer,
                    self._quote_store,
                    self._assembler,
                    self._latest_option_chain_snapshot,
                    self._latest_option_chain_analysis,
                    self._status,
                ) = old_state
                self._last_error = _safe_error(exc)
                raise

    def snapshot(self) -> LiveOptionChainSnapshot:
        with self._lock:
            quotes = self._quote_store.all_latest()
            now = self._now()
            fresh_count = sum(
                1
                for quote in quotes
                if (now - quote.exchange_timestamp).total_seconds()
                <= self._configuration.maximum_quote_age_seconds
            )
            complete_pairs = _complete_pair_count(self._universe, quotes)
            return LiveOptionChainSnapshot(
                status=self._status,
                underlying=self._universe.underlying,
                expiry=self._universe.expiry.expiry,
                configured_token_count=len(entries_from_universe(self._universe)),
                quoted_token_count=len(quotes),
                fresh_token_count=fresh_count,
                complete_pair_count=complete_pairs,
                expected_pair_count=len(self._universe.pairs),
                received_tick_count=self._received_tick_count,
                accepted_tick_count=self._accepted_tick_count,
                duplicate_tick_count=self._duplicate_tick_count,
                stale_tick_count=self._stale_tick_count,
                rejected_tick_count=self._rejected_tick_count,
                assembly_count=self._assembly_count,
                engine_update_count=self._engine_update_count,
                underlying_price=self._quote_store.underlying_price,
                latest_quotes=quotes,
                latest_option_chain_snapshot=self._latest_option_chain_snapshot,
                latest_option_chain_analysis=self._latest_option_chain_analysis,
                last_batch_result=self._last_batch_result,
                last_received_at=self._last_received_at,
                last_assembled_at=self._last_assembled_at,
                last_error=self._last_error,
            )

    def clear(self) -> LiveOptionChainSnapshot:
        with self._lock:
            if self._status is not LiveOptionChainStatus.STOPPED:
                raise RuntimeError("clear requires stopped runtime")
            entries = entries_from_universe(self._universe)
            self._quote_store.reset(entries)
            self._option_chain_engine.reset()
            self._received_tick_count = 0
            self._accepted_tick_count = 0
            self._duplicate_tick_count = 0
            self._stale_tick_count = 0
            self._rejected_tick_count = 0
            self._assembly_count = 0
            self._engine_update_count = 0
            self._last_batch_result = None
            self._last_received_at = None
            self._last_assembled_at = None
            self._last_error = None
            self._latest_option_chain_snapshot = None
            self._latest_option_chain_analysis = None
            self._status = LiveOptionChainStatus.CLEARED
            return self.snapshot()

    def _try_assemble(self) -> tuple[bool, bool]:
        price = self._quote_store.underlying_price
        if price is None:
            self._status = LiveOptionChainStatus.PARTIAL
            return False, False
        try:
            now = self._now()
            snapshot = self._assembler.assemble(
                quotes=self._quote_store.all_latest(),
                underlying_price=price,
                timestamp=now,
            )
        except StaleLiveOptionQuoteError as exc:
            self._status = LiveOptionChainStatus.STALE
            self._last_error = _safe_error(exc)
            return False, False
        except IncompleteLiveOptionChainError:
            self._status = LiveOptionChainStatus.PARTIAL
            return False, False
        previous_engine_snapshot = self._option_chain_engine.snapshot
        state = self._option_chain_engine.process(snapshot)
        self._latest_option_chain_snapshot = snapshot
        self._latest_option_chain_analysis = state
        self._last_assembled_at = snapshot.timestamp
        self._assembly_count += 1
        engine_updated = self._option_chain_engine.snapshot != previous_engine_snapshot
        if engine_updated:
            self._engine_update_count += 1
        self._status = LiveOptionChainStatus.READY
        return True, engine_updated

    def _active_entries(self, *, require_active: bool):
        snapshot = self._subscription_manager.snapshot()
        if require_active and not snapshot.active:
            raise RuntimeError("active option subscriptions are required")
        return snapshot.entries

    def _validate_entries(self, universe: ZerodhaOptionUniverse, entries) -> None:
        expected = entries_from_universe(universe)
        if tuple(entry.subscription.instrument_token for entry in entries) != tuple(
            entry.subscription.instrument_token for entry in expected
        ):
            raise ValueError("subscription manager tokens do not match option universe")
        if entries and (entries[0].contract.underlying is not universe.underlying or entries[0].contract.expiry != universe.expiry.expiry):
            raise ValueError("subscription manager context does not match option universe")

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock result must be datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock result must be timezone-aware")
        return value


def _raw_token(row) -> int:
    if not isinstance(row, Mapping):
        raise TypeError("raw option tick must be mapping")
    token = row.get("instrument_token")
    if isinstance(token, bool) or not isinstance(token, int) or token <= 0:
        raise ValueError("instrument_token must be positive integer")
    return token


def _raw_oi(row) -> int:
    if not isinstance(row, Mapping):
        raise TypeError("raw option tick must be mapping")
    oi = row.get("oi", 0)
    if isinstance(oi, bool) or not isinstance(oi, int) or oi < 0:
        raise ValueError("oi must be non-negative integer")
    return oi


def _complete_pair_count(universe: ZerodhaOptionUniverse, quotes) -> int:
    tokens = {quote.instrument_token for quote in quotes}
    return sum(
        1
        for pair in universe.pairs
        if pair.call.instrument_token in tokens and pair.put.instrument_token in tokens
    )


def _safe_error(exc: Exception) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    if "{" in message or "}" in message:
        return message.split("{", 1)[0].strip()
    return message
