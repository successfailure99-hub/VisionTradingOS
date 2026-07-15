# Vision Trading OS

Version: 1.0.0

Vision Trading OS is a synchronous, deterministic trading-analysis workstation. The current release candidate runs in protected modes only and is designed for analysis, validation, and dashboard review.

## Architecture

The application composes one `EventBus`, one `ApplicationOrchestrator`, and one `ApplicationLifecycleManager` through `ApplicationBootstrap`. Runtime state flows from engines into immutable `RuntimeSnapshot` values and then through dashboard presenters before widgets render read-only views.

## Execution Modes

- Safety mode: `ANALYSIS_ONLY` by default.
- Broker execution mode: `DRY_RUN`.
- Live order submission is not enabled by default.

## Supported Instruments

NIFTY, BANKNIFTY, SENSEX

## Startup

Desktop dashboard:

```powershell
python desktop_main.py
```

The startup path validates configuration, supported instruments, execution mode, safety mode, and core runtime dependencies before composing the application.

## Testing

Full regression suite:

```powershell
python -m pytest -v
```

Focused dashboard suite:

```powershell
python -m pytest tests/test_dashboard* -v
```

Focused price-action suite:

```powershell
python -m pytest tests/test_price_action* -v
```
