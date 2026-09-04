"""NSE F&O (Futures & Options) stock universe definitions and DhanHQ dynamic synchronization."""

import csv
from datetime import datetime, timedelta
import io
import json
import logging
import os
from typing import Optional, Set
import urllib.request

logger = logging.getLogger(__name__)

# Official Dhan compact scrip master CSV endpoint
DHAN_SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
DEFAULT_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "data",
    "dhan_fno_symbols.json",
)

# Comprehensive fallback set of active NSE F&O underlying equity symbols (~218 stocks)
# Used when offline or during initial startup before Dhan sync
FALLBACK_FNO_SYMBOLS: Set[str] = {
    "AARTIIND", "ABB", "ABBOTINDIA", "ABCAPITAL", "ABFRL", "ACC", "ADANIENT",
    "ADANIPORTS", "ALKEM", "AMBUJACEM", "ANGELONE", "APOLLOHOSP", "APOLLOTYRE",
    "ASHOKLEY", "ASIANPAINT", "ASTRAL", "ATUL", "AUBANK", "AUROPHARMA", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BALKRISIND", "BANDHANBNK", "BANKBARODA",
    "BANKINDIA", "BATAINDIA", "BDL", "BEL", "BERGEPAINT", "BHARATFORG", "BHARTIARTL",
    "BHEL", "BIOCON", "BOSCHLTD", "BPCL", "BRITANNIA", "BSE", "BSOFT", "CANBK",
    "CANFINHOME", "CDSL", "CESC", "CGPOWER", "CHAMBLFERT", "CHOLAFIN", "CIPLA",
    "COALINDIA", "COCHINSHIP", "COFORGE", "COLPAL", "CONCOR", "COROMANDEL", "CROMPTON",
    "CUB", "CUMMINSIND", "CYIENT", "DABUR", "DALBHARAT", "DEEPAKNTR", "DELHIVERY",
    "DIVISLAB", "DIXON", "DLF", "DRREDDY", "EICHERMOT", "ESCORTS", "EXIDEIND",
    "FEDERALBNK", "GAIL", "GLENMARK", "GMRINFRA", "GNFC", "GODREJCP", "GODREJPROP",
    "GRANULES", "GRASIM", "GUJGASLTD", "HAL", "HAVELLS", "HCLTECH", "HDFCAMC",
    "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO", "HINDCOPPER", "HINDPETRO",
    "HINDUNILVR", "HUDCO", "ICICIBANK", "ICICIGI", "ICICIPRULI", "IDEA", "IDFCFIRSTB",
    "IEX", "IGL", "INDHOTEL", "INDIAMART", "INDIGO", "INDUSINDBK", "INDUSTOWER",
    "INFY", "IOC", "IPCALAB", "IRCTC", "IRFC", "ITC", "JINDALSTEL", "JIOFIN",
    "JKCEMENT", "JSWENERGY", "JSWSTEEL", "JUBLFOOD", "KALYANKJIL", "KEI", "KOTAKBANK",
    "KPITTECH", "LALPATHLAB", "LAURUSLABS", "LICHSGFIN", "LTIM", "LT", "LTF",
    "LUPIN", "M&M", "M&MFIN", "MARICO", "MARUTI", "MAXHEALTH", "MAZDOCK", "MCX",
    "METROPOLIS", "MFSL", "MGL", "MOTHERSON", "MPHASIS", "MRF", "MUTHOOTFIN",
    "NATIONALUM", "NAUKRI", "NAVINFLUOR", "NBCC", "NESTLEIND", "NHPC", "NMDC",
    "NTPC", "NYKAA", "OBEROIRLTY", "OFSS", "OIL", "ONGC", "PAGEIND", "PAYTM",
    "PEL", "PERSISTENT", "PETRONET", "PFC", "PIDILITIND", "PIIND", "PNB",
    "POLICYBZR", "POLYCAB", "POONAWALLA", "POWERGRID", "PREMIERENE", "PRESTIGE",
    "PVRINOX", "RAMCOCEM", "RBLBANK", "RECLTD", "RELIANCE", "RVNL", "SAIL",
    "SBICARD", "SBILIFE", "SBIN", "SHREECEM", "SHRIRAMFIN", "SIEMENS", "SJVN",
    "SOLARINDS", "SONACOMS", "SRF", "SUNPHARMA", "SUNTV", "SUPREMEIND", "SUZLON",
    "SYNGENE", "TATACHEM", "TATACOMM", "TATACONSUM", "TATAELXSI", "TATAMOTORS",
    "TATAPOWER", "TATASTEEL", "TATATECH", "TCS", "TECHM", "TITAN", "TORNTPHARM",
    "TRENT", "TVSMOTOR", "UBL", "ULTRACEMCO", "UNIONBANK", "UPL", "VBL", "VEDL",
    "VOLTAS", "WIPRO", "YESBANK", "ZOMATO", "ZYDUSLIFE",
}

# Verified DhanHQ numeric security IDs for core F&O underlying equities
# Used for instantaneous O(1) resolution and offline resilience
FALLBACK_SECURITY_IDS: dict[str, str] = {
    "ADANIENT": "25",
    "ADANIPORTS": "15083",
    "AXISBANK": "5900",
    "BAJFINANCE": "317",
    "BANKINDIA": "4811",
    "BDL": "2168",
    "BEL": "383",
    "BHARTIARTL": "10604",
    "BHEL": "438",
    "BSE": "19585",
    "CGPOWER": "730",
    "COALINDIA": "20374",
    "CONCOR": "4749",
    "DIXON": "21769",
    "DLF": "14732",
    "HAL": "2303",
    "HDFCBANK": "1333",
    "HINDUNILVR": "1394",
    "HUDCO": "11809",
    "ICICIBANK": "4963",
    "INFY": "1594",
    "IRFC": "13611",
    "ITC": "1660",
    "JSWSTEEL": "11723",
    "KOTAKBANK": "1922",
    "LT": "11483",
    "MARUTI": "10999",
    "NTPC": "11630",
    "ONGC": "2475",
    "POWERGRID": "14977",
    "PRESTIGE": "20292",
    "PVRINOX": "13147",
    "RELIANCE": "2885",
    "RVNL": "1348",
    "SBIN": "3045",
    "SUNPHARMA": "3351",
    "TATAMOTORS": "3456",
    "TATASTEEL": "3499",
    "TCS": "11536",
    "TITAN": "3506",
    "VEDL": "3063",
    "WIPRO": "3787",
    "ZOMATO": "5097",
}

# Mutable in-memory active universe, seeded with fallback
_ACTIVE_FNO_SYMBOLS: Set[str] = set(FALLBACK_FNO_SYMBOLS)
_SECURITY_ID_MAP: dict[str, str] = dict(FALLBACK_SECURITY_IDS)


def parse_fno_symbols_from_csv(csv_content: str) -> Set[str]:
    """Parse CSV text from Dhan scrip master and extract active NSE F&O underlying symbols."""
    symbols: Set[str] = set()
    reader = csv.DictReader(io.StringIO(csv_content))

    for row in reader:
        exch = (row.get("SEM_EXM_EXCH_ID") or "").strip().upper()
        inst = (row.get("SEM_INSTRUMENT_NAME") or "").strip().upper()

        # Match NSE stock derivatives (Futures & Options on stocks)
        if exch == "NSE" and inst in ("FUTSTK", "OPTSTK"):
            symbol = (
                row.get("SEM_CUSTOM_SYMBOL")
                or row.get("SEM_TRADING_SYMBOL")
                or ""
            ).strip().upper()

            # Clean potential suffix formatting (e.g. if custom symbol has spaces or contract details)
            clean_symbol = symbol.split("-")[0].split()[0].strip()
            if clean_symbol and len(clean_symbol) <= 15:
                symbols.add(clean_symbol)

    return symbols


def parse_security_ids_from_csv(csv_content: str) -> dict[str, str]:
    """Parse CSV text from Dhan scrip master and extract mapping of NSE symbol -> numeric security_id."""
    mapping: dict[str, str] = {}
    reader = csv.DictReader(io.StringIO(csv_content))

    for row in reader:
        exch = (row.get("SEM_EXM_EXCH_ID") or "").strip().upper()
        inst = (row.get("SEM_INSTRUMENT_NAME") or "").strip().upper()

        if exch == "NSE" and inst == "EQUITY":
            sec_id = (row.get("SEM_SMST_SECURITY_ID") or "").strip()
            trading_symbol = (row.get("SEM_TRADING_SYMBOL") or "").strip().upper()
            custom_symbol = (row.get("SEM_CUSTOM_SYMBOL") or "").strip().upper()

            if sec_id:
                if trading_symbol:
                    mapping[trading_symbol] = sec_id
                    base_sym = trading_symbol.split("-")[0].strip()
                    if base_sym:
                        mapping[base_sym] = sec_id
                if custom_symbol:
                    clean_custom = custom_symbol.split("-")[0].split()[0].strip()
                    if clean_custom:
                        mapping[clean_custom] = sec_id

    return mapping


def sync_dhan_fno_symbols(
    cache_path: Optional[str] = None,
    max_age_hours: int = 24,
    force_refresh: bool = False,
    timeout: int = 10,
) -> Set[str]:
    """Fetch and sync the latest F&O universe and security ID map from DhanHQ scrip master."""
    global _ACTIVE_FNO_SYMBOLS, _SECURITY_ID_MAP
    target_cache = cache_path or DEFAULT_CACHE_PATH

    # 1. Check if cache exists and is fresh
    if not force_refresh and os.path.exists(target_cache):
        try:
            with open(target_cache, "r", encoding="utf-8") as f:
                cached = json.load(f)
                updated_at = datetime.fromisoformat(cached.get("updated_at", "1970-01-01"))
                if datetime.now() - updated_at < timedelta(hours=max_age_hours):
                    symbols = set(cached.get("symbols", []))
                    sec_ids = cached.get("security_ids", {})
                    if len(symbols) >= 50:
                        _ACTIVE_FNO_SYMBOLS = symbols
                    if sec_ids:
                        _SECURITY_ID_MAP.update(sec_ids)
                    if len(symbols) >= 50:
                        logger.info(
                            "Loaded %d F&O symbols and %d security IDs from local Dhan cache.",
                            len(symbols),
                            len(_SECURITY_ID_MAP),
                        )
                        return _ACTIVE_FNO_SYMBOLS
        except Exception as e:
            logger.debug("Failed reading Dhan F&O cache: %s", e)

    # 2. Attempt download from Dhan scrip master endpoint
    try:
        req = urllib.request.Request(
            DHAN_SCRIP_MASTER_URL,
            headers={"User-Agent": "Mozilla/5.0 (NewsStrategy/1.0)"},
        )
        ctx = None
        try:
            import ssl
            try:
                ctx = ssl.create_default_context()
            except Exception:
                ctx = ssl._create_unverified_context()
        except Exception:
            pass

        try:
            resp_cm = urllib.request.urlopen(req, context=ctx, timeout=timeout) if ctx else urllib.request.urlopen(req, timeout=timeout)
        except Exception:
            import ssl
            resp_cm = urllib.request.urlopen(req, context=ssl._create_unverified_context(), timeout=timeout)

        with resp_cm as resp:
            if resp.status == 200:
                raw_csv = resp.read().decode("utf-8", errors="ignore")
                parsed_symbols = parse_fno_symbols_from_csv(raw_csv)
                parsed_sec_ids = parse_security_ids_from_csv(raw_csv)

                if len(parsed_symbols) >= 50:
                    _ACTIVE_FNO_SYMBOLS = parsed_symbols
                if parsed_sec_ids:
                    _SECURITY_ID_MAP.update(parsed_sec_ids)

                if len(parsed_symbols) >= 50 or parsed_sec_ids:
                    # Persist to local cache
                    try:
                        os.makedirs(os.path.dirname(target_cache), exist_ok=True)
                        with open(target_cache, "w", encoding="utf-8") as f:
                            json.dump(
                                {
                                    "updated_at": datetime.now().isoformat(),
                                    "count": len(_ACTIVE_FNO_SYMBOLS),
                                    "symbols": sorted(list(_ACTIVE_FNO_SYMBOLS)),
                                    "security_ids": _SECURITY_ID_MAP,
                                },
                                f,
                                indent=2,
                            )
                        logger.info(
                            "Synced %d F&O symbols and %d security IDs from Dhan scrip master.",
                            len(_ACTIVE_FNO_SYMBOLS),
                            len(_SECURITY_ID_MAP),
                        )
                    except Exception as err:
                        logger.warning("Could not write Dhan F&O cache file: %s", err)

                    return _ACTIVE_FNO_SYMBOLS
    except Exception as e:
        logger.warning("Could not sync Dhan F&O universe from %s: %s", DHAN_SCRIP_MASTER_URL, e)

    # 3. Fallback: If cache exists even if expired, use it
    if os.path.exists(target_cache):
        try:
            with open(target_cache, "r", encoding="utf-8") as f:
                cached = json.load(f)
                symbols = set(cached.get("symbols", []))
                sec_ids = cached.get("security_ids", {})
                if len(symbols) >= 50:
                    _ACTIVE_FNO_SYMBOLS = symbols
                if sec_ids:
                    _SECURITY_ID_MAP.update(sec_ids)
                if len(symbols) >= 50:
                    logger.info("Using expired local Dhan cache with %d symbols.", len(symbols))
                    return _ACTIVE_FNO_SYMBOLS
        except Exception:
            pass

    # 4. Final fallback: Use built-in comprehensive fallback list
    _ACTIVE_FNO_SYMBOLS = set(FALLBACK_FNO_SYMBOLS)
    return _ACTIVE_FNO_SYMBOLS


def get_fno_symbols() -> Set[str]:
    """Get the active set of NSE F&O underlying tickers."""
    return _ACTIVE_FNO_SYMBOLS


def is_fno_stock(symbol: str) -> bool:
    """Check if a given stock symbol is an active NSE F&O constituent."""
    if not symbol:
        return False
    normalized = symbol.strip().upper()
    return normalized in get_fno_symbols()


def resolve_security_id(symbol: str) -> Optional[str]:
    """Instant O(1) resolution from stock symbol to Dhan numeric security_id.
    
    Handles exact symbols (e.g. 'BEL'), case-insensitivity ('bel'),
    and series suffixes ('TATAMOTORS-EQ' -> 'TATAMOTORS').
    """
    if not symbol:
        return None
    clean = symbol.strip().upper()
    # 1. Exact match
    if clean in _SECURITY_ID_MAP:
        return _SECURITY_ID_MAP[clean]
    # 2. Suffix strip (-EQ, -BE, etc.)
    base = clean.split("-")[0].strip()
    if base in _SECURITY_ID_MAP:
        return _SECURITY_ID_MAP[base]
    # 3. Whitespace/token strip
    first_token = clean.split()[0].strip()
    return _SECURITY_ID_MAP.get(first_token)


def get_security_id_map() -> dict[str, str]:
    """Get the in-memory mapping of trading symbols to Dhan security IDs."""
    return dict(_SECURITY_ID_MAP)


# Backward-compatibility alias
FNO_SYMBOLS = _ACTIVE_FNO_SYMBOLS

__all__ = [
    "FNO_SYMBOLS",
    "FALLBACK_FNO_SYMBOLS",
    "FALLBACK_SECURITY_IDS",
    "sync_dhan_fno_symbols",
    "get_fno_symbols",
    "is_fno_stock",
    "parse_fno_symbols_from_csv",
    "parse_security_ids_from_csv",
    "resolve_security_id",
    "get_security_id_map",
]
