"""Storage and retrieval manager for EOD Multi-Scanner Daily Digest snapshots."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EODReportStore:
    """Manages persistent database (MySQL / SQLite) & JSON file caching for daily EOD multi-scanner digests."""

    def __init__(self, base_dir: Optional[Path] = None, storage: Optional[Any] = None) -> None:
        if base_dir is None:
            import os
            env_dir = os.getenv("EOD_DATA_DIR")
            if env_dir:
                self.base_dir = Path(env_dir)
            elif Path("/app/data").exists():
                self.base_dir = Path("/app/data/eod_scans")
            else:
                # Default to repo root / data / eod_scans
                cur = Path(__file__).resolve()
                root = None
                for parent in cur.parents:
                    if (parent / "data").exists() or (parent / "scanners").exists():
                        root = parent
                        break
                self.base_dir = (root / "data" / "eod_scans") if root else Path("data/eod_scans")
        else:
            self.base_dir = Path(base_dir)

        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.storage = storage
        self._mem_cache: Dict[str, Dict[str, Any]] = {}
        if self.storage is None:
            try:
                from news_based_strategy.storage.repository import StrategyStorage
                self.storage = StrategyStorage()
            except Exception as e:
                logger.debug(f"StrategyStorage not available for EODReportStore: {e}")
                self.storage = None

    def save_report(self, report_dict: Dict[str, Any]) -> Path:
        """Save an EOD digest report into Database (MySQL/SQLite) and JSON file cache."""
        date_str = report_dict.get("date")
        if not date_str:
            raise ValueError("Report dictionary missing 'date' key")

        # Update in-memory cache immediately
        self._mem_cache[date_str] = report_dict
        self._mem_cache["latest"] = report_dict

        # 1. Primary: Save to relational database
        if self.storage is not None:
            try:
                self.storage.save_eod_digest_report(report_dict)
            except Exception as e:
                logger.error(f"Failed to save EOD report to database for date {date_str}: {e}")

        # 2. Secondary / File Cache: Save to dated json and latest.json
        file_path = self.base_dir / f"{date_str}.json"
        latest_path = self.base_dir / "latest.json"

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(report_dict, f, indent=2, ensure_ascii=False)

            with open(latest_path, "w", encoding="utf-8") as f:
                json.dump(report_dict, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to write EOD file cache for date {date_str}: {e}")

        logger.info(f"EOD Report saved successfully for date {date_str} (DB + file {file_path})")
        return file_path

    def get_latest_report(self) -> Optional[Dict[str, Any]]:
        """Load the most recent EOD digest report from Database, with fallback to file cache."""
        if "latest" in self._mem_cache:
            return self._mem_cache["latest"]

        # 1. Try DB primary
        if self.storage is not None:
            try:
                db_report = self.storage.get_latest_eod_digest_report()
                if db_report:
                    d = db_report.get("date")
                    if d:
                        self._mem_cache[d] = db_report
                    self._mem_cache["latest"] = db_report
                    return db_report
            except Exception as e:
                logger.warning(f"Failed to read latest EOD report from DB: {e}")

        # 2. Fallback to latest.json
        latest_path = self.base_dir / "latest.json"
        if latest_path.exists():
            try:
                with open(latest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._mem_cache["latest"] = data
                    if data.get("date"):
                        self._mem_cache[data["date"]] = data
                    return data
            except Exception as e:
                logger.error(f"Failed to read latest EOD report file: {e}")

        # 3. Fallback to the latest dated file
        dates = self.list_available_dates()
        if dates:
            res = self.get_report_by_date(dates[0])
            if res:
                self._mem_cache["latest"] = res
            return res
        return None

    def get_report_by_date(self, date_str: str) -> Optional[Dict[str, Any]]:
        """Load an EOD report for a specific date (YYYY-MM-DD) from Database or file cache."""
        if date_str in self._mem_cache:
            return self._mem_cache[date_str]

        # 1. Try DB primary
        if self.storage is not None:
            try:
                db_report = self.storage.get_eod_digest_report_by_date(date_str)
                if db_report:
                    self._mem_cache[date_str] = db_report
                    return db_report
            except Exception as e:
                logger.warning(f"Failed to read EOD report for date {date_str} from DB: {e}")

        # 2. Fallback to dated file
        file_path = self.base_dir / f"{date_str}.json"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._mem_cache[date_str] = data
                    return data
            except Exception as e:
                logger.error(f"Failed to read EOD report file for date {date_str}: {e}")
        return None

    def list_available_dates(self) -> List[str]:
        """Return list of available report dates in descending chronological order."""
        date_set = set()

        # 1. Query DB dates
        if self.storage is not None:
            try:
                db_dates = self.storage.list_eod_digest_dates()
                date_set.update(db_dates)
            except Exception as e:
                logger.warning(f"Failed to list EOD dates from DB: {e}")

        # 2. Query file system cache dates
        if self.base_dir.exists():
            for p in self.base_dir.glob("*.json"):
                if p.stem != "latest" and len(p.stem) == 10 and p.stem.count("-") == 2:
                    date_set.add(p.stem)

        dates = sorted(list(date_set), reverse=True)
        return dates
