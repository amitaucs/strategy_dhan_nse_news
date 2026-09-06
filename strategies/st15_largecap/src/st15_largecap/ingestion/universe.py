"""Nifty 200 universe management and DhanHQ Security ID synchronization."""

import csv
import io
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Set
import urllib.request

from st15_largecap.config import settings

logger = logging.getLogger(__name__)

DHAN_SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
DEFAULT_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "dhan_nifty200_symbols.json",
)

# Exact Official NIFTY 200 Constituents (Top 200 Large & Liquid Equities on NSE)
NIFTY_200_SYMBOLS: List[str] = [
    # Nifty 50 Large-Caps
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BPCL",
    "BHARTIARTL", "BRITANNIA", "CIPLA", "COALINDIA", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "ITC",
    "INDUSINDBK", "INFY", "JSWSTEEL", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SHRIRAMFIN", "SBIN",
    "SUNPHARMA", "TCS", "TATACONSUM", "TATAMOTORS", "TATASTEEL",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",

    # Nifty Next 50
    "ABB", "ADANIENSOL", "ADANIGREEN", "ADANIPOWER", "ATGL",
    "AMBUJACEM", "BANKBARODA", "BERGEPAINT", "BHEL", "BOSCHLTD",
    "CANBK", "CHOLAFIN", "COLPAL", "DLF", "DABUR",
    "DIVISLAB", "GAIL", "GODREJCP", "HAVELLS", "HAL",
    "ICICIGI", "ICICIPRULI", "IOC", "IRCTC", "IRFC",
    "IREDA", "JINDALSTEL", "JIOFIN", "LTIM", "MARICO",
    "MOTHERSON", "NAUKRI", "NHPC", "PFC", "PIDILITIND",
    "PNB", "REC", "SBICARD", "SIEMENS", "SRF",
    "TATAPOWER", "TVSMOTOR", "TORNTPOWER", "UNITDSPR", "VBL",
    "VEDL", "ZOMATO", "ZYDUSLIFE", "DMART", "LICI",

    # Nifty Midcap 100 Selected Constituents (completing exactly 200)
    "AUBANK", "AARTIIND", "ABBOTINDIA", "ABCAPITAL", "ABFRL",
    "ALKEM", "ANGELONE", "APOLLOTYRE", "ASHOKLEY", "ASTRAL",
    "ATUL", "AUROPHARMA", "BALKRISIND", "BANDHANBNK", "BANKINDIA",
    "BATAINDIA", "BAYERCROP", "BDL", "BHARATFORG", "BIOCON",
    "BSE", "BSOFT", "CANFINHOME", "CDSL", "CENTRALBK",
    "CGPOWER", "CHAMBLFERT", "CHOLAHLDNG", "COCHINSHIP", "COFORGE",
    "CONCOR", "COROMANDEL", "CROMPTON", "CUMMINSIND", "CYIENT",
    "DALBHARAT", "DEEPAKNTR", "DELHIVERY", "DEVYANI", "DIXON",
    "ESCORTS", "EXIDEIND", "FACT", "FEDERALBNK", "FORTIS",
    "GMRINFRA", "GLENMARK", "GODREJIND", "GODREJPROP", "GUJGASLTD",
    "HDFCAMC", "HFCL", "HINDPETRO", "HINDZINC", "HUDCO",
    "IDFCFIRSTB", "IEX", "INDHOTEL", "INDIANB", "INDIGO",
    "IGL", "INDUSTOWER", "IPCALAB", "JSWENERGY", "JSWINFRA",
    "JINDALSAW", "JSL", "JUBLFOOD", "KAJARIACER", "KALYANKJIL",
    "KEC", "KEI", "KPITTECH", "LTF", "LTTS",
    "LICHSGFIN", "LUPIN", "M&MFIN", "MAXHEALTH", "MAZDOCK",
    "METROPOLIS", "MFSL", "MPHASIS", "MRF", "MUTHOOTFIN",
    "NATIONALUM", "NAVINFLUOR", "NMDC", "OBEROIRLTY", "OFSS",
    "OIL", "PAGEIND", "PERSISTENT", "PETRONET", "PHOENIXLTD",
    "POLYCAB", "POONAWALLA", "PRESTIGE", "RADICO", "RVNL"
]

# Fallback Security ID mapping for popular top large-caps
DEFAULT_SEC_IDS: Dict[str, str] = {
    "RELIANCE": "2885", "TCS": "11536", "HDFCBANK": "1333", "INFY": "1594",
    "ICICIBANK": "4963", "HINDUNILVR": "1394", "ITC": "1660", "SBIN": "3045",
    "BHARTIARTL": "10604", "BAJFINANCE": "317", "KOTAKBANK": "1922", "LT": "11483",
    "AXISBANK": "5900", "ASIANPAINT": "236", "MARUTI": "10999", "TITAN": "3506",
    "SUNPHARMA": "3351", "ULTRACEMCO": "11532", "TATAMOTORS": "3456", "NTPC": "11630",
    "POWERGRID": "14977", "TATASTEEL": "3499", "M&M": "2031", "JSWSTEEL": "11723",
    "ADANIENT": "25", "ADANIPORTS": "15083", "COALINDIA": "20374", "ONGC": "2475",
    "HCLTECH": "7229", "WIPRO": "3787", "BAJAJFINSV": "16675", "NESTLEIND": "17963",
    "DRREDDY": "881", "DIVISLAB": "10940", "CIPLA": "694", "EICHERMOT": "910",
    "GRASIM": "1232", "HINDALCO": "1363", "APOLLOHOSP": "157", "HEROMOTOCO": "1348",
    "TECHM": "13538", "BPCL": "526", "BEL": "383", "HAL": "2303", "VEDL": "3063",
    "BANKBARODA": "4668", "TRENT": "1964", "ZOMATO": "5097", "JIOFIN": "18143",
    "VBL": "18938", "CHOLAFIN": "685", "POLYCAB": "9590", "DLF": "14732"
}


import ssl

# Common symbol aliases on Dhan / NSE
SYMBOL_ALIASES: Dict[str, str] = {
    "GMRINFRA": "GMRAIRPORT",
    "TATAMOTORS": "TMPV",
    "ZOMATO": "ETERNAL",
    "LTIM": "LTIM",
    "GUJGASLTD": "GUJGAST",
    "M&M": "M&M",
    "M&MFIN": "M&MFIN",
    "BAJAJ-AUTO": "BAJAJ-AUTO",
}


class UniverseManager:
    """Manages Nifty 200 ticker list and security ID resolution."""

    def __init__(self, cache_path: str = DEFAULT_CACHE_PATH):
        self.cache_path = cache_path
        self._sec_ids: Dict[str, str] = dict(DEFAULT_SEC_IDS)
        # Deduplicate and sort exactly
        self._symbols: List[str] = sorted(list(set(NIFTY_200_SYMBOLS)))
        self.load_cache()
        if len(self._sec_ids) < len(self._symbols):
            try:
                self.sync_from_dhan()
            except Exception:
                pass

    def load_cache(self) -> None:
        """Load cached symbol mappings from disk if available."""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._sec_ids.update(data)
                        logger.info("Loaded %d symbol mappings from cache", len(data))
            except Exception as e:
                logger.warning("Failed to load symbol cache from %s: %s", self.cache_path, e)

    def save_cache(self) -> None:
        """Persist current symbol mappings to disk."""
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._sec_ids, f, indent=2)
            logger.info("Saved %d symbol mappings to cache at %s", len(self._sec_ids), self.cache_path)
        except Exception as e:
            logger.warning("Failed to save symbol cache to %s: %s", self.cache_path, e)

    def sync_from_dhan(self, timeout_seconds: int = 15) -> int:
        """Download latest Dhan official scrip master CSV and resolve security IDs."""
        try:
            logger.info("Syncing Nifty 200 scrip master from DhanHQ (%s)...", DHAN_SCRIP_MASTER_URL)
            ssl_ctx = ssl._create_unverified_context()
            req = urllib.request.Request(
                DHAN_SCRIP_MASTER_URL,
                headers={"User-Agent": "Mozilla/5.0 (TradingPlatform/ST15)"},
            )
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=timeout_seconds) as response:
                csv_text = response.read().decode("utf-8", errors="ignore")

            reader = csv.reader(io.StringIO(csv_text))
            header = next(reader, None)
            if not header:
                return 0

            # Build fast lookup dictionary for NSE Equities
            nse_eq_map: Dict[str, str] = {}
            for row in reader:
                if len(row) < 8:
                    continue
                exch = row[0].strip().upper()
                seg = row[1].strip().upper()
                sec_id = row[2].strip()
                trad_sym = row[5].strip().upper()
                cust_sym = row[7].strip().upper()

                if exch in ("NSE", "NSE_EQ") and seg in ("E", "EQ", "NSE_EQ"):
                    clean_trad = trad_sym.replace("-EQ", "").replace(".EQ", "").strip()
                    clean_cust = cust_sym.replace("-EQ", "").replace(".EQ", "").strip()
                    if clean_trad:
                        nse_eq_map[clean_trad] = sec_id
                    if clean_cust:
                        nse_eq_map[clean_cust] = sec_id

            synced_count = 0
            for sym in self._symbols:
                target_alias = SYMBOL_ALIASES.get(sym, sym).upper()
                if sym in nse_eq_map:
                    self._sec_ids[sym] = nse_eq_map[sym]
                    synced_count += 1
                elif target_alias in nse_eq_map:
                    self._sec_ids[sym] = nse_eq_map[target_alias]
                    synced_count += 1

            logger.info("Successfully resolved %d / %d Nifty 200 security IDs from Dhan", len(self._sec_ids), len(self._symbols))
            self.save_cache()
            return synced_count
        except Exception as e:
            logger.warning("Dhan scrip master sync failed: %s. Using cached & fallback IDs.", e)
            return 0

    def get_security_id(self, symbol: str) -> str:
        """Get Dhan Security ID for a symbol."""
        clean = symbol.upper().strip()
        return self._sec_ids.get(clean, "")

    def get_universe(self) -> List[str]:
        """Get the full list of Nifty 200 symbols."""
        return list(self._symbols)


universe_manager = UniverseManager()

__all__ = ["UniverseManager", "universe_manager", "NIFTY_200_SYMBOLS", "DEFAULT_SEC_IDS"]
