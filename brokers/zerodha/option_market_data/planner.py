"""
Pure option subscription transition planner.
"""

from brokers.zerodha.option_market_data.models import (
    ZerodhaOptionSubscriptionEntry,
    ZerodhaOptionSubscriptionPlan,
)


class ZerodhaOptionSubscriptionPlanner:
    def plan(
        self,
        current_entries: tuple[ZerodhaOptionSubscriptionEntry, ...],
        proposed_entries: tuple[ZerodhaOptionSubscriptionEntry, ...],
    ) -> ZerodhaOptionSubscriptionPlan:
        current = tuple(current_entries)
        proposed = tuple(proposed_entries)
        if not proposed:
            raise ValueError("proposed_entries must not be empty")
        _validate_group(current, allow_empty=True)
        _validate_group(proposed, allow_empty=False)
        current_by_token = {entry.subscription.instrument_token: entry for entry in current}
        proposed_by_token = {entry.subscription.instrument_token: entry for entry in proposed}
        for token, proposed_entry in proposed_by_token.items():
            current_entry = current_by_token.get(token)
            if current_entry is not None and current_entry.contract != proposed_entry.contract:
                raise ValueError("token identity collision")
        subscribe = tuple(entry for entry in proposed if entry.subscription.instrument_token not in current_by_token)
        unsubscribe = tuple(entry for entry in current if entry.subscription.instrument_token not in proposed_by_token)
        mode_change = tuple(
            entry
            for entry in proposed
            if entry.subscription.instrument_token in current_by_token
            and current_by_token[entry.subscription.instrument_token].subscription.mode is not entry.subscription.mode
        )
        unchanged = tuple(
            entry
            for entry in proposed
            if entry.subscription.instrument_token in current_by_token
            and current_by_token[entry.subscription.instrument_token].subscription.mode is entry.subscription.mode
        )
        return ZerodhaOptionSubscriptionPlan(
            underlying=proposed[0].contract.underlying,
            expiry=proposed[0].contract.expiry,
            current_entries=current,
            proposed_entries=proposed,
            subscribe_entries=subscribe,
            unsubscribe_entries=unsubscribe,
            mode_change_entries=mode_change,
            unchanged_entries=unchanged,
        )


def _validate_group(entries: tuple[ZerodhaOptionSubscriptionEntry, ...], *, allow_empty: bool) -> None:
    if not entries and not allow_empty:
        raise ValueError("entries must not be empty")
    tokens = set()
    underlying = None
    expiry = None
    for entry in entries:
        if not isinstance(entry, ZerodhaOptionSubscriptionEntry):
            raise TypeError("entries must contain ZerodhaOptionSubscriptionEntry values")
        token = entry.subscription.instrument_token
        if token in tokens:
            raise ValueError("duplicate token")
        tokens.add(token)
        if underlying is None:
            underlying = entry.contract.underlying
            expiry = entry.contract.expiry
        elif entry.contract.underlying is not underlying or entry.contract.expiry != expiry:
            raise ValueError("entries must share one underlying and expiry")
