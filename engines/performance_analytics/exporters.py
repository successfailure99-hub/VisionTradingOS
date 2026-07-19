"""
CSV and XLSX exporters for performance analytics.
"""

from __future__ import annotations

import csv
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from engines.paper_trading.models import PaperTradeRecord
from engines.performance_analytics.models import AnalyticsSnapshot, ExportResult


CSV_COLUMNS = (
    "trade_id", "position_id", "paper_order_id", "plan_id", "instrument", "direction", "quantity", "lot_size",
    "entry_time", "entry_price", "exit_time", "exit_price", "stop_price", "target_price", "exit_type", "gross_pnl",
    "fees", "net_pnl", "reward_risk_planned", "reward_risk_realized", "maximum_favourable_excursion",
    "maximum_adverse_excursion", "holding_seconds", "strategy_setup", "strategy_confidence", "strategy_reasoning",
    "trading_date", "entry_type", "timeframe", "ai_confidence", "ai_decision", "ai_reasoning_summary",
    "price_action_setup", "market_phase", "day_bias", "option_chain_bias", "cpr_relationship",
    "cpr_width_classification", "camarilla_relationship", "vwap_relationship", "source_strategy_id",
    "source_plan_identity",
)


class PerformanceAnalyticsExporter:
    def export_csv(self, records: tuple[PaperTradeRecord, ...], path: Path | str, *, exported_at: datetime, overwrite: bool = False) -> ExportResult:
        target = Path(path)
        if target.exists() and not overwrite:
            raise FileExistsError("export target already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, dir=str(target.parent)) as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for record in records:
                writer.writerow({column: _cell(getattr(record, column, None)) for column in CSV_COLUMNS})
            temp = Path(handle.name)
        temp.replace(target)
        return ExportResult(target, len(records), exported_at, "csv")

    def export_excel(self, records: tuple[PaperTradeRecord, ...], snapshot: AnalyticsSnapshot, path: Path | str, *, exported_at: datetime, overwrite: bool = False) -> ExportResult:
        target = Path(path)
        if target.exists() and not overwrite:
            raise FileExistsError("export target already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        sheets = {
            "Summary": (("Metric", "Value"), _summary_rows(snapshot)),
            "Trades": (CSV_COLUMNS, tuple(tuple(_cell(getattr(record, column, None)) for column in CSV_COLUMNS) for record in records)),
            "Equity Curve": (("Sequence", "Trade ID", "Timestamp", "Trade P&L", "Cumulative P&L", "Drawdown", "Drawdown %"), tuple((p.sequence, p.trade_id, p.timestamp.isoformat(), p.trade_pnl, p.cumulative_pnl, p.drawdown, p.drawdown_percentage) for p in snapshot.equity_curve)),
            "Daily": _period_sheet(snapshot.daily_performance),
            "Weekly": _period_sheet(snapshot.weekly_performance),
            "Monthly": _period_sheet(snapshot.monthly_performance),
            "Setup Statistics": _group_sheet(snapshot.setup_statistics),
            "Time of Day": _group_sheet(snapshot.time_of_day_statistics),
            "Camarilla": _group_sheet(snapshot.camarilla_statistics),
            "CPR": _group_sheet(snapshot.cpr_statistics),
            "AI Review": (("Trade ID", "Review"), tuple((record.trade_id, "Deterministic post-trade review available from analytics API") for record in records)),
        }
        with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(target.parent)) as handle:
            temp = Path(handle.name)
        _write_xlsx(temp, sheets)
        temp.replace(target)
        return ExportResult(target, len(records), exported_at, "xlsx")


def _summary_rows(snapshot):
    s = snapshot.selected_instrument
    return (
        ("Total Trades", s.record_count),
        ("Net P&L", s.net_profit),
        ("Win Rate", s.win_rate),
        ("Loss Rate", s.loss_rate),
        ("Profit Factor", s.profit_factor),
        ("Expectancy", s.expectancy),
        ("Average R", s.average_r),
        ("Maximum Drawdown", s.maximum_drawdown),
        ("Current Drawdown %", s.current_drawdown_percentage),
    )


def _period_sheet(periods):
    return (("Period", "Start", "End", "Trades", "Net P&L", "Win Rate"), tuple((p.label, p.period_start.isoformat(), p.period_end.isoformat(), p.summary.record_count, p.summary.net_profit, p.summary.win_rate) for p in periods))


def _group_sheet(groups):
    return (("Group", "Trades", "Net P&L", "Win Rate", "Profit Factor"), tuple((g.group_key, g.summary.record_count, g.summary.net_profit, g.summary.win_rate, g.summary.profit_factor) for g in groups))


def _write_xlsx(path: Path, sheets) -> None:
    sheet_names = tuple(sheets)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types(len(sheet_names)))
        zf.writestr("_rels/.rels", _root_rels())
        zf.writestr("xl/workbook.xml", _workbook(sheet_names))
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels(len(sheet_names)))
        zf.writestr("xl/styles.xml", _styles())
        for index, (name, (headers, rows)) in enumerate(sheets.items(), start=1):
            zf.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(headers, rows))


def _sheet_xml(headers, rows):
    all_rows = (tuple(headers),) + tuple(tuple(row) for row in rows)
    xml_rows = []
    for r_index, row in enumerate(all_rows, start=1):
        cells = []
        for c_index, value in enumerate(row, start=1):
            ref = f"{_col(c_index)}{r_index}"
            style = ' s="1"' if r_index == 1 else ""
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"{style}><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t>{escape(str(value) if value is not None else "")}</t></is></c>')
        xml_rows.append(f'<row r="{r_index}">{"".join(cells)}</row>')
    return f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetData>{"".join(xml_rows)}</sheetData><autoFilter ref="A1:{_col(max(len(headers),1))}{max(len(all_rows),1)}"/></worksheet>'


def _col(index):
    result = ""
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def _content_types(count):
    sheets = "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, count + 1))
    return f'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>{sheets}</Types>'


def _root_rels():
    return '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'


def _workbook(names):
    sheets = "".join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(names, start=1))
    return f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{sheets}</sheets></workbook>'


def _workbook_rels(count):
    rels = "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, count + 1))
    return f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}<Relationship Id="rId{count+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'


def _styles():
    return '<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font/><font><b/></font></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf fontId="0"/><xf fontId="1" applyFont="1"/></cellXfs></styleSheet>'


def _cell(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return " | ".join(str(item) for item in value)
    return getattr(value, "value", value)

