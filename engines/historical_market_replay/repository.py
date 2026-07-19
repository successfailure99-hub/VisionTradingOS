from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path

from application.enums import RuntimeInstrument
from core.enums.exchange import Exchange
from core.enums.instrument import Instrument
from core.models.tick import Tick
from engines.historical_market_replay.enums import ReplayRecordType
from engines.historical_market_replay.models import ReplayManifest, ReplayRecord
from engines.option_chain.enums import OptionType, PositioningBias, PressureType
from engines.option_chain.models import OptionChainSnapshot, OptionChainState, OptionLeg, OptionStrike, StrikeMetric


SCHEMA_VERSION = 1


class HistoricalReplayRepository:
    def __init__(self, output_dir: Path | str):
        self._output_dir = Path(output_dir)
        self._report_writes = 0
        self._failures = 0

    @property
    def report_writes(self) -> int:
        return self._report_writes

    @property
    def failures(self) -> int:
        return self._failures

    def load_session(self, path: Path | str) -> tuple[ReplayManifest, tuple[ReplayRecord, ...]]:
        source = Path(path)
        try:
            lines = source.read_text(encoding="utf-8").splitlines()
        except Exception as exc:
            self._failures += 1
            raise ValueError("Historical replay session file is not readable.") from exc
        if not lines or not lines[0].strip():
            self._failures += 1
            raise ValueError("Historical replay session is empty.")
        try:
            manifest_raw = json.loads(lines[0])
            record_rows = [json.loads(line) for line in lines[1:] if line.strip()]
        except Exception as exc:
            self._failures += 1
            raise ValueError("Malformed historical replay JSON.") from exc
        manifest = self._manifest(manifest_raw)
        records = tuple(self._record(row, manifest) for row in record_rows)
        self._validate_session(manifest, records)
        return manifest, records

    def write_report(self, report) -> Path:
        path = self._output_dir / f"{report.session_id}.json"
        payload = self._json_bytes({"schema_version": SCHEMA_VERSION, "report": report})
        try:
            _atomic_replace(path, payload)
        except Exception:
            self._failures += 1
            raise
        self._report_writes += 1
        return path

    def load_report(self, path: Path | str) -> dict[str, object]:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            self._failures += 1
            raise ValueError("Malformed historical replay report.") from exc
        if payload.get("schema_version") != SCHEMA_VERSION:
            self._failures += 1
            raise ValueError("Unsupported historical replay report schema.")
        return payload

    def _manifest(self, row: dict) -> ReplayManifest:
        if row.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported historical replay schema.")
        required = ("session_id", "trading_date", "timezone", "instruments", "created_at", "record_count", "source")
        if any(name not in row for name in required):
            raise ValueError("Malformed historical replay manifest.")
        for name in ("session_id", "timezone", "source"):
            if not isinstance(row[name], str) or not row[name].strip():
                raise ValueError("Historical replay manifest values must be non-empty strings.")
        try:
            instruments = tuple(RuntimeInstrument(str(item).strip().upper()) for item in row["instruments"])
        except Exception as exc:
            raise ValueError("Historical replay supports only NIFTY, BANKNIFTY, and SENSEX.") from exc
        return ReplayManifest(
            session_id=str(row["session_id"]).strip(),
            trading_date=date.fromisoformat(str(row["trading_date"])),
            timezone=str(row["timezone"]).strip(),
            instruments=instruments,
            created_at=_parse_aware(row["created_at"], "created_at"),
            record_count=int(row["record_count"]),
            source=str(row["source"]).strip(),
        )

    def _record(self, row: dict, manifest: ReplayManifest) -> ReplayRecord:
        if row.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported historical replay record schema.")
        try:
            record_type = ReplayRecordType(str(row.get("record_type", "")).strip().upper())
        except Exception as exc:
            raise ValueError("Historical replay record_type is unsupported.") from exc
        timestamp = _parse_aware(row.get("event_timestamp"), "event_timestamp")
        try:
            instrument = RuntimeInstrument(str(row.get("instrument", "")).strip().upper())
        except Exception as exc:
            raise ValueError("Historical replay supports only NIFTY, BANKNIFTY, and SENSEX.") from exc
        if instrument not in manifest.instruments:
            raise ValueError("Replay record instrument is outside manifest instruments.")
        payload = row.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("Replay record payload must be an object.")
        if record_type is ReplayRecordType.TICK:
            value = _tick(instrument, timestamp, payload)
        else:
            value = _option_chain(instrument, timestamp, payload)
        return ReplayRecord(sequence=int(row.get("sequence")), record_type=record_type, event_timestamp=timestamp, instrument=instrument, payload=value)

    def _validate_session(self, manifest: ReplayManifest, records: tuple[ReplayRecord, ...]) -> None:
        if not records:
            raise ValueError("Historical replay session is empty.")
        if manifest.record_count != len(records):
            raise ValueError("Historical replay record_count mismatch.")
        seen_sequences = set()
        seen_identity = set()
        previous_key = None
        for record in records:
            if record.sequence in seen_sequences:
                raise ValueError("Duplicate historical replay sequence.")
            seen_sequences.add(record.sequence)
            key = (record.event_timestamp, record.sequence)
            if previous_key is not None and key < previous_key:
                raise ValueError("Historical replay records must be ordered by timestamp and sequence.")
            previous_key = key
            if record.event_timestamp.date() != manifest.trading_date:
                raise ValueError("Historical replay record trading date mismatch.")
            identity = (record.record_type, record.instrument, record.event_timestamp, _identity_payload(record.payload))
            if identity in seen_identity:
                raise ValueError("Duplicate historical replay record identity.")
            seen_identity.add(identity)

    def _json_bytes(self, payload: dict[str, object]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default).encode("utf-8")


def _tick(instrument: RuntimeInstrument, timestamp: datetime, payload: dict) -> Tick:
    price = _finite_positive(payload.get("last_price"), "last_price")
    volume = _non_negative_int(payload.get("volume", 0), "volume")
    open_interest = _non_negative_int(payload.get("open_interest", 0), "open_interest")
    bid = _finite_positive(payload.get("bid_price", price), "bid_price")
    ask = _finite_positive(payload.get("ask_price", price), "ask_price")
    if bid > ask:
        raise ValueError("Tick bid_price cannot exceed ask_price.")
    exchange = Exchange(str(payload.get("exchange", "NSE")).strip().upper())
    return Tick(Instrument(instrument.value), exchange, timestamp, price, volume, bid, ask, open_interest)


def _option_chain(instrument: RuntimeInstrument, timestamp: datetime, payload: dict):
    expiry = date.fromisoformat(str(payload["expiry_date"]))
    strikes = tuple(_strike(row) for row in tuple(payload.get("strikes", ()) or ()))
    if not strikes:
        raise ValueError("Option-chain replay payload requires strikes.")
    values = tuple(strike.strike_price for strike in strikes)
    if values != tuple(sorted(values)) or len(set(values)) != len(values):
        raise ValueError("Option-chain strikes must be ordered and unique.")
    common = dict(
        symbol=instrument.value,
        exchange=str(payload.get("exchange", "NSE")).strip().upper(),
        expiry_date=expiry,
        timestamp=timestamp,
        underlying_price=_finite_positive(payload.get("underlying_price"), "underlying_price"),
        strikes=strikes,
    )
    if "atm_strike" not in payload:
        return OptionChainSnapshot(**common)
    return OptionChainState(
        common["symbol"], common["exchange"], expiry, timestamp, common["underlying_price"],
        float(payload["atm_strike"]), int(payload.get("strike_count", len(strikes))),
        _non_negative_int(payload.get("total_call_oi", 0), "total_call_oi"),
        _non_negative_int(payload.get("total_put_oi", 0), "total_put_oi"),
        _non_negative_int(payload.get("total_call_change_oi", 0), "total_call_change_oi"),
        _non_negative_int(payload.get("total_put_change_oi", 0), "total_put_change_oi"),
        payload.get("oi_pcr"), payload.get("change_oi_pcr"),
        _metric(payload.get("max_call_oi")), _metric(payload.get("max_put_oi")),
        _metric(payload.get("max_call_change_oi")), _metric(payload.get("max_put_change_oi")),
        payload.get("resistance_strike"), payload.get("support_strike"), payload.get("max_pain_strike"),
        PressureType(str(payload.get("call_pressure", "unknown")).lower()),
        PressureType(str(payload.get("put_pressure", "unknown")).lower()),
        PositioningBias(str(payload.get("positioning_bias", "unknown")).lower()),
        strikes,
    )


def _strike(row: dict) -> OptionStrike:
    strike = _finite_positive(row.get("strike_price"), "strike_price")
    call = _leg(row.get("call"), OptionType.CALL)
    put = _leg(row.get("put"), OptionType.PUT)
    return OptionStrike(strike, call, put)


def _leg(row, option_type: OptionType):
    if row is None:
        return None
    leg = OptionLeg(
        option_type,
        _finite_positive(row.get("last_price"), "last_price"),
        _non_negative_int(row.get("open_interest", 0), "open_interest"),
        int(row.get("change_in_open_interest", 0)),
        _non_negative_int(row.get("volume", 0), "volume"),
        row.get("bid_price"),
        row.get("ask_price"),
    )
    if leg.bid_price is not None and leg.ask_price is not None and leg.bid_price > leg.ask_price:
        raise ValueError("Option bid_price cannot exceed ask_price.")
    return leg


def _metric(row):
    if row is None:
        return None
    return StrikeMetric(float(row["strike_price"]), _non_negative_int(row.get("value", 0), "value"))


def _parse_aware(value, name: str) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


def _finite_positive(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


def _non_negative_int(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _identity_payload(payload) -> str:
    return str((payload.__class__.__name__, getattr(payload, "symbol", None), getattr(payload, "timestamp", None), getattr(payload, "last_price", None), getattr(payload, "strikes", None)))


def _json_default(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.name
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temp_name, path)


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        try:
            written = os.write(fd, view)
        except InterruptedError:
            continue
        if written <= 0:
            raise OSError("Unable to persist historical replay report.")
        view = view[written:]
