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

Offline desktop mode:

```powershell
$env:LIVE_MARKET_DATA_ENABLED="false"
python desktop_main.py
```

Live market-data desktop mode uses Zerodha Kite Connect credentials from environment variables. Obtain the API key and API secret from the Zerodha developer console, and provide a current access token for the session. Zerodha access tokens normally expire and may need renewal. Keep credentials in local environment variables only; never commit `.env` files or real secrets.

Required live market-data variables are shown in `.env.example`:

```powershell
$env:ZERODHA_API_KEY="<your api key>"
$env:ZERODHA_API_SECRET="<your api secret>"
$env:ZERODHA_ACCESS_TOKEN="<current access token>"
$env:NIFTY_INSTRUMENT_TOKEN="<token>"
$env:BANKNIFTY_INSTRUMENT_TOKEN="<token>"
$env:SENSEX_INSTRUMENT_TOKEN="<token>"
$env:LIVE_MARKET_DATA_ENABLED="true"
$env:LIVE_MARKET_DATA_AUTO_CONNECT="true"
python desktop_main.py
```

Live market data enables WebSocket ticks for NIFTY, BANKNIFTY, and SENSEX only. Order execution remains protected: broker mode is `DRY_RUN`, safety mode remains `ANALYSIS_ONLY`, and live order placement is not enabled.

Live option-chain integration is disabled by default. To enable the dashboard option-chain runtime, keep live market data enabled and add:

```powershell
$env:LIVE_OPTION_CHAIN_ENABLED="true"
$env:LIVE_OPTION_CHAIN_AUTO_START="true"
$env:OPTION_CHAIN_STRIKES_EACH_SIDE="5"
python desktop_main.py
```

Option contracts are discovered dynamically from Zerodha's instrument master after the first valid spot tick for NIFTY, BANKNIFTY, or SENSEX. Do not configure or store option tokens manually. If option-chain discovery or subscription fails, the spot feed continues and the Option Chain panel shows a sanitized runtime error. Zerodha access tokens are valid only for the current session/day and must not be committed.

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
