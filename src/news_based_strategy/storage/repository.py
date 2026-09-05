"""Persistent storage for filing deduplication, audit logs, and trade executions.

Supports remote MySQL (MariaDB) with transparent local SQLite fallback.
"""

from datetime import datetime
import logging
import os
from pathlib import Path
import sqlite3
from typing import Dict, Optional, Set
from news_based_strategy.config import settings
from news_based_strategy.core.models import FilingAudit, TradeResult

logger = logging.getLogger(__name__)


class StrategyStorage:
    """Manages persistent storage with MySQL primary and SQLite fallback."""

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
        if use_mysql is None:
            # Default to settings.use_mysql unless a custom db_path is explicitly provided
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

    @property
    def conn(self):
        """Active underlying DB connection (pymysql or sqlite3)."""
        return self._mysql_conn if self.is_mysql_active else self._sqlite_conn

    def _init_mysql(self) -> bool:
        """Initialize connection to remote MySQL / MariaDB."""
        try:
            import pymysql

            self._mysql_conn = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                connect_timeout=10,
                autocommit=True,
            )
            self.is_mysql_active = True
            logger.info(
                "Connected to MySQL database '%s' on %s:%s",
                self.database,
                self.host,
                self.port,
            )
            return True
        except Exception as e:
            logger.warning(
                "Could not connect to MySQL (%s:%s/%s): %s. Falling back to SQLite.",
                self.host,
                self.port,
                self.database,
                e,
            )
            self.is_mysql_active = False
            self._mysql_conn = None
            return False

    def _init_sqlite(self) -> None:
        """Initialize connection to local SQLite database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._sqlite_conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        logger.debug("Initialized local SQLite database at %s", self.db_path)

    def _ensure_connection(self) -> None:
        """Ensure active database connection with automatic reconnection for MySQL."""
        if self.is_mysql_active and self._mysql_conn:
            try:
                self._mysql_conn.ping(reconnect=True)
            except Exception as e:
                logger.warning("MySQL connection ping failed: %s. Falling back to SQLite.", e)
                self.is_mysql_active = False
                if not self._sqlite_conn:
                    self._init_sqlite()
                    self._init_tables()

    def _init_tables(self) -> None:
        """Create necessary tables if they do not exist."""
        if self.is_mysql_active:
            try:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS processed_filings (
                            seq_id VARCHAR(64) PRIMARY KEY,
                            symbol VARCHAR(32) NOT NULL,
                            an_dt VARCHAR(64),
                            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            INDEX idx_symbol (symbol),
                            INDEX idx_processed_at (processed_at)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """
                    )
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS audit_logs (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            seq_id VARCHAR(64) NOT NULL,
                            symbol VARCHAR(32) NOT NULL,
                            sentiment VARCHAR(16) NOT NULL,
                            confidence INT NOT NULL,
                            catalyst_type VARCHAR(64) NOT NULL,
                            material_impact TINYINT NOT NULL,
                            summary TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            INDEX idx_seq_id (seq_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """
                    )
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS trade_executions (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            symbol VARCHAR(32) NOT NULL,
                            action VARCHAR(8) NOT NULL,
                            quantity INT NOT NULL,
                            product_type VARCHAR(16) NOT NULL,
                            order_id VARCHAR(64),
                            remarks TEXT,
                            dry_run TINYINT NOT NULL,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """
                    )
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS system_settings (
                            `key` VARCHAR(64) PRIMARY KEY,
                            `value` TEXT NOT NULL,
                            `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """
                    )
                return
            except Exception as e:
                logger.warning("Failed creating MySQL tables: %s. Reverting to SQLite.", e)
                self.is_mysql_active = False
                self._init_sqlite()

        if self._sqlite_conn:
            with self._sqlite_conn:
                self._sqlite_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS processed_filings (
                        seq_id TEXT PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        an_dt TEXT,
                        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                self._sqlite_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        seq_id TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        sentiment TEXT NOT NULL,
                        confidence INTEGER NOT NULL,
                        catalyst_type TEXT NOT NULL,
                        material_impact INTEGER NOT NULL,
                        summary TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                self._sqlite_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS trade_executions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        action TEXT NOT NULL,
                        quantity INTEGER NOT NULL,
                        product_type TEXT NOT NULL,
                        order_id TEXT,
                        remarks TEXT,
                        dry_run INTEGER NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                self._sqlite_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS system_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

    def is_processed(self, seq_id: str) -> bool:
        """Check if an announcement has already been processed."""
        if not seq_id:
            return False
        self._ensure_connection()
        if self.is_mysql_active:
            with self._mysql_conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM processed_filings WHERE seq_id = %s", (seq_id,))
                return cursor.fetchone() is not None
        elif self._sqlite_conn:
            cursor = self._sqlite_conn.cursor()
            cursor.execute("SELECT 1 FROM processed_filings WHERE seq_id = ?", (seq_id,))
            return cursor.fetchone() is not None
        return False

    def mark_processed(self, seq_id: str, symbol: str, an_dt: str = "") -> None:
        """Record an announcement as processed."""
        if not seq_id:
            return
        self._ensure_connection()
        if self.is_mysql_active:
            try:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT IGNORE INTO processed_filings (seq_id, symbol, an_dt) VALUES (%s, %s, %s)",
                        (seq_id, symbol, an_dt),
                    )
            except Exception as e:
                logger.warning("Failed to mark_processed in MySQL: %s", e)
        elif self._sqlite_conn:
            with self._sqlite_conn:
                self._sqlite_conn.execute(
                    "INSERT OR IGNORE INTO processed_filings (seq_id, symbol, an_dt) VALUES (?, ?, ?)",
                    (seq_id, symbol, an_dt),
                )

    def get_processed_seq_ids(self, limit: int = 2000) -> Set[str]:
        """Preload recently processed sequence IDs into a Python set."""
        self._ensure_connection()
        try:
            if self.is_mysql_active:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT seq_id FROM processed_filings ORDER BY processed_at DESC LIMIT %s",
                        (limit,),
                    )
                    return {str(row[0]) for row in cursor.fetchall()}
            elif self._sqlite_conn:
                cursor = self._sqlite_conn.cursor()
                cursor.execute(
                    "SELECT seq_id FROM processed_filings ORDER BY processed_at DESC LIMIT ?",
                    (limit,),
                )
                return {str(row[0]) for row in cursor.fetchall()}
        except Exception as e:
            logger.warning("Error fetching processed_seq_ids: %s", e)
        return set()

    def save_audit(self, seq_id: str, symbol: str, audit: FilingAudit) -> None:
        """Save an AI filing audit."""
        self._ensure_connection()
        if self.is_mysql_active:
            try:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO audit_logs (seq_id, symbol, sentiment, confidence, catalyst_type, material_impact, summary)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            seq_id,
                            symbol,
                            audit.sentiment,
                            int(audit.confidence),
                            audit.catalyst_type,
                            1 if audit.material_impact else 0,
                            audit.summary,
                        ),
                    )
            except Exception as e:
                logger.warning("Failed to save audit in MySQL: %s", e)
        elif self._sqlite_conn:
            with self._sqlite_conn:
                self._sqlite_conn.execute(
                    """
                    INSERT INTO audit_logs (seq_id, symbol, sentiment, confidence, catalyst_type, material_impact, summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        seq_id,
                        symbol,
                        audit.sentiment,
                        int(audit.confidence),
                        audit.catalyst_type,
                        1 if audit.material_impact else 0,
                        audit.summary,
                    ),
                )

    def save_trade(self, result: TradeResult) -> None:
        """Log a trade execution attempt."""
        self._ensure_connection()
        if self.is_mysql_active:
            try:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO trade_executions (symbol, action, quantity, product_type, order_id, remarks, dry_run)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            result.symbol,
                            result.action,
                            result.quantity,
                            result.product_type,
                            result.order_id,
                            result.remarks,
                            1 if result.dry_run else 0,
                        ),
                    )
            except Exception as e:
                logger.warning("Failed to save trade in MySQL: %s", e)
        elif self._sqlite_conn:
            with self._sqlite_conn:
                self._sqlite_conn.execute(
                    """
                    INSERT INTO trade_executions (symbol, action, quantity, product_type, order_id, remarks, dry_run)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.symbol,
                        result.action,
                        result.quantity,
                        result.product_type,
                        result.order_id,
                        result.remarks,
                        1 if result.dry_run else 0,
                    ),
                )

    def get_processed_count(self) -> int:
        """Return the total number of processed filings."""
        self._ensure_connection()
        if self.is_mysql_active:
            with self._mysql_conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM processed_filings")
                row = cursor.fetchone()
                return int(row[0]) if row else 0
        elif self._sqlite_conn:
            cursor = self._sqlite_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM processed_filings")
            row = cursor.fetchone()
            return int(row[0]) if row else 0
        return 0

    def get_today_order_count(self) -> int:
        """Return the number of successfully placed orders today."""
        self._ensure_connection()
        today_prefix = datetime.now().strftime("%Y-%m-%d")
        if self.is_mysql_active:
            try:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM trade_executions WHERE DATE(timestamp) = CURRENT_DATE AND order_id IS NOT NULL"
                    )
                    row = cursor.fetchone()
                    return int(row[0]) if row else 0
            except Exception as e:
                logger.warning("Failed querying today order count in MySQL: %s", e)
        elif self._sqlite_conn:
            try:
                cursor = self._sqlite_conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM trade_executions WHERE timestamp LIKE ? AND order_id IS NOT NULL",
                    (f"{today_prefix}%",),
                )
                row = cursor.fetchone()
                return int(row[0]) if row else 0
            except Exception as e:
                logger.warning("Failed querying today order count in SQLite: %s", e)
        return 0

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve a stored setting value by key."""
        if not key:
            return default
        self._ensure_connection()
        try:
            if self.is_mysql_active and self._mysql_conn:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute("SELECT `value` FROM system_settings WHERE `key` = %s", (key,))
                    row = cursor.fetchone()
                    return str(row[0]) if row and row[0] is not None else default
            elif self._sqlite_conn:
                cursor = self._sqlite_conn.cursor()
                cursor.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
                row = cursor.fetchone()
                return str(row[0]) if row and row[0] is not None else default
        except Exception as e:
            logger.warning("Error fetching setting '%s': %s", key, e)
        return default

    def set_setting(self, key: str, value: str) -> None:
        """Upsert a setting key-value pair into the database."""
        if not key:
            return
        self._ensure_connection()
        try:
            if self.is_mysql_active and self._mysql_conn:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO system_settings (`key`, `value`, `updated_at`)
                        VALUES (%s, %s, CURRENT_TIMESTAMP)
                        ON DUPLICATE KEY UPDATE `value` = VALUES(`value`), `updated_at` = CURRENT_TIMESTAMP
                        """,
                        (key, value),
                    )
            elif self._sqlite_conn:
                with self._sqlite_conn:
                    self._sqlite_conn.execute(
                        """
                        INSERT INTO system_settings (key, value, updated_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                        """,
                        (key, value),
                    )
        except Exception as e:
            logger.warning("Failed setting '%s' to '%s': %s", key, value, e)

    def get_all_settings(self) -> Dict[str, str]:
        """Retrieve all stored settings as a dictionary."""
        self._ensure_connection()
        res: Dict[str, str] = {}
        try:
            if self.is_mysql_active and self._mysql_conn:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute("SELECT `key`, `value` FROM system_settings")
                    for row in cursor.fetchall():
                        res[str(row[0])] = str(row[1])
            elif self._sqlite_conn:
                cursor = self._sqlite_conn.cursor()
                cursor.execute("SELECT key, value FROM system_settings")
                for row in cursor.fetchall():
                    res[str(row[0])] = str(row[1])
        except Exception as e:
            logger.warning("Error fetching all settings: %s", e)
        return res

    def delete_setting(self, key: str) -> bool:
        """Delete a setting by key."""
        if not key:
            return False
        self._ensure_connection()
        try:
            if self.is_mysql_active and self._mysql_conn:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute("DELETE FROM system_settings WHERE `key` = %s", (key,))
                    return cursor.rowcount > 0
            elif self._sqlite_conn:
                with self._sqlite_conn:
                    cursor = self._sqlite_conn.cursor()
                    cursor.execute("DELETE FROM system_settings WHERE key = ?", (key,))
                    return cursor.rowcount > 0
        except Exception as e:
            logger.warning("Error deleting setting '%s': %s", key, e)
        return False

    def get_status_description(self) -> str:
        """Return human-readable connection description for CLI banner."""
        count = self.get_processed_count()
        if self.is_mysql_active:
            return f"MySQL ({self.host}:{self.port}/{self.database} | {count} stored filings)"
        return f"SQLite ({self.db_path} | {count} stored filings)"

    def close(self) -> None:
        """Close database connection."""
        if self._mysql_conn:
            try:
                self._mysql_conn.close()
            except Exception:
                pass
            self._mysql_conn = None
            self.is_mysql_active = False

        if self._sqlite_conn:
            try:
                self._sqlite_conn.close()
            except Exception:
                pass
            self._sqlite_conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


__all__ = ["StrategyStorage"]
