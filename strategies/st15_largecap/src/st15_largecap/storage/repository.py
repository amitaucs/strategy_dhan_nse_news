"""SQLite Repository for ST15 LargeCap persistence."""

from datetime import datetime
import json
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

from st15_largecap.config import settings
from st15_largecap.core.models import Position, PositionStatus, ScanResult, SetupSignal, SignalStatus, TradeOrder

logger = logging.getLogger(__name__)


class Repository:
    """Thread-safe SQLite storage for ST15 LargeCap signals, scans, positions, and orders."""

    def __init__(self, db_path: str = settings.DATABASE_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_tables()

    def _init_tables(self) -> None:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS scan_results (
                symbol TEXT PRIMARY KEY,
                sec_id TEXT,
                ltp REAL,
                ema_20 REAL,
                ema_50 REAL,
                ema_200 REAL,
                is_ema_stacked INTEGER,
                is_in_dip INTEGER,
                nearest_ema TEXT,
                nearest_ema_dist_pct REAL,
                is_ha_green INTEGER,
                is_supertrend_green INTEGER,
                is_setup_ready INTEGER,
                swing_low REAL,
                scanned_at TEXT
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                sec_id TEXT,
                setup_time TEXT,
                trigger_price REAL,
                stop_loss_price REAL,
                target_profit_price REAL,
                risk_per_share REAL,
                risk_reward_ratio REAL,
                ema_20 REAL,
                ema_50 REAL,
                ema_200 REAL,
                supertrend REAL,
                nearest_ema_name TEXT,
                nearest_ema_dist_pct REAL,
                status TEXT,
                created_at TEXT
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                sec_id TEXT,
                quantity INTEGER,
                entry_price REAL,
                entry_time TEXT,
                stop_loss REAL,
                target_price REAL,
                current_price REAL,
                product_type TEXT,
                status TEXT,
                exit_price REAL,
                exit_time TEXT,
                order_id TEXT,
                exit_order_id TEXT,
                remarks TEXT
            )
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                symbol TEXT,
                sec_id TEXT,
                action TEXT,
                quantity INTEGER,
                entry_price REAL,
                stop_loss REAL,
                target_price REAL,
                product_type TEXT,
                order_type TEXT,
                status TEXT,
                dry_run INTEGER,
                placed_at TEXT,
                remarks TEXT
            )
            """)
            conn.commit()
        finally:
            conn.close()

    def save_scan_results(self, results: List[ScanResult]) -> None:
        """Upsert latest scan results."""
        if not results:
            return
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            cursor = conn.cursor()
            for r in results:
                cursor.execute("""
                INSERT OR REPLACE INTO scan_results (
                    symbol, sec_id, ltp, ema_20, ema_50, ema_200,
                    is_ema_stacked, is_in_dip, nearest_ema, nearest_ema_dist_pct,
                    is_ha_green, is_supertrend_green, is_setup_ready, swing_low, scanned_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r.symbol, r.sec_id, r.ltp, r.ema_20, r.ema_50, r.ema_200,
                    1 if r.is_ema_stacked else 0,
                    1 if r.is_in_dip else 0,
                    r.nearest_ema, r.nearest_ema_dist_pct,
                    1 if r.is_ha_green else 0,
                    1 if r.is_supertrend_green else 0,
                    1 if r.is_setup_ready else 0,
                    r.swing_low,
                    r.scanned_at.isoformat() if isinstance(r.scanned_at, datetime) else str(r.scanned_at),
                ))
            conn.commit()
        finally:
            conn.close()

    def get_latest_scans(self) -> List[Dict[str, Any]]:
        """Retrieve recent scan results."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scan_results ORDER BY is_setup_ready DESC, nearest_ema_dist_pct ASC")
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def save_signal(self, signal: SetupSignal) -> int:
        """Save a triggered setup signal."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO signals (
                symbol, sec_id, setup_time, trigger_price, stop_loss_price,
                target_profit_price, risk_per_share, risk_reward_ratio,
                ema_20, ema_50, ema_200, supertrend, nearest_ema_name,
                nearest_ema_dist_pct, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.symbol, signal.sec_id,
                signal.setup_time.isoformat() if isinstance(signal.setup_time, datetime) else str(signal.setup_time),
                signal.trigger_price, signal.stop_loss_price, signal.target_profit_price,
                signal.risk_per_share, signal.risk_reward_ratio,
                signal.ema_20, signal.ema_50, signal.ema_200, signal.supertrend,
                signal.nearest_ema_name, signal.nearest_ema_dist_pct,
                signal.status.value if hasattr(signal.status, "value") else str(signal.status),
                datetime.now().isoformat(),
            ))
            conn.commit()
            return cursor.lastrowid or 0
        finally:
            conn.close()

    def get_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent signals."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def save_order(self, order: TradeOrder) -> None:
        """Save a trade order record."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO orders (
                order_id, symbol, sec_id, action, quantity,
                entry_price, stop_loss, target_price, product_type,
                order_type, status, dry_run, placed_at, remarks
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order.order_id, order.symbol, order.sec_id, order.action, order.quantity,
                order.entry_price, order.stop_loss, order.target_price, order.product_type,
                order.order_type, order.status, 1 if order.dry_run else 0,
                order.placed_at.isoformat() if isinstance(order.placed_at, datetime) else str(order.placed_at),
                order.remarks,
            ))
            conn.commit()
        finally:
            conn.close()

    def get_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent trade orders."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders ORDER BY placed_at DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def save_position(self, pos: Position) -> int:
        """Create or update a position."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            cursor = conn.cursor()
            if pos.id:
                cursor.execute("""
                UPDATE positions SET
                    symbol=?, sec_id=?, quantity=?, entry_price=?, entry_time=?,
                    stop_loss=?, target_price=?, current_price=?, product_type=?,
                    status=?, exit_price=?, exit_time=?, order_id=?, exit_order_id=?, remarks=?
                WHERE id=?
                """, (
                    pos.symbol, pos.sec_id, pos.quantity, pos.entry_price,
                    pos.entry_time.isoformat() if isinstance(pos.entry_time, datetime) else str(pos.entry_time),
                    pos.stop_loss, pos.target_price, pos.current_price, pos.product_type,
                    pos.status.value if hasattr(pos.status, "value") else str(pos.status),
                    pos.exit_price,
                    pos.exit_time.isoformat() if isinstance(pos.exit_time, datetime) and pos.exit_time else None,
                    pos.order_id, pos.exit_order_id, pos.remarks, pos.id,
                ))
                conn.commit()
                return pos.id
            else:
                cursor.execute("""
                INSERT INTO positions (
                    symbol, sec_id, quantity, entry_price, entry_time,
                    stop_loss, target_price, current_price, product_type,
                    status, exit_price, exit_time, order_id, exit_order_id, remarks
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pos.symbol, pos.sec_id, pos.quantity, pos.entry_price,
                    pos.entry_time.isoformat() if isinstance(pos.entry_time, datetime) else str(pos.entry_time),
                    pos.stop_loss, pos.target_price, pos.current_price, pos.product_type,
                    pos.status.value if hasattr(pos.status, "value") else str(pos.status),
                    pos.exit_price,
                    pos.exit_time.isoformat() if isinstance(pos.exit_time, datetime) and pos.exit_time else None,
                    pos.order_id, pos.exit_order_id, pos.remarks,
                ))
                conn.commit()
                return cursor.lastrowid or 0
        finally:
            conn.close()

    def get_positions(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve positions optionally filtered by status."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM positions WHERE status=? ORDER BY id DESC", (status,))
            else:
                cursor.execute("SELECT * FROM positions ORDER BY id DESC")
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()


repository = Repository()
