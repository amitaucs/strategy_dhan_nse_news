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

# Comprehensive Nifty 200 stock list (Top 200 Large & Liquid Equities on NSE)
NIFTY_200_SYMBOLS: List[str] = [
    "ABB", "ACC", "AIAENG", "APLAPOLLO", "AUBANK", "AARTIIND", "AAVAS", "ABBOTINDIA",
    "ABCAPITAL", "ABFRL", "ADANIENSOL", "ADANIENT", "ADANIGREEN", "ADANIPORTS", "ADANIPOWER",
    "ATGL", "ABCAPITAL", "ALKEM", "ALOKINDS", "AMBUJACEM", "ANGELONE", "APOLLOHOSP",
    "APOLLOTYRE", "ASHOKLEY", "ASIANPAINT", "ASTRAL", "ATUL", "AUROPHARMA", "AVANTIFEED",
    "DMART", "AXISBANK", "BSOFT", "BAJAJ-AUTO", "BAJAJFINSV", "BAJAJHLDNG", "BAJFINANCE",
    "BALKRISIND", "BALRAMCHIN", "BANDHANBNK", "BANKBARODA", "BANKINDIA", "BATAINDIA",
    "BAYERCROP", "BERGEPAINT", "BDL", "BEL", "BHARATFORG", "BHEL", "BPCL", "BHARTIARTL",
    "BIOCON", "BIRLACORPN", "BLS", "BLUEDART", "BOSCHLTD", "BRITANNIA", "BSE", "CANFINHOME",
    "CANBK", "CAPL", "CARBORUNIV", "CASTROLIND", "CDSL", "CEATLTD", "CENTRALBK", "CENTURYPLY",
    "CENTURYTEX", "CESC", "CGPOWER", "CHAMBLFERT", "CHOLAFIN", "CHOLAHLDNG", "CIPLA",
    "CUB", "COALINDIA", "COCHINSHIP", "COFORGE", "COLPAL", "CONCOR", "COROMANDEL", "CRAFTSMAN",
    "CREDITACC", "CRISIL", "CROMPTON", "CUMMINSIND", "CYIENT", "DABUR", "DALBHARAT",
    "DEEPAKNTR", "DELHIVERY", "DEVYANI", "DIVISLAB", "DIXON", "LALPATHLAB", "DRREDDY",
    "EICHERMOT", "ELGIEQUIP", "EMAMILTD", "ENDURANCE", "ENGINERSIN", "EQUITASBNK", "ERIS",
    "ESCORTS", "EXIDEIND", "FSL", "FEDERALBNK", "FACT", "FINEORG", "FINPIPE", "FORTIS",
    "GRINFRA", "GAIL", "GMRINFRA", "GLENMARK", "MEDANTA", "GODFRYPHLP", "GODREJCP",
    "GODREJIND", "GODREJPROP", "GRANULES", "GRASIM", "GRAVITA", "GESHIP", "FLUOROCHEM",
    "GUJGASLTD", "GNFC", "GPPL", "GSFC", "GSPL", "HDFCAMC", "HDFCBANK", "HDFCLIFE",
    "HFCL", "HLEGLAS", "HAL", "HAPPSTMNDS", "HAVELLS", "HCLTECH", "HEG", "HEROMOTOCO",
    "HINDALCO", "HINDCOPPER", "HINDPETRO", "HINDUNILVR", "HINDZINC", "HOMEFIRST", "HONAUT",
    "HUDCO", "ICICIBANK", "ICICIGI", "ICICIPRULI", "ISEC", "IDBI", "IDFCFIRSTB", "IDFC",
    "IFCI", "IIFL", "IEX", "INDHOTEL", "INDIACEM", "INDIAMART", "INDIANB", "INDIGO",
    "IRCTC", "IRFC", "IREDA", "IGL", "INDUSINDBK", "INDUSTOWER", "INFIBEAM", "NAUKRI",
    "INFY", "INGERRAND", "INTELLECT", "INDIGO", "IOC", "IPCALAB", "JBCHEPHARM", "JKCEMENT",
    "JBMA", "JKLAKSHMI", "JKTYRE", "JMFINANCIL", "JSWENERGY", "JSWINFRA", "JSWSTEEL",
    "JINDALSAW", "JSL", "JINDALSTEL", "JIOFIN", "JUBLFOOD", "JUBLINGREA", "JUBLPHARMA",
    "JUSTDIAL", "JYOTHYLAB", "KPRMILL", "KEI", "KNRCON", "KPITTECH", "KRBL", "KSB",
    "KAJARIACER", "KALYANKJIL", "KANSAINER", "KARURVYSYA", "KAYNES", "KEC", "KOTAKBANK",
    "LTF", "LTTS", "LICHSGFIN", "LTIM", "LT", "LAURUSLABS", "LEMONTREE", "LICI", "LINDEINDIA",
    "LUPIN", "MMTC", "MRF", "MGL", "MAHSEAMLES", "M&MFIN", "M&M", "MANAPPURAM", "MARICO",
    "MARUTI", "MASTEK", "MAXHEALTH", "MAZDOCK", "METROPOLIS", "MFSL", "MSUMI", "MOTILALOFS",
    "MPHASIS", "MCX", "MUTHOOTFIN", "NATCOPHARM", "NBCC", "NCC", "NHPC", "NLCINDIA",
    "NMDC", "NOCIL", "NTPC", "NH", "NATIONALUM", "NAVINFLUOR", "NESTLEIND", "NETWORK18",
    "NUVAMA", "OBEROIRLTY", "ONGC", "OIL", "OLECTRA", "PAYTM", "OFSS", "ORIENTELEC",
    "POLICYBZR", "PIIND", "PNBHOUSING", "PNCINFRA", "PVRINOX", "PAGEIND", "PATANJALI",
    "PERSISTENT", "PETRONET", "PFIZER", "PHOENIXLTD", "PIDILITIND", "POLYMED", "POLYCAB",
    "POONAWALLA", "PFC", "POWERGRID", "PRESTIGE", "PRINCEPIPE", "PRSMJOHNSN", "PGHH",
    "PNB", "QUESS", "RBLBANK", "REC", "RITES", "RADICO", "RVNL", "RAILTEL", "RAIN",
    "RAJESHEXPO", "RALLIS", "RAMCOCEM", "RATNAMANI", "RAYMOND", "RELIANCE", "RBA",
    "ROSSARI", "ROUTE", "SBICARD", "SBILIFE", "SJVN", "SKFINDIA", "SRF", "SAFARI",
    "MOTHERSON", "SANOFI", "SAPPHIRE", "SAREGAMA", "SCHAEFFLER", "SHARDACROP", "SHOPERSTOP",
    "SHREECEM", "SHRIRAMFIN", "SIEMENS", "SOBHA", "SOLARINDS", "SONACOMS", "STARHEALTH",
    "SBIN", "SAIL", "SUMICHEM", "SUNPHARMA", "SUNTV", "SUNDARMFIN", "SUNDRMFAST", "SUNTECK",
    "SUPRAJIT", "SUPREMEIND", "SUZLON", "SWANENERGY", "SYMPHONY", "SYNGENE", "TATACHEM",
    "TATACOMM", "TCS", "TATACONSUM", "TATAELXSI", "TATAMOTORS", "TATAPOWER", "TATASTEEL",
    "TATATECH", "TTML", "TEAMLEASE", "TECHM", "TEJASNET", "NIACL", "RAMCOIND", "THERMAX",
    "TIMKEN", "TITAGARH", "TITAN", "TORNTPHARM", "TORNTPOWER", "TRENT", "TRIDENT", "TRITURBINE",
    "TIINDIA", "UCOBANK", "UNOMINDA", "UPL", "UTIAMC", "UJJIVANSFB", "ULTRACEMCO", "UNIONBANK",
    "VGUARD", "VMART", "VIPIND", "VAIBHAVGBL", "VTL", "VARROC", "VBL", "VEDL", "VIJAYA",
    "IDEA", "VOLTAS", "WELCORP", "WELSPUNLIV", "WESTLIFE", "WHIRLPOOL", "WIPRO", "YESBANK",
    "ZEEL", "ZENSARTECH", "ZYDUSLIFE", "ZYDUSWELL"
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


class UniverseManager:
    """Manages Nifty 200 ticker list and security ID resolution."""

    def __init__(self, cache_path: str = DEFAULT_CACHE_PATH):
        self.cache_path = cache_path
        self._sec_ids: Dict[str, str] = dict(DEFAULT_SEC_IDS)
        self._symbols: List[str] = list(NIFTY_200_SYMBOLS)
        self.load_cache()

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
            req = urllib.request.Request(
                DHAN_SCRIP_MASTER_URL,
                headers={"User-Agent": "Mozilla/5.0 (TradingPlatform/ST15)"},
            )
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                csv_text = response.read().decode("utf-8", errors="ignore")

            reader = csv.reader(io.StringIO(csv_text))
            header = next(reader, None)
            if not header:
                return 0

            # Find column indices
            header_upper = [h.strip().upper() for h in header]
            sym_col = -1
            id_col = -1
            seg_col = -1

            for idx, col in enumerate(header_upper):
                if "SYMBOL" in col or "TRADING_SYMBOL" in col or "SEM_CUSTOM_SYMBOL" in col:
                    if sym_col == -1:
                        sym_col = idx
                if "SM_TOKEN" in col or "SECURITY_ID" in col or "SEM_SMST_SECURITY_ID" in col:
                    if id_col == -1:
                        id_col = idx
                if "EXCHANGE_SEGMENT" in col or "SEM_EXM_EXCH_ID" in col:
                    if seg_col == -1:
                        seg_col = idx

            if sym_col == -1 or id_col == -1:
                # Fallback standard columns
                sym_col = 1
                id_col = 0

            nifty_set = set(self._symbols)
            synced_count = 0

            for row in reader:
                if len(row) <= max(sym_col, id_col):
                    continue
                symbol = row[sym_col].strip().upper()
                sec_id = row[id_col].strip()

                if seg_col != -1 and len(row) > seg_col:
                    seg = row[seg_col].strip().upper()
                    if seg not in ("NSE_EQ", "NSE", "EQ", "E"):
                        continue

                # Strip '-EQ' or 'EQ' suffixes if present
                clean_sym = symbol.replace("-EQ", "").replace(".EQ", "").strip()

                if clean_sym in nifty_set and sec_id:
                    self._sec_ids[clean_sym] = sec_id
                    synced_count += 1

            logger.info("Successfully resolved %d Nifty 200 security IDs from Dhan", synced_count)
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
