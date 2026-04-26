"""Parser for the XM Partner ``traderTrades.csv`` export.

The file uses Thai column headers and a few Thai cell values
(ซื้อ/ขาย → buy/sell). We intentionally keep the parser tolerant:

* Multiple column-name variants are accepted.
* Unknown / extra columns are ignored.
* Rows with bad data are collected as ``errors`` instead of aborting.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional


# ─── Column aliases (Thai → canonical) ─────────────────────────────
ALIASES: dict[str, list[str]] = {
    "trade_id":         ["trade #", "เทรด #", "เทรด#", "ticket", "trade id", "deal id", "deal #"],
    "mt_id":            ["mt4/mt5 id", "mt4 id", "mt5 id", "mt id", "account", "เลขบัญชี"],
    "account_type":     ["account type", "ประเภทบัญชี"],
    "account_currency": ["account currency", "currency", "สกุลเงินของบัญชี", "สกุลเงิน"],
    "brand":            ["account brand", "brand", "แบรนด์ของบัญชี"],
    "campaign":         ["campaign", "แคมเปญ"],
    "open_time":        ["open time", "เวลาเปิด"],
    "close_time":       ["close time", "เวลาปิด"],
    "trade_kind":       ["trade type", "ประเภทของการซื้อขาย"],
    "side":             ["type", "side", "ประเภทของเทรด", "ประเภทเทรด"],
    "symbol":           ["instrument", "symbol", "ตราสาร"],
    "symbol_group":     ["instrument group", "กลุ่มของตราสาร"],
    "lots":             ["lots", "volume", "ปริมาณ"],
    "commission":       ["total commission", "commission", "คอมมิชชั่นรวม", "คอมมิชชั่น"],
    "affiliate_comm":   ["affiliate commission", "แอฟฟิลิเอตคอมมิชชั่น", "แอฟฟิลิเอตคอม"],
}

SIDE_MAP = {
    "buy": "buy", "sell": "sell",
    "ซื้อ": "buy", "ขาย": "sell",
    "long": "buy", "short": "sell",
    "b": "buy", "s": "sell",
}

DATE_FORMATS = [
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
]


@dataclass
class ParsedTrade:
    external_trade_id: str
    mt_id: str
    symbol: str
    side: str            # "buy" | "sell"
    lots: float
    traded_at: datetime
    account_currency: Optional[str] = None
    commission: Optional[float] = None
    raw_row: int = 0     # 1-based row number for debugging


@dataclass
class ParseReport:
    trades: list[ParsedTrade] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    header_map: dict[str, str] = field(default_factory=dict)  # canonical → original header

    @property
    def total_lots(self) -> float:
        return round(sum(t.lots for t in self.trades), 2)

    @property
    def unique_mt_ids(self) -> set[str]:
        return {t.mt_id for t in self.trades}


# ─── Helpers ───────────────────────────────────────────────────────
def _normalise(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _build_header_map(headers: list[str]) -> dict[str, str]:
    """Map our canonical names → the actual column header found in the file."""
    norm_to_orig = {_normalise(h): h for h in headers}
    mapping: dict[str, str] = {}
    for canonical, options in ALIASES.items():
        for opt in options:
            key = _normalise(opt)
            if key in norm_to_orig:
                mapping[canonical] = norm_to_orig[key]
                break
    return mapping


def _decode_bytes(raw: bytes) -> str:
    """Try a few sensible encodings (UTF-8 with/without BOM, Windows-874 for Thai)."""
    for enc in ("utf-8-sig", "utf-8", "cp874", "tis-620", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _parse_date(val: str) -> Optional[datetime]:
    if not val:
        return None
    val = val.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def _parse_float(val: str) -> Optional[float]:
    if val is None:
        return None
    cleaned = re.sub(r"[^\d\.\-,]", "", str(val)).replace(",", "")
    if not cleaned or cleaned in {"-", ".", "-.", ".-"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_side(val: str) -> Optional[str]:
    if not val:
        return None
    return SIDE_MAP.get(_normalise(val))


# ─── Main entry points ─────────────────────────────────────────────
def parse_csv_bytes(raw: bytes) -> ParseReport:
    text = _decode_bytes(raw)
    return parse_csv_text(text)


def parse_csv_text(text: str) -> ParseReport:
    report = ParseReport()

    # csv.Sniffer is unreliable for Thai content; default to comma but fall back to tab.
    first_line = text.splitlines()[0] if text else ""
    delimiter = "\t" if first_line.count("\t") > first_line.count(",") else ","

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows: Iterable[list[str]] = iter(reader)
    try:
        headers = next(rows)
    except StopIteration:
        report.errors.append({"row": 0, "error": "ไฟล์ว่างเปล่า"})
        return report

    headers = [h.strip().lstrip("\ufeff") for h in headers]
    header_map = _build_header_map(headers)
    report.header_map = header_map

    required = ["trade_id", "mt_id", "lots"]
    missing = [r for r in required if r not in header_map]
    if missing:
        report.errors.append({
            "row": 1,
            "error": f"ไม่พบคอลัมน์ที่จำเป็น: {missing}",
            "found_headers": headers,
        })
        return report

    idx = {canonical: headers.index(orig) for canonical, orig in header_map.items()}

    def get(row: list[str], key: str) -> str:
        i = idx.get(key)
        if i is None or i >= len(row):
            return ""
        return (row[i] or "").strip()

    for line_no, row in enumerate(rows, start=2):
        if not row or not any(c.strip() for c in row):
            continue

        trade_id = get(row, "trade_id")
        mt_id = get(row, "mt_id")
        lots_raw = get(row, "lots")

        if not trade_id or not mt_id:
            report.errors.append({"row": line_no, "error": "ขาด Trade ID หรือ MT ID"})
            continue

        lots = _parse_float(lots_raw)
        if lots is None or lots <= 0:
            report.errors.append({"row": line_no, "error": f"Lots ไม่ถูกต้อง: {lots_raw!r}"})
            continue

        side_raw = get(row, "side")
        side = _parse_side(side_raw) or "buy"

        when = _parse_date(get(row, "close_time")) or _parse_date(get(row, "open_time"))
        if when is None:
            report.errors.append({"row": line_no, "error": "อ่านวันที่ไม่ได้"})
            continue

        commission = _parse_float(get(row, "commission"))

        report.trades.append(ParsedTrade(
            external_trade_id=trade_id,
            mt_id=mt_id,
            symbol=(get(row, "symbol") or "UNKNOWN").upper(),
            side=side,
            lots=round(lots, 5),
            traded_at=when,
            account_currency=(get(row, "account_currency") or None),
            commission=commission,
            raw_row=line_no,
        ))

    return report
