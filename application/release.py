"""
Vision Trading OS release metadata.
"""

from application.enums import ExecutionSafetyMode, RuntimeInstrument
from brokers.zerodha.enums import BrokerExecutionMode


VERSION = "1.0.0"
SUPPORTED_RUNTIME_INSTRUMENTS = (
    RuntimeInstrument.NIFTY,
    RuntimeInstrument.BANKNIFTY,
    RuntimeInstrument.SENSEX,
)
SUPPORTED_SAFETY_MODES = (
    ExecutionSafetyMode.ANALYSIS_ONLY,
    ExecutionSafetyMode.DRY_RUN,
)
REQUIRED_BROKER_MODE = BrokerExecutionMode.DRY_RUN
