"""Universal Dynamic Market Universe Manager with DhanHQ & NSE Synchronization."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import threading
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Default URLs
DHAN_SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
NSE_INDEX_URLS = {
    "NIFTY_50": "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
    "NIFTY_100": "https://archives.nseindia.com/content/indices/ind_nifty100list.csv",
    "NIFTY_200": "https://archives.nseindia.com/content/indices/ind_nifty200list.csv",
    "NIFTY_500": "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    "NIFTY_MIDCAP_100": "https://archives.nseindia.com/content/indices/ind_niftymidcap100list.csv",
    "NIFTY_SMALLCAP_100": "https://archives.nseindia.com/content/indices/ind_niftysmallcap100list.csv",
}

CACHE_TTL_SECONDS = 86400  # 24 hours


class DhanUniverseManager:
    """Manages dynamic synchronisation and local caching of all NSE stock universes."""

    _instance: Optional[DhanUniverseManager] = None
    _lock = threading.Lock()

    def __init__(self, cache_dir: Optional[str | Path] = None) -> None:
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            # Resolve data/universes in project root or relative directory
            base_dir = Path(os.getenv("UNIVERSE_DATA_DIR", "data/universes"))
            if not base_dir.is_absolute():
                # Attempt to find project root or fallback to cwd/data/universes
                curr = Path.cwd()
                while curr != curr.parent and not (curr / "scanners").exists() and not (curr / "strategies").exists():
                    curr = curr.parent
                base_dir = curr / "data" / "universes"
            self.cache_dir = base_dir

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._fno_lot_sizes: Dict[str, int] = {}
        self._fno_symbols_set: Set[str] = set()
        self._equity_sec_ids: Dict[str, str] = {}
        self._init_memory_from_cache()

    @classmethod
    def get_instance(cls, cache_dir: Optional[str | Path] = None) -> DhanUniverseManager:
        """Get or create singleton instance of DhanUniverseManager."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(cache_dir=cache_dir)
            return cls._instance

    def _get_cache_path(self, universe_key: str) -> Path:
        norm = universe_key.lower().replace("_", "")
        return self.cache_dir / f"{norm}_universe.json"

    def _init_memory_from_cache(self) -> None:
        """Load any existing valid cached universes on startup."""
        for key in ["fno", "nifty50", "nifty100", "nifty200", "nifty500", "niftymidcap100", "niftysmallcap100", "dhanequitymaster"]:
            cpath = self._get_cache_path(key)
            if cpath.exists():
                try:
                    with open(cpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        u_name = data.get("universe", key.upper())
                        self._memory_cache[u_name] = data
                        self._memory_cache[key.upper()] = data
                        if key == "fno":
                            self._fno_symbols_set = set(data.get("symbols", []))
                            self._fno_lot_sizes = {k: int(v) for k, v in data.get("lot_sizes", {}).items()}
                        elif key == "dhanequitymaster":
                            self._equity_sec_ids = data.get("equity_sec_ids", {})
                except Exception as exc:
                    logger.warning("Could not load universe cache for %s: %s", key, exc)

    def is_cache_valid(self, universe_key: str) -> bool:
        """Check if universe cache file exists, is valid JSON with metadata, and is within 24-hour TTL."""
        cpath = self._get_cache_path(universe_key)
        if not cpath.exists():
            return False
        try:
            with open(cpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    if "last_updated" in data:
                        lu = datetime.strptime(data["last_updated"], "%Y-%m-%d %H:%M:%S")
                        ttl = data.get("ttl_seconds", CACHE_TTL_SECONDS)
                        return (datetime.now() - lu).total_seconds() < ttl
            mtime = cpath.stat().st_mtime
            return (time.time() - mtime) < CACHE_TTL_SECONDS
        except Exception:
            return False

    def sync_all(self, force: bool = False) -> Dict[str, Any]:
        """Download latest Dhan Scrip Master and official NSE index constituent lists."""
        logger.info("🔄 [Universe Manager] Starting dynamic universe synchronization (force=%s)...", force)
        summary: Dict[str, Any] = {"status": "SUCCESS", "synced": [], "errors": []}

        # 1. Sync Dhan Scrip Master for Equity and F&O derivatives
        dhan_ok = self._sync_dhan_scrip_master(force=force)
        if dhan_ok:
            summary["synced"].append("DHAN_SCRIP_MASTER")
            summary["synced"].append("ALL_F_AND_O")
        else:
            summary["errors"].append("DHAN_SCRIP_MASTER")

        # 2. Sync NSE Index Constituent Lists
        for idx_name, url in NSE_INDEX_URLS.items():
            if not force and self.is_cache_valid(idx_name):
                logger.info("ℹ️ [Universe Manager] Cache for %s is fresh. Skipping download.", idx_name)
                summary["synced"].append(f"{idx_name} (Cached)")
                continue

            idx_ok = self._sync_nse_index(idx_name, url)
            if idx_ok:
                summary["synced"].append(idx_name)
            else:
                summary["errors"].append(idx_name)

        logger.info("✅ [Universe Manager] Universal sync finished: %s", summary)
        return summary

    def _sync_dhan_scrip_master(self, force: bool = False) -> bool:
        """Download and parse Dhan's official Scrip Master CSV."""
        if not force and self.is_cache_valid("fno") and self.is_cache_valid("dhan_equity_master"):
            logger.info("ℹ️ [Universe Manager] Dhan Scrip Master cache is fresh.")
            return True

        try:
            logger.info("📥 [Universe Manager] Downloading Dhan Scrip Master from %s...", DHAN_SCRIP_MASTER_URL)
            req = urllib.request.Request(DHAN_SCRIP_MASTER_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                csv_bytes = resp.read()

            lines = [line.decode("utf-8", errors="ignore") for line in io.BytesIO(csv_bytes).readlines()]
            reader = csv.DictReader(lines)

            equity_sec_ids: Dict[str, str] = {}
            fno_symbols_dict: Dict[str, int] = {}
            fno_sec_ids: Dict[str, str] = {}

            for row in reader:
                exch = row.get("SEM_EXM_EXCH_ID", "").strip()
                if exch != "NSE":
                    continue

                inst = row.get("SEM_INSTRUMENT_NAME", "").strip()
                trading_sym = row.get("SEM_TRADING_SYMBOL", "").strip()
                custom_sym = row.get("SEM_CUSTOM_SYMBOL", "").strip()
                sec_id = row.get("SEM_SMST_SECURITY_ID", "").strip()
                series = row.get("SEM_SERIES", "").strip()

                # 1. Cash Equity mapping (NSE_EQ)
                if inst == "EQUITY" and series == "EQ":
                    if trading_sym and sec_id:
                        equity_sec_ids[trading_sym] = sec_id

                # 2. Stock Options & Futures (NSE_FNO)
                if inst in ("OPTSTK", "FUTSTK"):
                    # Extract root underlying symbol
                    root_sym = custom_sym.split()[0] if custom_sym else trading_sym.split("-")[0]
                    if root_sym and "NSETEST" not in root_sym.upper() and not root_sym.startswith("0"):
                        lot_val = row.get("SEM_LOT_UNITS", 0)
                        try:
                            lot = int(float(lot_val)) if lot_val else 250
                        except Exception:
                            lot = 250
                        if root_sym not in fno_symbols_dict:
                            fno_symbols_dict[root_sym] = lot

            self._equity_sec_ids = equity_sec_ids

            # Associate underlying security ID with F&O symbols
            sorted_fno_symbols = sorted(fno_symbols_dict.keys())
            for sym in sorted_fno_symbols:
                if sym in equity_sec_ids:
                    fno_sec_ids[sym] = equity_sec_ids[sym]

            # Support legacy alias for TATAMOTORS -> TMPV
            if "TMPV" in fno_sec_ids and "TATAMOTORS" not in fno_sec_ids:
                fno_sec_ids["TATAMOTORS"] = fno_sec_ids["TMPV"]
                fno_symbols_dict["TATAMOTORS"] = fno_symbols_dict.get("TMPV", 250)
                if "TATAMOTORS" not in sorted_fno_symbols:
                    sorted_fno_symbols.append("TATAMOTORS")
                    sorted_fno_symbols.sort()

            self._fno_symbols_set = set(sorted_fno_symbols)
            self._fno_lot_sizes = fno_symbols_dict

            now = datetime.now()
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")
            expires_str = (now + timedelta(seconds=CACHE_TTL_SECONDS)).strftime("%Y-%m-%d %H:%M:%S")

            # Save F&O Universe Cache
            fno_data = {
                "version": 1,
                "universe": "ALL_F_AND_O",
                "count": len(sorted_fno_symbols),
                "last_updated": now_str,
                "expires_at": expires_str,
                "ttl_seconds": CACHE_TTL_SECONDS,
                "symbols": sorted_fno_symbols,
                "lot_sizes": fno_symbols_dict,
                "security_ids": fno_sec_ids,
            }
            with open(self._get_cache_path("fno"), "w", encoding="utf-8") as f:
                json.dump(fno_data, f, indent=2)
            self._memory_cache["ALL_F_AND_O"] = fno_data
            self._memory_cache["FNO"] = fno_data

            # Save Dhan Equity Master Cache
            eq_data = {
                "version": 1,
                "count": len(equity_sec_ids),
                "last_updated": now_str,
                "expires_at": expires_str,
                "ttl_seconds": CACHE_TTL_SECONDS,
                "equity_sec_ids": equity_sec_ids,
            }
            with open(self._get_cache_path("dhan_equity_master"), "w", encoding="utf-8") as f:
                json.dump(eq_data, f, indent=2)
            self._memory_cache["DHAN_EQUITY_MASTER"] = eq_data

            logger.info("✅ [Universe Manager] Parsed %d NSE Cash Equities & %d Active F&O Underlyings from Dhan.", len(equity_sec_ids), len(sorted_fno_symbols))
            return True
        except Exception as exc:
            logger.error("❌ [Universe Manager] Failed to sync Dhan Scrip Master: %s", exc)
            return False

    def _sync_nse_index(self, index_name: str, url: str) -> bool:
        """Download index constituents from NSE and map to Dhan security IDs."""
        try:
            logger.info("📥 [Universe Manager] Fetching %s constituents from %s...", index_name, url)
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                lines = [l.decode("utf-8", errors="ignore") for l in resp.readlines()]

            reader = csv.DictReader(lines)
            symbols: List[str] = []
            for row in reader:
                sym = row.get("Symbol", "").strip()
                if sym and sym not in symbols:
                    symbols.append(sym)

            if not symbols:
                logger.warning("⚠️ [Universe Manager] No symbols found for %s from NSE feed.", index_name)
                return False

            symbols.sort()
            sec_ids: Dict[str, str] = {}
            for s in symbols:
                if s in self._equity_sec_ids:
                    sec_ids[s] = self._equity_sec_ids[s]

            now = datetime.now()
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")
            expires_str = (now + timedelta(seconds=CACHE_TTL_SECONDS)).strftime("%Y-%m-%d %H:%M:%S")
            data = {
                "version": 1,
                "universe": index_name,
                "count": len(symbols),
                "last_updated": now_str,
                "expires_at": expires_str,
                "ttl_seconds": CACHE_TTL_SECONDS,
                "symbols": symbols,
                "security_ids": sec_ids,
            }

            with open(self._get_cache_path(index_name), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._memory_cache[index_name] = data

            logger.info("✅ [Universe Manager] %s synced with %d symbols (%d security IDs mapped).", index_name, len(symbols), len(sec_ids))
            return True
        except Exception as exc:
            logger.error("❌ [Universe Manager] Error syncing %s: %s", index_name, exc)
            return False

    def is_fno_stock(self, symbol: str) -> bool:
        """Check if a stock ticker is currently an active NSE F&O underlying."""
        if not self._fno_symbols_set:
            self._ensure_loaded("fno")
        return symbol.upper() in self._fno_symbols_set

    def get_lot_size(self, symbol: str, default: Optional[int] = None) -> Optional[int]:
        """Get exact exchange lot size for a stock symbol from verified F&O master."""
        if not self._fno_lot_sizes:
            self._ensure_loaded("fno")
        return self._fno_lot_sizes.get(symbol.upper(), default)

    def _ensure_loaded(self, universe_key: str) -> None:
        """Ensure universe is loaded from cache or triggers initial sync if missing."""
        cpath = self._get_cache_path(universe_key)
        if not cpath.exists() or not self.is_cache_valid(universe_key):
            self.sync_all(force=False)
        else:
            self._init_memory_from_cache()

    def get_universe(
        self,
        universe_name: Optional[str] = None,
    ) -> Tuple[str, List[str], Dict[str, str]]:
        """Retrieve symbol list and security ID mapping for any supported universe.

        Supports:
          - ALL_F_AND_O / FNO
          - NIFTY_50
          - NIFTY_100
          - NIFTY_200
          - NIFTY_500
          - NIFTY_SMALLCAP_100
        """
        val = universe_name or os.getenv("UNIVERSE") or "NIFTY_50"
        norm = str(val).strip().upper()

        key = "NIFTY_50"
        if norm in ("ALL_F_AND_O", "ALL_FNO", "FNO", "F&O", "F_AND_O"):
            key = "ALL_F_AND_O"
        elif norm in ("NIFTY_500", "NIFTY500", "500", "NSE_500", "NSE500"):
            key = "NIFTY_500"
        elif norm in ("NIFTY_200", "NIFTY200", "200"):
            key = "NIFTY_200"
        elif norm in ("NIFTY_100", "NIFTY100", "100"):
            key = "NIFTY_100"
        elif norm in ("NIFTY_MIDCAP_100", "NIFTY_MIDCAP", "MIDCAP_100", "MIDCAP", "NIFTYMIDCAP100"):
            key = "NIFTY_MIDCAP_100"
        elif norm in ("NIFTY_SMALLCAP_100", "NIFTY_SMALLCAP", "SMALLCAP_100", "SMALLCAP"):
            key = "NIFTY_SMALLCAP_100"
        elif norm in ("NIFTY_50", "NIFTY50", "50"):
            key = "NIFTY_50"

        disk_key = "fno" if key == "ALL_F_AND_O" else key.lower()
        if not self.is_cache_valid(disk_key):
            logger.info("ℹ️ [Universe Manager] Cache for '%s' is expired or missing. Triggering fresh sync...", key)
            self.sync_all(force=True)

        # Check memory cache if fresh
        if key in self._memory_cache and self.is_cache_valid(disk_key):
            d = self._memory_cache[key]
            return key, list(d.get("symbols", [])), dict(d.get("security_ids", {}))

        # Check disk cache if fresh
        cpath = self._get_cache_path(disk_key)
        if cpath.exists() and self.is_cache_valid(disk_key):
            try:
                with open(cpath, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    self._memory_cache[key] = d
                    return key, list(d.get("symbols", [])), dict(d.get("security_ids", {}))
            except Exception:
                pass

        # Fallback to in-memory if sync ran or partial available
        if key in self._memory_cache:
            d = self._memory_cache[key]
            return key, list(d.get("symbols", [])), dict(d.get("security_ids", {}))

        return key, [], {}


# Global helper functions
def get_universe_manager() -> DhanUniverseManager:
    return DhanUniverseManager.get_instance()


def is_fno_stock(symbol: str) -> bool:
    return get_universe_manager().is_fno_stock(symbol)


def get_fno_lot_size(symbol: str, default: Optional[int] = None) -> Optional[int]:
    return get_universe_manager().get_lot_size(symbol, default=default)

