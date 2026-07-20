"""
Read-only Zerodha connectivity adapter.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from brokers.zerodha.market_data import ZerodhaInstrumentSubscription, ZerodhaSubscriptionMode, ZerodhaSubscriptionRegistry, ZerodhaTickNormalizer
from core import events
from core.base_engine import BaseEngine
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.models.tick import Tick

from .enums import ZerodhaConnectionState
from .models import (
    SUPPORTED_INSTRUMENTS,
    ZerodhaConnectionSnapshot,
    ZerodhaCredentials,
    ZerodhaInstrumentToken,
    ZerodhaSubscription,
)


def _default_clock() -> datetime:
    return datetime.now(UTC)


class ZerodhaReadOnlyAdapter(BaseEngine):
    def __init__(
        self,
        event_bus,
        *,
        auth_client=None,
        instrument_client=None,
        ticker_client=None,
        tick_consumer=None,
        clock=None,
    ):
        super().__init__(event_bus)
        self._auth_client = auth_client
        self._instrument_client = instrument_client
        self._ticker_client = ticker_client
        self._tick_consumer = tick_consumer
        self._clock = clock or _default_clock
        self._state = ZerodhaConnectionState.CREATED
        self._credentials: ZerodhaCredentials | None = None
        self._authenticated = False
        self._registry = ZerodhaSubscriptionRegistry()
        self._normalizer = ZerodhaTickNormalizer(self._registry, clock=self._now)
        self._resolved_tokens: tuple[ZerodhaInstrumentToken, ...] = ()
        self._subscribed_instruments: tuple[Instrument, ...] = ()
        self._seen_tick_identities: set[str] = set()
        self._received_tick_count = 0
        self._published_tick_count = 0
        self._rejected_tick_count = 0
        self._duplicate_tick_count = 0
        self._last_tick_at: datetime | None = None
        self._last_connected_at: datetime | None = None
        self._last_disconnected_at: datetime | None = None
        self._last_error_code: str | None = None

    def start(self) -> ZerodhaConnectionSnapshot:
        if self._state is ZerodhaConnectionState.CREATED:
            self._state = ZerodhaConnectionState.READY
        self._publish_state()
        return self.snapshot()

    def configure_credentials(
        self,
        credentials: ZerodhaCredentials,
    ) -> ZerodhaConnectionSnapshot:
        if not isinstance(credentials, ZerodhaCredentials):
            raise TypeError("credentials must be ZerodhaCredentials")
        self._credentials = credentials
        try:
            if self._auth_client is None:
                raise RuntimeError("read-only auth client is not configured")
            self._auth_client.set_access_token(credentials.access_token)
            profile = self._auth_client.profile()
            if not isinstance(profile, Mapping):
                raise TypeError("profile response must be a mapping")
            self._authenticated = True
            self._last_error_code = None
            if self._state is ZerodhaConnectionState.CREATED:
                self._state = ZerodhaConnectionState.READY
        except Exception as exc:
            self._authenticated = False
            self._state = ZerodhaConnectionState.FAILED
            self._last_error_code = self._safe_error_code(exc)
            self._event_bus.publish(events.ZERODHA_AUTHENTICATION_FAILED, self.snapshot())
            self._publish_state()
            return self.snapshot()
        self._publish_state()
        return self.snapshot()

    def load_instrument_tokens(self) -> ZerodhaConnectionSnapshot:
        if self._instrument_client is None:
            self._fail("instrument_client_missing")
            return self.snapshot()
        try:
            from brokers.zerodha.instruments.catalogue import ZerodhaInstrumentCatalogue
            from brokers.zerodha.instruments.normalizer import ZerodhaInstrumentNormalizer
            from brokers.zerodha.instruments.resolver import ZerodhaIndexSubscriptionResolver

            normalizer = ZerodhaInstrumentNormalizer()
            records = []
            for exchange in (Exchange.NSE, Exchange.BSE):
                records.extend(normalizer.normalize_many(self._instrument_client.instruments(exchange.value)))
            catalogue = ZerodhaInstrumentCatalogue(tuple(records))
            resolver = ZerodhaIndexSubscriptionResolver(catalogue)
            resolutions = resolver.resolve_many(SUPPORTED_INSTRUMENTS, mode=ZerodhaSubscriptionMode.FULL)
            tokens = tuple(
                ZerodhaInstrumentToken(
                    instrument=resolution.instrument,
                    exchange=resolution.record.exchange,
                    trading_symbol=resolution.record.tradingsymbol,
                    instrument_token=resolution.subscription.instrument_token,
                )
                for resolution in resolutions
            )
            subscriptions = tuple(resolution.subscription for resolution in resolutions)
            self._registry.replace(subscriptions)
            self._normalizer = ZerodhaTickNormalizer(self._registry, clock=self._now)
            self._resolved_tokens = tokens
            self._last_error_code = None
            self._publish_state()
            return self.snapshot()
        except Exception as exc:
            self._fail(self._safe_error_code(exc))
            return self.snapshot()

    def connect(self) -> ZerodhaConnectionSnapshot:
        if self._state in {ZerodhaConnectionState.STOPPED, ZerodhaConnectionState.FAILED}:
            raise RuntimeError("reset Zerodha adapter before connecting")
        if self._state in {ZerodhaConnectionState.CONNECTING, ZerodhaConnectionState.CONNECTED}:
            return self.snapshot()
        if self._state is ZerodhaConnectionState.CREATED:
            self.start()
        if not self._authenticated:
            self._fail("not_authenticated")
            return self.snapshot()
        if self._ticker_client is None:
            self._fail("ticker_client_missing")
            return self.snapshot()
        self._state = ZerodhaConnectionState.CONNECTING
        self._ticker_client.set_callbacks(
            on_connect=self.on_connect,
            on_ticks=self.on_ticks,
            on_close=self.on_close,
            on_error=self.on_error,
            on_reconnect=self.on_reconnect,
            on_noreconnect=self.on_noreconnect,
        )
        self._publish_state()
        try:
            self._ticker_client.connect(threaded=False)
        except Exception as exc:
            self._fail(self._safe_error_code(exc))
        return self.snapshot()

    def subscribe(
        self,
        instruments: tuple[str, ...],
    ) -> ZerodhaConnectionSnapshot:
        if self._state is not ZerodhaConnectionState.CONNECTED:
            raise RuntimeError("Zerodha subscriptions require CONNECTED state")
        requested = self._normalize_instruments(instruments)
        if not self._resolved_tokens:
            self.load_instrument_tokens()
        by_instrument = {token.instrument: token for token in self._resolved_tokens}
        missing_resolutions = tuple(instrument for instrument in requested if instrument not in by_instrument)
        if missing_resolutions:
            raise ValueError("requested instrument token is not resolved")
        current = set(self._subscribed_instruments)
        missing = tuple(instrument for instrument in requested if instrument not in current)
        if not missing:
            return self.snapshot()
        tokens = [by_instrument[instrument].instrument_token for instrument in missing]
        self._ticker_client.subscribe(tokens)
        self._ticker_client.set_mode(ZerodhaSubscriptionMode.FULL.value, tokens)
        self._subscribed_instruments = self._subscribed_instruments + missing
        self._event_bus.publish(events.ZERODHA_SUBSCRIPTION_UPDATED, self.snapshot())
        self._publish_state()
        return self.snapshot()

    def disconnect(self) -> ZerodhaConnectionSnapshot:
        if self._state is ZerodhaConnectionState.CONNECTED:
            self._ticker_client.close()
            self._state = ZerodhaConnectionState.DISCONNECTED
            self._last_disconnected_at = self._now()
            self._event_bus.publish(events.ZERODHA_DISCONNECTED, self.snapshot())
            self._publish_state()
        return self.snapshot()

    def stop(self) -> ZerodhaConnectionSnapshot:
        if self._state in {
            ZerodhaConnectionState.READY,
            ZerodhaConnectionState.CONNECTING,
            ZerodhaConnectionState.CONNECTED,
            ZerodhaConnectionState.DISCONNECTED,
        }:
            if self._state is ZerodhaConnectionState.CONNECTED and self._ticker_client is not None:
                self._ticker_client.close()
            self._state = ZerodhaConnectionState.STOPPED
            self._publish_state()
        return self.snapshot()

    def reset(self) -> ZerodhaConnectionSnapshot:
        if self._state in {ZerodhaConnectionState.FAILED, ZerodhaConnectionState.STOPPED}:
            self._state = ZerodhaConnectionState.READY
        self._authenticated = False
        self._credentials = None
        self._subscribed_instruments = ()
        self._seen_tick_identities = set()
        self._received_tick_count = 0
        self._published_tick_count = 0
        self._rejected_tick_count = 0
        self._duplicate_tick_count = 0
        self._last_tick_at = None
        self._last_connected_at = None
        self._last_disconnected_at = None
        self._last_error_code = None
        self._publish_state()
        return self.snapshot()

    def snapshot(self) -> ZerodhaConnectionSnapshot:
        return ZerodhaConnectionSnapshot(
            enabled=True,
            state=self._state,
            connected=self._state is ZerodhaConnectionState.CONNECTED,
            authenticated=self._authenticated,
            subscribed_instruments=self._subscribed_instruments,
            resolved_tokens=self._resolved_tokens,
            received_tick_count=self._received_tick_count,
            published_tick_count=self._published_tick_count,
            rejected_tick_count=self._rejected_tick_count,
            duplicate_tick_count=self._duplicate_tick_count,
            last_tick_at=self._last_tick_at,
            last_connected_at=self._last_connected_at,
            last_disconnected_at=self._last_disconnected_at,
            last_error_code=self._last_error_code,
        )

    def on_connect(self, ws=None, response=None) -> None:
        if self._is_terminal():
            return
        self._state = ZerodhaConnectionState.CONNECTED
        self._last_connected_at = self._now()
        self._last_error_code = None
        self._event_bus.publish(events.ZERODHA_CONNECTED, self.snapshot())
        self._publish_state()

    def on_ticks(self, ws=None, ticks=None) -> None:
        if self._is_terminal():
            return
        if self._state is not ZerodhaConnectionState.CONNECTED:
            return
        if isinstance(ticks, (str, bytes, Mapping)) or ticks is None:
            self._reject_tick("malformed_tick_batch")
            return
        for raw_tick in tuple(ticks):
            self._received_tick_count += 1
            try:
                tick = self._normalizer.normalize(raw_tick)
                identity = self._tick_identity(tick)
                if identity in self._seen_tick_identities:
                    self._duplicate_tick_count += 1
                    continue
                self._seen_tick_identities.add(identity)
                self._publish_tick(tick)
            except Exception as exc:
                self._reject_tick(self._safe_error_code(exc))
        self._publish_state()

    def on_close(self, ws=None, code=None, reason=None) -> None:
        if self._is_terminal():
            return
        self._state = ZerodhaConnectionState.DISCONNECTED
        self._last_disconnected_at = self._now()
        self._event_bus.publish(events.ZERODHA_DISCONNECTED, self.snapshot())
        self._publish_state()

    def on_error(self, ws=None, code=None, reason=None) -> None:
        if self._is_terminal():
            return
        self._fail("websocket_error")

    def on_reconnect(self, ws=None, attempts_count=None) -> None:
        if self._is_terminal():
            return
        self._publish_state()

    def on_noreconnect(self, ws=None) -> None:
        if self._is_terminal():
            return
        self._fail("websocket_reconnect_exhausted")

    def _publish_tick(self, tick: Tick) -> None:
        if self._tick_consumer is not None:
            self._tick_consumer(tick)
        else:
            self._event_bus.publish(events.NEW_TICK, tick)
        self._last_tick_at = tick.timestamp
        self._published_tick_count += 1

    def _reject_tick(self, code: str) -> None:
        self._rejected_tick_count += 1
        self._last_error_code = code[:120] or "tick_rejected"
        self._event_bus.publish(events.ZERODHA_TICK_REJECTED, self.snapshot())

    def _fail(self, code: str) -> None:
        self._state = ZerodhaConnectionState.FAILED
        self._last_error_code = code[:120] or "zerodha_connection_failed"
        self._event_bus.publish(events.ZERODHA_CONNECTION_FAILED, self.snapshot())
        self._publish_state()

    def _publish_state(self) -> None:
        snapshot = self.snapshot()
        self._data = snapshot
        self._event_bus.publish(events.ZERODHA_CONNECTION_STATE_UPDATED, snapshot)

    def _normalize_instruments(self, instruments: tuple[str, ...]) -> tuple[Instrument, ...]:
        if isinstance(instruments, (str, bytes)) or not isinstance(instruments, tuple) or not instruments:
            raise ValueError("instruments must be a non-empty tuple")
        normalized = []
        for instrument in instruments:
            value = Instrument.from_symbol(instrument.strip().upper()) if isinstance(instrument, str) else instrument
            if value not in SUPPORTED_INSTRUMENTS:
                raise ValueError("unsupported Zerodha read-only instrument")
            if value not in normalized:
                normalized.append(value)
        return tuple(normalized)

    def _tick_identity(self, tick: Tick) -> str:
        return "|".join(
            (
                tick.symbol.value,
                tick.exchange.value,
                tick.timestamp.isoformat(),
                str(tick.last_price),
                str(tick.volume),
                str(tick.bid_price),
                str(tick.ask_price),
                str(tick.open_interest),
            )
        )

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise TypeError("clock result must be datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock result must be timezone-aware")
        return value

    def _is_terminal(self) -> bool:
        return self._state in {
            ZerodhaConnectionState.STOPPED,
            ZerodhaConnectionState.FAILED,
        }

    def _safe_error_code(self, exc: Exception | str) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        if self._credentials is not None:
            for secret in (self._credentials.api_key, self._credentials.access_token):
                message = message.replace(secret, "[REDACTED]")
        if "{" in message or "}" in message:
            message = message.split("{", 1)[0].strip()
        return message[:120] or "zerodha_error"
