"""
Immutable option market-data subscription models.
"""

from dataclasses import dataclass
from datetime import date, datetime

from brokers.zerodha.market_data import ZerodhaInstrumentSubscription
from brokers.zerodha.option_market_data.enums import (
    ZerodhaOptionSubscriptionOperation,
    ZerodhaOptionSubscriptionStatus,
)
from brokers.zerodha.options import (
    ZerodhaDerivativeVenue,
    ZerodhaOptionContract,
    ZerodhaOptionRight,
    ZerodhaOptionUniverse,
)
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument


def _require_aware(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _non_negative(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be non-negative integer")
    return value


def _positive_unique_tokens(tokens: tuple[int, ...], field_name: str) -> tuple[int, ...]:
    values = tuple(tokens)
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must contain unique tokens")
    for token in values:
        if isinstance(token, bool) or not isinstance(token, int) or token <= 0:
            raise ValueError(f"{field_name} must contain positive integer tokens")
    return values


def _exchange_for_venue(venue: ZerodhaDerivativeVenue) -> Exchange:
    if venue is ZerodhaDerivativeVenue.NFO:
        return Exchange.NSE
    if venue is ZerodhaDerivativeVenue.BFO:
        return Exchange.BSE
    raise ValueError("unsupported derivative venue")


@dataclass(frozen=True, slots=True)
class ZerodhaOptionSubscriptionEntry:
    contract: ZerodhaOptionContract
    subscription: ZerodhaInstrumentSubscription

    def __post_init__(self) -> None:
        if not isinstance(self.contract, ZerodhaOptionContract):
            raise TypeError("contract must be ZerodhaOptionContract")
        if not isinstance(self.subscription, ZerodhaInstrumentSubscription):
            raise TypeError("subscription must be ZerodhaInstrumentSubscription")
        if self.contract.instrument_token != self.subscription.instrument_token:
            raise ValueError("subscription token must match contract token")
        if self.contract.underlying is not self.subscription.instrument:
            raise ValueError("subscription instrument must match contract underlying")
        if _exchange_for_venue(self.contract.venue) is not self.subscription.exchange:
            raise ValueError("subscription exchange must match derivative venue")


@dataclass(frozen=True, slots=True)
class ZerodhaOptionSubscriptionPlan:
    underlying: Instrument
    expiry: date
    current_entries: tuple[ZerodhaOptionSubscriptionEntry, ...]
    proposed_entries: tuple[ZerodhaOptionSubscriptionEntry, ...]
    subscribe_entries: tuple[ZerodhaOptionSubscriptionEntry, ...]
    unsubscribe_entries: tuple[ZerodhaOptionSubscriptionEntry, ...]
    mode_change_entries: tuple[ZerodhaOptionSubscriptionEntry, ...]
    unchanged_entries: tuple[ZerodhaOptionSubscriptionEntry, ...]

    def __post_init__(self) -> None:
        groups = (
            tuple(self.current_entries),
            tuple(self.proposed_entries),
            tuple(self.subscribe_entries),
            tuple(self.unsubscribe_entries),
            tuple(self.mode_change_entries),
            tuple(self.unchanged_entries),
        )
        for group in groups:
            _validate_entry_tuple(group)
        if not isinstance(self.underlying, Instrument):
            raise TypeError("underlying must be Instrument")
        if not isinstance(self.expiry, date) or isinstance(self.expiry, datetime):
            raise TypeError("expiry must be date")
        for entry in self.proposed_entries:
            if entry.contract.underlying is not self.underlying or entry.contract.expiry != self.expiry:
                raise ValueError("proposed entries must share plan underlying and expiry")
        action_sets = [
            {entry.subscription.instrument_token for entry in self.subscribe_entries},
            {entry.subscription.instrument_token for entry in self.unsubscribe_entries},
            {entry.subscription.instrument_token for entry in self.mode_change_entries},
            {entry.subscription.instrument_token for entry in self.unchanged_entries},
        ]
        if sum(len(items) for items in action_sets) != len(set().union(*action_sets)):
            raise ValueError("plan action token categories must be disjoint")
        current_tokens = {entry.subscription.instrument_token for entry in self.current_entries}
        proposed_tokens = {entry.subscription.instrument_token for entry in self.proposed_entries}
        explained_current = (
            {entry.subscription.instrument_token for entry in self.unsubscribe_entries}
            | {entry.subscription.instrument_token for entry in self.mode_change_entries}
            | {entry.subscription.instrument_token for entry in self.unchanged_entries}
        )
        explained_proposed = (
            {entry.subscription.instrument_token for entry in self.subscribe_entries}
            | {entry.subscription.instrument_token for entry in self.mode_change_entries}
            | {entry.subscription.instrument_token for entry in self.unchanged_entries}
        )
        if explained_current != current_tokens or explained_proposed != proposed_tokens:
            raise ValueError("plan actions must explain current-to-proposed transition")


@dataclass(frozen=True, slots=True)
class ZerodhaOptionSubscriptionBatchResult:
    operation: ZerodhaOptionSubscriptionOperation
    subscribed_tokens: tuple[int, ...]
    unsubscribed_tokens: tuple[int, ...]
    mode_updated_tokens: tuple[int, ...]
    active_tokens: tuple[int, ...]
    completed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.operation, ZerodhaOptionSubscriptionOperation):
            raise TypeError("operation must be ZerodhaOptionSubscriptionOperation")
        object.__setattr__(self, "subscribed_tokens", _positive_unique_tokens(self.subscribed_tokens, "subscribed_tokens"))
        object.__setattr__(self, "unsubscribed_tokens", _positive_unique_tokens(self.unsubscribed_tokens, "unsubscribed_tokens"))
        object.__setattr__(self, "mode_updated_tokens", _positive_unique_tokens(self.mode_updated_tokens, "mode_updated_tokens"))
        object.__setattr__(self, "active_tokens", _positive_unique_tokens(self.active_tokens, "active_tokens"))
        _require_aware(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class ZerodhaOptionSubscriptionSnapshot:
    status: ZerodhaOptionSubscriptionStatus
    underlying: Instrument | None
    expiry: date | None
    entries: tuple[ZerodhaOptionSubscriptionEntry, ...]
    active: bool
    prepared: bool
    operation_count: int
    successful_operation_count: int
    failed_operation_count: int
    activation_count: int
    replacement_count: int
    deactivation_count: int
    subscribed_token_count: int
    last_operation: ZerodhaOptionSubscriptionOperation | None
    last_result: ZerodhaOptionSubscriptionBatchResult | None
    last_started_at: datetime | None
    last_completed_at: datetime | None
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ZerodhaOptionSubscriptionStatus):
            raise TypeError("status must be ZerodhaOptionSubscriptionStatus")
        entries = tuple(self.entries)
        _validate_entry_tuple(entries)
        if self.underlying is not None and not isinstance(self.underlying, Instrument):
            raise TypeError("underlying must be Instrument or None")
        if self.expiry is not None and (not isinstance(self.expiry, date) or isinstance(self.expiry, datetime)):
            raise TypeError("expiry must be date or None")
        for name in (
            "operation_count",
            "successful_operation_count",
            "failed_operation_count",
            "activation_count",
            "replacement_count",
            "deactivation_count",
            "subscribed_token_count",
        ):
            _non_negative(getattr(self, name), name)
        if self.active and not entries:
            raise ValueError("active snapshot requires entries")
        if self.prepared and not entries:
            raise ValueError("prepared snapshot requires entries")
        if not entries and (self.underlying is not None or self.expiry is not None):
            raise ValueError("empty snapshot must not expose underlying or expiry")
        if self.last_operation is not None and not isinstance(self.last_operation, ZerodhaOptionSubscriptionOperation):
            raise TypeError("last_operation must be ZerodhaOptionSubscriptionOperation or None")
        if self.last_result is not None and not isinstance(self.last_result, ZerodhaOptionSubscriptionBatchResult):
            raise TypeError("last_result must be ZerodhaOptionSubscriptionBatchResult or None")
        _require_aware(self.last_started_at, "last_started_at")
        _require_aware(self.last_completed_at, "last_completed_at")
        if self.last_error is not None and not isinstance(self.last_error, str):
            raise TypeError("last_error must be str or None")
        object.__setattr__(self, "entries", entries)


def entries_from_universe(universe: ZerodhaOptionUniverse) -> tuple[ZerodhaOptionSubscriptionEntry, ...]:
    if not isinstance(universe, ZerodhaOptionUniverse):
        raise TypeError("universe must be ZerodhaOptionUniverse")
    contracts = []
    for pair in universe.pairs:
        contracts.extend((pair.call, pair.put))
    if len(contracts) != len(universe.subscriptions):
        raise ValueError("universe subscriptions must match pair contracts")
    entries = []
    for contract, subscription in zip(contracts, universe.subscriptions):
        if contract.instrument_token != subscription.instrument_token:
            raise ValueError("subscription token mismatch")
        entries.append(ZerodhaOptionSubscriptionEntry(contract, subscription))
    return tuple(entries)


def _validate_entry_tuple(entries: tuple[ZerodhaOptionSubscriptionEntry, ...]) -> None:
    tokens = set()
    for entry in entries:
        if not isinstance(entry, ZerodhaOptionSubscriptionEntry):
            raise TypeError("entries must contain ZerodhaOptionSubscriptionEntry values")
        token = entry.subscription.instrument_token
        if token in tokens:
            raise ValueError("duplicate subscription token")
        tokens.add(token)
