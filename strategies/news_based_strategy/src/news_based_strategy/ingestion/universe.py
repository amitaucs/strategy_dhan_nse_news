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

# Verified DhanHQ numeric security IDs for all active NSE F&O underlying equities
# Used for instantaneous O(1) resolution and offline resilience
FALLBACK_SECURITY_IDS: dict[str, str] = {
    "360ONE": "13061",
    "AARTIIND": "7",
    "ABB": "13",
    "ABBOTINDIA": "17903",
    "ABCAPITAL": "21614",
    "ABFRL": "30108",
    "ACC": "22",
    "ADANIENSOL": "10217",
    "ADANIENT": "25",
    "ADANIGREEN": "3563",
    "ADANIPORTS": "15083",
    "ADANIPOWER": "17388",
    "ALKEM": "11703",
    "AMBER": "1185",
    "AMBUJACEM": "1270",
    "ANGELONE": "324",
    "APLAPOLLO": "25780",
    "APOLLOHOSP": "157",
    "APOLLOTYRE": "163",
    "ASHOKLEY": "212",
    "ASIANPAINT": "236",
    "ASTRAL": "14418",
    "ATHERENERG": "757645",
    "ATUL": "30023",
    "AUBANK": "21238",
    "AUROPHARMA": "275",
    "AXISBANK": "5900",
    "BAJAJ-AUTO": "16669",
    "BAJAJFINSV": "16675",
    "BAJAJHLDNG": "305",
    "BAJFINANCE": "317",
    "BALKRISIND": "335",
    "BANDHANBNK": "2263",
    "BANKBARODA": "4668",
    "BANKINDIA": "4745",
    "BATAINDIA": "371",
    "BDL": "2144",
    "BEL": "383",
    "BERGEPAINT": "404",
    "BHARATFORG": "422",
    "BHARTIARTL": "10604",
    "BHEL": "438",
    "BIOCON": "11373",
    "BLUESTARCO": "8311",
    "BOSCHLTD": "2181",
    "BPCL": "526",
    "BRITANNIA": "547",
    "BSE": "19585",
    "BSOFT": "6994",
    "CAMS": "342",
    "CANBK": "10794",
    "CANFINHOME": "583",
    "CDSL": "21174",
    "CESC": "628",
    "CGPOWER": "760",
    "CHAMBLFERT": "637",
    "CHOLAFIN": "685",
    "CIPLA": "694",
    "COALINDIA": "20374",
    "COCHINSHIP": "21508",
    "COFORGE": "11543",
    "COLPAL": "15141",
    "CONCOR": "4749",
    "COROMANDEL": "739",
    "CROMPTON": "17094",
    "CUB": "5701",
    "CUMMINSIND": "1901",
    "CYIENT": "5748",
    "DABUR": "772",
    "DALBHARAT": "8075",
    "DEEPAKNTR": "19943",
    "DELHIVERY": "9599",
    "DIVISLAB": "10940",
    "DIXON": "21690",
    "DLF": "14732",
    "DMART": "19913",
    "DRREDDY": "881",
    "EICHERMOT": "910",
    "ESCORTS": "958",
    "ETERNAL": "5097",
    "EXIDEIND": "676",
    "FEDERALBNK": "1023",
    "FORCEMOT": "11573",
    "FORTIS": "14592",
    "GAIL": "4717",
    "GLENMARK": "7406",
    "GMRAIRPORT": "13528",
    "GMRINFRA": "13528",
    "GNFC": "1174",
    "GODFRYPHLP": "1181",
    "GODREJCP": "10099",
    "GODREJPROP": "17875",
    "GRANULES": "11872",
    "GRASIM": "1232",
    "GUJENERGY": "10599",
    "GUJGASLTD": "10599",
    "GVT&D": "16783",
    "HAL": "2303",
    "HAVELLS": "9819",
    "HCLTECH": "7229",
    "HDFCAMC": "4244",
    "HDFCBANK": "1333",
    "HDFCLIFE": "467",
    "HEROMOTOCO": "1348",
    "HINDALCO": "1363",
    "HINDCOPPER": "17939",
    "HINDPETRO": "1406",
    "HINDUNILVR": "1394",
    "HINDZINC": "1424",
    "HUDCO": "20825",
    "HYUNDAI": "25844",
    "ICICIBANK": "4963",
    "ICICIGI": "21770",
    "ICICIPRULI": "18652",
    "IDEA": "14366",
    "IDFCFIRSTB": "11184",
    "IEX": "220",
    "IGL": "11262",
    "INDHOTEL": "1512",
    "INDIAMART": "10726",
    "INDIANB": "14309",
    "INDIGO": "11195",
    "INDUSINDBK": "5258",
    "INDUSTOWER": "29135",
    "INFY": "1594",
    "INOXWIND": "7852",
    "IOC": "1624",
    "IPCALAB": "1633",
    "IRCTC": "13611",
    "IREDA": "20261",
    "IRFC": "2029",
    "ITC": "1660",
    "JINDALSTEL": "6733",
    "JIOFIN": "18143",
    "JKCEMENT": "13270",
    "JSWENERGY": "17869",
    "JSWSTEEL": "11723",
    "JUBLFOOD": "18096",
    "KALYANKJIL": "2955",
    "KAYNES": "12092",
    "KEI": "13310",
    "KFINTECH": "13359",
    "KOTAKBANK": "1922",
    "KPITTECH": "9683",
    "LALPATHLAB": "11654",
    "LAURUSLABS": "19234",
    "LICHSGFIN": "1997",
    "LICI": "9480",
    "LODHA": "3220",
    "LT": "11483",
    "LTF": "24948",
    "LTIM": "17818",
    "LTM": "17818",
    "LUPIN": "10440",
    "M&M": "2031",
    "M&MFIN": "13285",
    "MAHABANK": "11377",
    "MANAPPURAM": "19061",
    "MANKIND": "15380",
    "MARICO": "4067",
    "MARUTI": "10999",
    "MAXHEALTH": "22377",
    "MAZDOCK": "509",
    "MCX": "31181",
    "METROPOLIS": "9581",
    "MFSL": "2142",
    "MGL": "17534",
    "MOTHERSON": "4204",
    "MOTILALOFS": "14947",
    "MPHASIS": "4503",
    "MRF": "2277",
    "MUTHOOTFIN": "23650",
    "NAM-INDIA": "357",
    "NATIONALUM": "6364",
    "NAUKRI": "13751",
    "NAVINFLUOR": "14672",
    "NBCC": "31415",
    "NESTLEIND": "17963",
    "NHPC": "17400",
    "NMDC": "15332",
    "NTPC": "11630",
    "NYKAA": "6545",
    "OBEROIRLTY": "20242",
    "OFSS": "10738",
    "OIL": "17438",
    "ONGC": "2475",
    "PAGEIND": "14413",
    "PATANJALI": "17029",
    "PAYTM": "6705",
    "PEL": "758732",
    "PERSISTENT": "18365",
    "PETRONET": "11351",
    "PFC": "14299",
    "PGEL": "25358",
    "PHOENIXLTD": "14552",
    "PIDILITIND": "2664",
    "PIIND": "24184",
    "PNB": "10666",
    "PNBHOUSING": "18908",
    "POLICYBZR": "6656",
    "POLYCAB": "9590",
    "POONAWALLA": "11403",
    "POWERGRID": "14977",
    "POWERINDIA": "18457",
    "PREMIERENE": "25049",
    "PRESTIGE": "20302",
    "PVRINOX": "13147",
    "RADICO": "10990",
    "RAMCOCEM": "2043",
    "RBLBANK": "18391",
    "RECLTD": "15355",
    "RELIANCE": "2885",
    "RVNL": "9552",
    "SAGILITY": "27052",
    "SAIL": "2963",
    "SBICARD": "17971",
    "SBILIFE": "21808",
    "SBIN": "3045",
    "SHREECEM": "3103",
    "SHRIRAMFIN": "4306",
    "SIEMENS": "3150",
    "SJVN": "18883",
    "SOLARINDS": "13332",
    "SONACOMS": "4684",
    "SRF": "3273",
    "SUNPHARMA": "3351",
    "SUNTV": "13404",
    "SUPREMEIND": "3363",
    "SUZLON": "12018",
    "SWIGGY": "27066",
    "SYNGENE": "10243",
    "TATACHEM": "3405",
    "TATACOMM": "3721",
    "TATACONSUM": "3432",
    "TATAELXSI": "3411",
    "TATAMOTORS": "3456",
    "TATAMTRDVR": "3456",
    "TATAPOWER": "3426",
    "TATASTEEL": "3499",
    "TATATECH": "20293",
    "TCS": "11536",
    "TECHM": "13538",
    "TIINDIA": "312",
    "TITAN": "3506",
    "TMPV": "3456",
    "TORNTPHARM": "3518",
    "TRENT": "1964",
    "TVSMOTOR": "8479",
    "UBL": "16713",
    "ULTRACEMCO": "11532",
    "UNIONBANK": "10753",
    "UNITDSPR": "10447",
    "UNOMINDA": "14154",
    "UPL": "11287",
    "VBL": "18921",
    "VEDL": "3063",
    "VMM": "27969",
    "VOLTAS": "3718",
    "WAAREEENER": "25907",
    "WIPRO": "3787",
    "YESBANK": "11915",
    "ZOMATO": "5097",
    "ZYDUSLIFE": "7929",
}

# Common symbol aliases and renaming for robust lookup
SYMBOL_ALIASES: dict[str, str] = {
    "LTIM": "17818",
    "LTM": "17818",
    "GMRINFRA": "13528",
    "GMRAIRPORT": "13528",
    "GUJGASLTD": "10599",
    "GUJENERGY": "10599",
    "TATAMTRDVR": "3456",
    "BAJAJ_AUTO": "16669",
    "M_AND_M": "2031",
    "M&M": "2031",
    "M&MFIN": "13285",
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
    """Parse CSV text from Dhan scrip master and extract mapping of NSE symbol -> numeric security_id.
    
    Strictly prioritizes Series 'EQ' equities so that rights, debt, or preference series
    do not overwrite active underlying equity numeric security IDs.
    """
    mapping: dict[str, str] = {}
    reader = csv.DictReader(io.StringIO(csv_content))

    for row in reader:
        exch = (row.get("SEM_EXM_EXCH_ID") or "").strip().upper()
        inst = (row.get("SEM_INSTRUMENT_NAME") or "").strip().upper()
        series = (row.get("SEM_SERIES") or "").strip().upper()
        sec_id = (row.get("SEM_SMST_SECURITY_ID") or "").strip()
        trading_symbol = (row.get("SEM_TRADING_SYMBOL") or "").strip().upper()
        custom_symbol = (row.get("SEM_CUSTOM_SYMBOL") or "").strip().upper()

        if exch == "NSE" and inst == "EQUITY" and sec_id:
            base_trading = trading_symbol.split("-")[0].strip() if trading_symbol else ""
            base_custom = custom_symbol.split("-")[0].split()[0].strip() if custom_symbol else ""

            # Exact full symbols
            if trading_symbol:
                mapping[trading_symbol] = sec_id
            if custom_symbol:
                mapping[custom_symbol] = sec_id

            # Base symbol mapping: EQ series always has absolute top priority
            if series in ("EQ", ""):
                if base_trading:
                    mapping[base_trading] = sec_id
                if base_custom:
                    mapping[base_custom] = sec_id
            elif series in ("BE", "BZ", "SM"):
                # Only set if not already set by EQ series
                if base_trading and base_trading not in mapping:
                    mapping[base_trading] = sec_id
                if base_custom and base_custom not in mapping:
                    mapping[base_custom] = sec_id

    return mapping


def _get_candidate_cache_paths() -> list[str]:
    """Return ordered list of possible local cache paths for dhan_fno_symbols.json."""
    paths: list[str] = [
        DEFAULT_CACHE_PATH,
        os.path.join(os.getcwd(), "data", "dhan_fno_symbols.json"),
        os.path.join(os.getcwd(), "strategies", "news_based_strategy", "data", "dhan_fno_symbols.json"),
        "/app/data/dhan_fno_symbols.json",
        "/app/strategies/news_based_strategy/data/dhan_fno_symbols.json",
    ]
    # Add path relative to current file
    pkg_data = os.path.normpath(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "..",
            "..",
            "data",
            "dhan_fno_symbols.json",
        )
    )
    if pkg_data not in paths:
        paths.append(pkg_data)
    return paths


def _load_cached_universe_file(path: str) -> bool:
    """Load symbols and security IDs from a local cache file into in-memory state."""
    global _ACTIVE_FNO_SYMBOLS, _SECURITY_ID_MAP
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)
            symbols = set(cached.get("symbols", []))
            sec_ids = cached.get("security_ids", {})
            if len(symbols) >= 50:
                _ACTIVE_FNO_SYMBOLS.update(symbols)
            if sec_ids:
                _SECURITY_ID_MAP.update(sec_ids)
            if len(symbols) >= 50 or sec_ids:
                logger.info(
                    "Loaded %d F&O symbols and %d security IDs from local cache (%s).",
                    len(_ACTIVE_FNO_SYMBOLS),
                    len(_SECURITY_ID_MAP),
                    path,
                )
                return True
    except Exception as e:
        logger.debug("Failed reading cache at %s: %s", path, e)
    return False


def sync_dhan_fno_symbols(
    cache_path: Optional[str] = None,
    max_age_hours: int = 24,
    force_refresh: bool = False,
    timeout: int = 10,
) -> Set[str]:
    """Fetch and sync the latest F&O universe and security ID map from DhanHQ scrip master."""
    global _ACTIVE_FNO_SYMBOLS, _SECURITY_ID_MAP
    target_cache = cache_path or DEFAULT_CACHE_PATH

    # Always ensure fallback is populated first
    _SECURITY_ID_MAP.update(FALLBACK_SECURITY_IDS)
    _SECURITY_ID_MAP.update(SYMBOL_ALIASES)

    # 1. Check if cache exists and is fresh (try target_cache and candidate paths)
    if not force_refresh:
        for cpath in ([target_cache] if target_cache else []) + _get_candidate_cache_paths():
            if os.path.exists(cpath):
                try:
                    with open(cpath, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                        updated_at = datetime.fromisoformat(cached.get("updated_at", "1970-01-01"))
                        if datetime.now() - updated_at < timedelta(hours=max_age_hours):
                            if _load_cached_universe_file(cpath):
                                return _ACTIVE_FNO_SYMBOLS
                except Exception:
                    pass

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

    # 3. Fallback: If any cache file exists even if expired, use it
    for cpath in ([target_cache] if target_cache else []) + _get_candidate_cache_paths():
        if os.path.exists(cpath):
            if _load_cached_universe_file(cpath):
                return _ACTIVE_FNO_SYMBOLS

    # 4. Final fallback: Use built-in comprehensive fallback list
    _ACTIVE_FNO_SYMBOLS.update(FALLBACK_FNO_SYMBOLS)
    _SECURITY_ID_MAP.update(FALLBACK_SECURITY_IDS)
    _SECURITY_ID_MAP.update(SYMBOL_ALIASES)
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
    """Instant O(1) multi-stage resolution from stock symbol to Dhan numeric security_id.
    
    Handles exact symbols (e.g. 'ALKEM', 'BEL'), case-insensitivity ('alkem'),
    series suffixes ('TATAMOTORS-EQ' -> 'TATAMOTORS'), aliases ('LTIM' -> '17818'),
    and falls back to scanner_dhan and cached master dictionaries.
    """
    if not symbol:
        return None
    clean = symbol.strip().upper()

    # 1. Check in-memory active map
    if clean in _SECURITY_ID_MAP:
        return _SECURITY_ID_MAP[clean]

    # 2. Check suffix strip (-EQ, -BE, etc.)
    base = clean.split("-")[0].strip()
    if base in _SECURITY_ID_MAP:
        return _SECURITY_ID_MAP[base]

    # 3. Check whitespace/token strip
    first_token = clean.split()[0].strip()
    if first_token in _SECURITY_ID_MAP:
        return _SECURITY_ID_MAP[first_token]

    # 4. Check known symbol aliases (e.g., LTIM, GMRINFRA, GUJGASLTD)
    if clean in SYMBOL_ALIASES:
        sec_id = SYMBOL_ALIASES[clean]
        _SECURITY_ID_MAP[clean] = sec_id
        return sec_id
    if base in SYMBOL_ALIASES:
        sec_id = SYMBOL_ALIASES[base]
        _SECURITY_ID_MAP[base] = sec_id
        return sec_id

    # 5. Check FALLBACK_SECURITY_IDS directly
    if clean in FALLBACK_SECURITY_IDS:
        sec_id = FALLBACK_SECURITY_IDS[clean]
        _SECURITY_ID_MAP[clean] = sec_id
        return sec_id
    if base in FALLBACK_SECURITY_IDS:
        sec_id = FALLBACK_SECURITY_IDS[base]
        _SECURITY_ID_MAP[base] = sec_id
        return sec_id

    # 6. Check scanner_dhan universe if imported/available
    try:
        from scanner_dhan.universe.fno import FNO_SECURITY_IDS as SCANNER_FNO_SECS
        if clean in SCANNER_FNO_SECS:
            sec_id = SCANNER_FNO_SECS[clean]
            _SECURITY_ID_MAP[clean] = sec_id
            return sec_id
        if base in SCANNER_FNO_SECS:
            sec_id = SCANNER_FNO_SECS[base]
            _SECURITY_ID_MAP[base] = sec_id
            return sec_id
    except Exception:
        pass

    # 7. On-demand cache file reload (if new symbols exist in cache file on disk)
    for cpath in _get_candidate_cache_paths():
        if os.path.exists(cpath):
            if _load_cached_universe_file(cpath):
                if clean in _SECURITY_ID_MAP:
                    return _SECURITY_ID_MAP[clean]
                if base in _SECURITY_ID_MAP:
                    return _SECURITY_ID_MAP[base]
                break

    return None


def get_security_id_map() -> dict[str, str]:
    """Get the in-memory mapping of trading symbols to Dhan security IDs."""
    return dict(_SECURITY_ID_MAP)


# Backward-compatibility alias
FNO_SYMBOLS = _ACTIVE_FNO_SYMBOLS

__all__ = [
    "FNO_SYMBOLS",
    "FALLBACK_FNO_SYMBOLS",
    "FALLBACK_SECURITY_IDS",
    "SYMBOL_ALIASES",
    "sync_dhan_fno_symbols",
    "get_fno_symbols",
    "is_fno_stock",
    "parse_fno_symbols_from_csv",
    "parse_security_ids_from_csv",
    "resolve_security_id",
    "get_security_id_map",
]
