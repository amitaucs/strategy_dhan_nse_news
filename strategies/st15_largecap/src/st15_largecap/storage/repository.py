"""Persistent Storage Repository for ST15 LargeCap Strategy.

Supports remote MySQL (MariaDB) with transparent local SQLite fallback.
All tables for this strategy are prefixed with 'st_':
  - st_scan_results
  - st_signals
  - st_positions
  - st_orders
"""

from datetime import datetime
from functools import wraps
import logging
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

from st15_largecap.config import settings
from st15_largecap.core.models import Position, PositionStatus, ScanResult, SetupSignal, SignalStatus, TradeOrder

logger = logging.getLogger(__name__)


def _thread_safe(method):
    """Decorator ensuring thread-safe atomic access to database operations."""
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


class Repository:
    """Storage repository supporting MySQL with transparent SQLite fallback and 'st_' table prefix."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        use_mysql: Optional[bool] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ):
        self._lock = threading.RLock()
        if use_mysql is None:
            self.use_mysql = settings.use_mysql if db_path is None else False
        else:
            self.use_mysql = use_mysql

        self.db_path = Path(db_path or settings.database_path)
        self.host = host or settings.mysql_host
        self.port = port or settings.mysql_port
        self.user = user or settings.mysql_user
        self.password = password or settings.mysql_password
        self.database = database or settings.mysql_database

        self.is_mysql_active = False
        self._mysql_conn = None
        self._sqlite_conn = None

        if self.use_mysql:
            self._init_mysql()

        if not self.is_mysql_active:
            self._init_sqlite()

        self._init_tables()

    def _init_mysql(self) -> bool:
        """Initialize connection to remote MySQL / MariaDB."""
        try:
            import pymysql
            import pymysql.cursors

            self._mysql_conn = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
                connect_timeout=10,
            )
            self.is_mysql_active = True
            logger.info("Connected to remote MySQL database: %s@%s:%s/%s",
                        self.user, self.host, self.port, self.database)
            return True
        except Exception as e:
            logger.warning("Could not connect to MySQL (%s). Falling back to SQLite (%s).", e, self.db_path)
            self.is_mysql_active = False
            return False

    def _init_sqlite(self) -> None:
        """Initialize local SQLite database fallback."""
        os.makedirs(self.db_path.parent, exist_ok=True)
        self._sqlite_conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=10.0)
        self._sqlite_conn.row_factory = sqlite3.Row
        self.is_mysql_active = False
        logger.info("Initialized SQLite storage at: %s", self.db_path)

    def _check_mysql_alive(self) -> bool:
        """Ping MySQL connection and reconnect if dropped."""
        if not self.is_mysql_active or not self._mysql_conn:
            return False
        try:
            self._mysql_conn.ping(reconnect=True)
            return True
        except Exception as e:
            logger.warning("MySQL connection ping failed (%s), attempting reconnect...", e)
            return self._init_mysql()

    def _init_tables(self) -> None:
        """Create ST15 tables prefixed with 'st_'."""
        with self._lock:
            if self.is_mysql_active and self._check_mysql_alive():
                self._init_mysql_tables()
            else:
                self._init_sqlite_tables()

    def _init_mysql_tables(self) -> None:
        with self._mysql_conn.cursor() as cursor:
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS st_scan_results (
                symbol VARCHAR(50) PRIMARY KEY,
                sec_id VARCHAR(50),
                ltp DOUBLE,
                ema_20 DOUBLE,
                ema_50 DOUBLE,
                ema_200 DOUBLE,
                is_ema_stacked TINYINT(1),
                is_in_dip TINYINT(1),
                nearest_ema VARCHAR(50),
                nearest_ema_dist_pct DOUBLE,
                is_ha_green TINYINT(1),
                is_supertrend_green TINYINT(1),
                is_setup_ready TINYINT(1),
                swing_low DOUBLE,
                invalidation_reason TEXT,
                scanned_at VARCHAR(50)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS st_signals (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(50),
                sec_id VARCHAR(50),
                setup_time VARCHAR(50),
                trigger_price DOUBLE,
                stop_loss_price DOUBLE,
                target_profit_price DOUBLE,
                risk_per_share DOUBLE,
                risk_reward_ratio DOUBLE,
                ema_20 DOUBLE,
                ema_50 DOUBLE,
                ema_200 DOUBLE,
                supertrend DOUBLE,
                nearest_ema_name VARCHAR(50),
                nearest_ema_dist_pct DOUBLE,
                status VARCHAR(50),
                invalidation_reason TEXT,
                created_at VARCHAR(50)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS st_positions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(50),
                sec_id VARCHAR(50),
                quantity INT,
                entry_price DOUBLE,
                entry_time VARCHAR(50),
                stop_loss DOUBLE,
                target_price DOUBLE,
                current_price DOUBLE,
                product_type VARCHAR(50),
                status VARCHAR(50),
                exit_price DOUBLE,
                exit_time VARCHAR(50),
                order_id VARCHAR(100),
                exit_order_id VARCHAR(100),
                remarks TEXT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS st_orders (
                order_id VARCHAR(100) PRIMARY KEY,
                symbol VARCHAR(50),
                sec_id VARCHAR(50),
                action VARCHAR(20),
                quantity INT,
                entry_price DOUBLE,
                stop_loss DOUBLE,
                target_price DOUBLE,
                product_type VARCHAR(50),
                order_type VARCHAR(50),
                status VARCHAR(50),
                dry_run TINYINT(1),
                placed_at VARCHAR(50),
                remarks TEXT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

    def _init_sqlite_tables(self) -> None:
        cursor = self._sqlite_conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS st_scan_results (
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
            invalidation_reason TEXT,
            scanned_at TEXT
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS st_signals (
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
            invalidation_reason TEXT,
            created_at TEXT
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS st_positions (
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
        CREATE TABLE IF NOT EXISTS st_orders (
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
        self._sqlite_conn.commit()

    def _execute(
        self,
        query: str,
        params: Tuple[Any, ...] = (),
        fetch_all: bool = False,
        fetch_one: bool = False,
        last_row_id: bool = False,
    ) -> Any:
        """Execute a query transparently across MySQL or SQLite."""
        with self._lock:
            if self.is_mysql_active and self._check_mysql_alive():
                # Adapt SQLite '?' parameter placeholders to MySQL '%s'
                mysql_query = query.replace("?", "%s")
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(mysql_query, params)
                    if fetch_all:
                        return cursor.fetchall() or []
                    if fetch_one:
                        return cursor.fetchone()
                    if last_row_id:
                        return cursor.lastrowid or 0
                    return cursor.rowcount
            else:
                if not self._sqlite_conn:
                    self._init_sqlite()
                cursor = self._sqlite_conn.cursor()
                cursor.execute(query, params)
                if fetch_all:
                    rows = cursor.fetchall()
                    return [dict(r) for r in rows] if rows else []
                if fetch_one:
                    row = cursor.fetchone()
                    return dict(row) if row else None
                self._sqlite_conn.commit()
                if last_row_id:
                    return cursor.lastrowid or 0
                return cursor.rowcount

    @_thread_safe
    def save_scan_results(self, results: List[ScanResult]) -> None:
        """Upsert latest scan results into st_scan_results."""
        if not results:
            return

        query = """
        REPLACE INTO st_scan_results (
            symbol, sec_id, ltp, ema_20, ema_50, ema_200,
            is_ema_stacked, is_in_dip, nearest_ema, nearest_ema_dist_pct,
            is_ha_green, is_supertrend_green, is_setup_ready, swing_low,
            invalidation_reason, scanned_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        for r in results:
            params = (
                r.symbol,
                r.sec_id,
                float(r.ltp),
                float(r.ema_20),
                float(r.ema_50),
                float(r.ema_200),
                1 if r.is_ema_stacked else 0,
                1 if r.is_in_dip else 0,
                r.nearest_ema,
                float(r.nearest_ema_dist_pct),
                1 if r.is_ha_green else 0,
                1 if r.is_supertrend_green else 0,
                1 if r.is_setup_ready else 0,
                float(r.swing_low or 0.0),
                r.invalidation_reason or "",
                r.scanned_at.isoformat() if isinstance(r.scanned_at, datetime) else str(r.scanned_at),
            )
            self._execute(query, params)

    @_thread_safe
    def get_latest_scans(self) -> List[Dict[str, Any]]:
        """Retrieve recent scan results from st_scan_results."""
        query = "SELECT * FROM st_scan_results ORDER BY is_setup_ready DESC, nearest_ema_dist_pct ASC"
        return self._execute(query, fetch_all=True)

    @_thread_safe
    def save_signal(self, signal: SetupSignal) -> int:
        """Save a triggered setup signal into st_signals."""
        query = """
        INSERT INTO st_signals (
            symbol, sec_id, setup_time, trigger_price, stop_loss_price,
            target_profit_price, risk_per_share, risk_reward_ratio,
            ema_20, ema_50, ema_200, supertrend, nearest_ema_name,
            nearest_ema_dist_pct, status, invalidation_reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            signal.symbol,
            signal.sec_id,
            signal.setup_time.isoformat() if isinstance(signal.setup_time, datetime) else str(signal.setup_time),
            float(signal.trigger_price),
            float(signal.stop_loss_price),
            float(signal.target_profit_price),
            float(signal.risk_per_share),
            float(signal.risk_reward_ratio),
            float(signal.ema_20),
            float(signal.ema_50),
            float(signal.ema_200),
            float(signal.supertrend),
            signal.nearest_ema_name,
            float(signal.nearest_ema_dist_pct),
            signal.status.value if hasattr(signal.status, "value") else str(signal.status),
            signal.invalidation_reason or "",
            datetime.now().isoformat(),
        )
        return self._execute(query, params, last_row_id=True)

    @_thread_safe
    def get_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent signals from st_signals."""
        query = "SELECT * FROM st_signals ORDER BY id DESC LIMIT ?"
        return self._execute(query, (limit,), fetch_all=True)

    @_thread_safe
    def update_signal_status(self, signal_id: int, status: str, invalidation_reason: str = "") -> bool:
        """Update status and invalidation reason of an existing signal."""
        query = "UPDATE st_signals SET status = ?, invalidation_reason = ? WHERE id = ?"
        return self._execute(query, (status, invalidation_reason, signal_id)) > 0

    @_thread_safe
    def save_position(self, pos: Position) -> int:
        """Create or update a position in st_positions."""
        if pos.id:
            query = """
            UPDATE st_positions SET
                symbol=?, sec_id=?, quantity=?, entry_price=?, entry_time=?,
                stop_loss=?, target_price=?, current_price=?, product_type=?,
                status=?, exit_price=?, exit_time=?, order_id=?, exit_order_id=?, remarks=?
            WHERE id=?
            """
            params = (
                pos.symbol,
                pos.sec_id,
                int(pos.quantity),
                float(pos.entry_price),
                pos.entry_time.isoformat() if isinstance(pos.entry_time, datetime) else str(pos.entry_time),
                float(pos.stop_loss),
                float(pos.target_price),
                float(pos.current_price),
                pos.product_type,
                pos.status.value if hasattr(pos.status, "value") else str(pos.status),
                float(pos.exit_price) if pos.exit_price is not None else None,
                pos.exit_time.isoformat() if isinstance(pos.exit_time, datetime) and pos.exit_time else None,
                pos.order_id,
                pos.exit_order_id,
                pos.remarks,
                pos.id,
            )
            self._execute(query, params)
            return pos.id
        else:
            query = """
            INSERT INTO st_positions (
                symbol, sec_id, quantity, entry_price, entry_time,
                stop_loss, target_price, current_price, product_type,
                status, exit_price, exit_time, order_id, exit_order_id, remarks
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                pos.symbol,
                pos.sec_id,
                int(pos.quantity),
                float(pos.entry_price),
                pos.entry_time.isoformat() if isinstance(pos.entry_time, datetime) else str(pos.entry_time),
                float(pos.stop_loss),
                float(pos.target_price),
                float(pos.current_price),
                pos.product_type,
                pos.status.value if hasattr(pos.status, "value") else str(pos.status),
                float(pos.exit_price) if pos.exit_price is not None else None,
                pos.exit_time.isoformat() if isinstance(pos.exit_time, datetime) and pos.exit_time else None,
                pos.order_id,
                pos.exit_order_id,
                pos.remarks,
            )
            return self._execute(query, params, last_row_id=True)

    @_thread_safe
    def get_positions(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve positions optionally filtered by status from st_positions."""
        if status:
            query = "SELECT * FROM st_positions WHERE status=? ORDER BY id DESC"
            return self._execute(query, (status,), fetch_all=True)
        query = "SELECT * FROM st_positions ORDER BY id DESC"
        return self._execute(query, fetch_all=True)

    @_thread_safe
    def save_order(self, order: TradeOrder) -> None:
        """Save or update a trade order record in st_orders."""
        query = """
        REPLACE INTO st_orders (
            order_id, symbol, sec_id, action, quantity,
            entry_price, stop_loss, target_price, product_type,
            order_type, status, dry_run, placed_at, remarks
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            order.order_id,
            order.symbol,
            order.sec_id,
            order.action,
            int(order.quantity),
            float(order.entry_price),
            float(order.stop_loss),
            float(order.target_price),
            order.product_type,
            order.order_type,
            order.status,
            1 if order.dry_run else 0,
            order.placed_at.isoformat() if isinstance(order.placed_at, datetime) else str(order.placed_at),
            order.remarks,
        )
        self._execute(query, params)

    @_thread_safe
    def get_orders(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent trade orders from st_orders."""
        query = "SELECT * FROM st_orders ORDER BY placed_at DESC LIMIT ?"
        return self._execute(query, (limit,), fetch_all=True)

    @_thread_safe
    def get_today_orders(self) -> List[Dict[str, Any]]:
        """Retrieve trade orders placed today from st_orders."""
        today_prefix = datetime.now().strftime("%Y-%m-%d")
        query = "SELECT * FROM st_orders WHERE placed_at LIKE ? ORDER BY placed_at DESC"
        return self._execute(query, (f"{today_prefix}%",), fetch_all=True)

    @_thread_safe
    def get_today_active_order_count(self) -> int:
        """Count active or filled orders placed today."""
        today_orders = self.get_today_orders()
        return sum(
            1 for o in today_orders
            if o.get("status") in ("PLACED", "SIMULATED", "FILLED", "OPEN")
        )

    def close(self) -> None:
        """Close open database connections."""
        with self._lock:
            if self._mysql_conn:
                try:
                    self._mysql_conn.close()
                except Exception:
                    pass
                self._mysql_conn = None
            if self._sqlite_conn:
                try:
                    self._sqlite_conn.close()
                except Exception:
                    pass
                self._sqlite_conn = None
            self.is_mysql_active = False


repository = Repository()

__all__ = ["Repository", "repository"]

