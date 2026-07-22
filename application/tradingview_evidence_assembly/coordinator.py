"""
TradingView Evidence Assembly Coordinator V1.
"""

from __future__ import annotations

from datetime import datetime
import hashlib

from application.enums import RuntimeInstrument
from engines.tradingview_evidence.engine import TradingViewEvidenceMappingEngine
from engines.tradingview_evidence.models import TradingViewEvidenceRequest, TradingViewEvidenceSnapshot, evidence_timestamp

from .models import TradingViewEvidenceAssemblyInput, TradingViewEvidenceAssemblySnapshot


class TradingViewEvidenceAssemblyCoordinator:
    """
    Collects canonical runtime outputs and delegates snapshot mapping.

    This coordinator performs no indicator, price-action, option-chain, or
    market-context calculation. It only waits for the minimum live chart inputs,
    builds a deterministic request, and lets the TradingView Evidence Mapping
    Engine publish the mapped or partial immutable snapshot.
    """

    def __init__(
        self,
        *,
        instrument: RuntimeInstrument,
        timeframe: str,
        mapping_engine: TradingViewEvidenceMappingEngine,
    ):
        if not isinstance(instrument, RuntimeInstrument):
            raise TypeError("instrument must be RuntimeInstrument")
        if not isinstance(timeframe, str) or not timeframe.strip():
            raise ValueError("timeframe must be non-empty text")
        if not isinstance(mapping_engine, TradingViewEvidenceMappingEngine):
            raise TypeError("mapping_engine must be TradingViewEvidenceMappingEngine")
        self._instrument = instrument
        self._timeframe = timeframe.strip()
        self._mapping_engine = mapping_engine
        self._enabled = True
        self._assembled_count = 0
        self._skipped_count = 0
        self._duplicate_count = 0
        self._last_fingerprint: str | None = None
        self._last_evidence: TradingViewEvidenceSnapshot | None = None
        self._last_wait_reason: str | None = None

    def assemble(self, source: TradingViewEvidenceAssemblyInput) -> TradingViewEvidenceSnapshot | None:
        if not isinstance(source, TradingViewEvidenceAssemblyInput):
            raise TypeError("source must be TradingViewEvidenceAssemblyInput")
        if source.instrument is not self._instrument:
            raise ValueError("assembly input instrument does not match coordinator")
        if source.timeframe != self._timeframe:
            raise ValueError("assembly input timeframe does not match coordinator")
        wait_reason = self._wait_reason(source)
        if wait_reason is not None:
            self._skipped_count += 1
            self._last_wait_reason = wait_reason
            return None

        request = self._request(source)
        fingerprint = request.fingerprint()
        if fingerprint == self._last_fingerprint:
            self._duplicate_count += 1
            return self._last_evidence

        result = self._mapping_engine.map_evidence(request)
        self._last_fingerprint = fingerprint
        self._last_evidence = result
        self._last_wait_reason = None
        self._assembled_count += 1
        return result

    def snapshot(self) -> TradingViewEvidenceAssemblySnapshot:
        return TradingViewEvidenceAssemblySnapshot(
            enabled=self._enabled,
            assembled_count=self._assembled_count,
            skipped_count=self._skipped_count,
            duplicate_count=self._duplicate_count,
            last_evidence=self._last_evidence,
            last_wait_reason=self._last_wait_reason,
        )

    def reset(self) -> TradingViewEvidenceAssemblySnapshot:
        self._assembled_count = 0
        self._skipped_count = 0
        self._duplicate_count = 0
        self._last_fingerprint = None
        self._last_evidence = None
        self._last_wait_reason = None
        return self.snapshot()

    def _wait_reason(self, source: TradingViewEvidenceAssemblyInput) -> str | None:
        if source.latest_price is None:
            return "latest price is unavailable"
        if source.latest_candle is None:
            return "latest closed candle is unavailable"
        return None

    def _request(self, source: TradingViewEvidenceAssemblyInput) -> TradingViewEvidenceRequest:
        timestamp = _latest_timestamp(source)
        pending = TradingViewEvidenceRequest(
            evidence_id="pending",
            timestamp=timestamp,
            instrument=source.instrument,
            timeframe=source.timeframe,
            latest_price=source.latest_price,
            latest_candle=source.latest_candle,
            camarilla=source.camarilla,
            cpr=source.cpr,
            vwap=source.vwap,
            adr=None,
            price_action=source.price_action,
            market_context=source.market_context,
            option_chain=source.option_chain,
            moving_averages=(),
            momentum=None,
            volume=None,
            correlation_id=source.correlation_id,
        )
        digest = hashlib.sha256(pending.fingerprint().encode("utf-8")).hexdigest()[:24]
        return TradingViewEvidenceRequest(
            evidence_id=f"tradingview-evidence-{source.instrument.value.lower()}-{source.timeframe}-{digest}",
            timestamp=timestamp,
            instrument=source.instrument,
            timeframe=source.timeframe,
            latest_price=source.latest_price,
            latest_candle=source.latest_candle,
            camarilla=source.camarilla,
            cpr=source.cpr,
            vwap=source.vwap,
            adr=None,
            price_action=source.price_action,
            market_context=source.market_context,
            option_chain=source.option_chain,
            moving_averages=(),
            momentum=None,
            volume=None,
            correlation_id=source.correlation_id,
        )


def _latest_timestamp(source: TradingViewEvidenceAssemblyInput) -> datetime:
    timestamps = [source.timestamp]
    for item in (
        source.latest_candle,
        source.price_action,
        source.camarilla,
        source.cpr,
        source.vwap,
        source.option_chain,
        source.market_context,
    ):
        timestamp = evidence_timestamp(item)
        if timestamp is not None:
            timestamps.append(timestamp)
    return max(timestamps)
