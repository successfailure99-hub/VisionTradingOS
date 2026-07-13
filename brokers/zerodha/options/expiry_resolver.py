"""
Expiry listing, classification, and selection.
"""

from datetime import date, datetime

from brokers.zerodha.options.catalogue import ZerodhaOptionContractCatalogue
from brokers.zerodha.options.enums import ZerodhaExpiryKind, ZerodhaExpirySelection
from brokers.zerodha.options.models import ZerodhaExpiry, require_supported_underlying
from core.enums.instrument import Instrument


class ZerodhaOptionExpiryResolver:
    def __init__(self, catalogue: ZerodhaOptionContractCatalogue):
        if not isinstance(catalogue, ZerodhaOptionContractCatalogue):
            raise TypeError("catalogue must be ZerodhaOptionContractCatalogue")
        self._catalogue = catalogue

    def list_expiries(self, underlying: Instrument, *, as_of: date) -> tuple[ZerodhaExpiry, ...]:
        require_supported_underlying(underlying)
        as_of = _date(as_of, "as_of")
        expiry_dates = self._catalogue.expiries(underlying, as_of=as_of)
        if not expiry_dates:
            return ()
        monthly_dates = {}
        for expiry in expiry_dates:
            key = (expiry.year, expiry.month)
            monthly_dates[key] = max(expiry, monthly_dates.get(key, expiry))
        items = []
        for expiry in expiry_dates:
            contracts = self._catalogue.contracts_for(underlying, expiry=expiry)
            strikes = sorted({contract.strike for contract in contracts})
            kind = ZerodhaExpiryKind.MONTHLY if monthly_dates[(expiry.year, expiry.month)] == expiry else ZerodhaExpiryKind.WEEKLY
            items.append(
                ZerodhaExpiry(
                    underlying=underlying,
                    expiry=expiry,
                    kind=kind,
                    contract_count=len(contracts),
                    strike_count=len(strikes),
                    first_strike=strikes[0],
                    last_strike=strikes[-1],
                )
            )
        return tuple(items)

    def resolve(
        self,
        underlying: Instrument,
        *,
        as_of: date,
        selection: ZerodhaExpirySelection = ZerodhaExpirySelection.CURRENT,
        explicit_expiry: date | None = None,
    ) -> ZerodhaExpiry:
        if not isinstance(selection, ZerodhaExpirySelection):
            raise TypeError("selection must be ZerodhaExpirySelection")
        if explicit_expiry is not None and selection is not ZerodhaExpirySelection.EXPLICIT:
            raise ValueError("explicit_expiry is allowed only with EXPLICIT selection")
        expiries = self.list_expiries(underlying, as_of=as_of)
        if not expiries:
            raise ValueError("no available expiry")
        if selection is ZerodhaExpirySelection.EXPLICIT:
            if explicit_expiry is None:
                raise ValueError("explicit_expiry is required")
            explicit_expiry = _date(explicit_expiry, "explicit_expiry")
            if explicit_expiry < _date(as_of, "as_of"):
                raise ValueError("explicit expiry is expired")
            for expiry in expiries:
                if expiry.expiry == explicit_expiry:
                    return expiry
            raise ValueError("explicit expiry not found")
        if selection is ZerodhaExpirySelection.CURRENT:
            return expiries[0]
        if selection is ZerodhaExpirySelection.NEXT:
            return _nth(expiries, 1, "next expiry not found")
        if selection in (ZerodhaExpirySelection.CURRENT_WEEKLY, ZerodhaExpirySelection.NEXT_WEEKLY):
            weekly = tuple(expiry for expiry in expiries if expiry.kind is ZerodhaExpiryKind.WEEKLY)
            return _nth(weekly, 0 if selection is ZerodhaExpirySelection.CURRENT_WEEKLY else 1, "weekly expiry not found")
        monthly = tuple(expiry for expiry in expiries if expiry.kind is ZerodhaExpiryKind.MONTHLY)
        return _nth(monthly, 0 if selection is ZerodhaExpirySelection.CURRENT_MONTHLY else 1, "monthly expiry not found")


def _date(value: date, field_name: str) -> date:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError(f"{field_name} must be date")
    return value


def _nth(values: tuple[ZerodhaExpiry, ...], index: int, message: str) -> ZerodhaExpiry:
    try:
        return values[index]
    except IndexError as exc:
        raise ValueError(message) from exc
