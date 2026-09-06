"""Persistent storage for filing deduplication, audit logs, and trade executions.

Supports remote MySQL (MariaDB) with transparent local SQLite fallback.
"""

from datetime import datetime, timedelta
from functools import wraps
import hashlib
import logging
import os
from pathlib import Path
import secrets
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Set, Tuple
from news_based_strategy.config import settings
from news_based_strategy.core.models import FilingAudit, TradeResult
from news_based_strategy.execution.risk import get_ist_now

logger = logging.getLogger(__name__)


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Hash password using PBKDF2-HMAC-SHA256 with random salt."""
    if not salt:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return key.hex(), salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Verify password against stored salt and expected hash using constant-time comparison."""
    computed_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(computed_hash, expected_hash)


def _thread_safe(method):
    """Decorator ensuring single-threaded atomic access to database connection."""
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


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
        self._lock = threading.RLock()
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
        self.seed_default_user()
        self.seed_authorized_clients()

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
                read_timeout=15,
                write_timeout=15,
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
        if self.is_mysql_active:
            if not self._mysql_conn:
                if not self._init_mysql():
                    logger.warning("MySQL reconnect failed. Falling back to SQLite.")
                    self.is_mysql_active = False
                    if not self._sqlite_conn:
                        self._init_sqlite()
                        self._init_tables()
            else:
                try:
                    self._mysql_conn.ping(reconnect=True)
                except Exception as e:
                    logger.warning("MySQL connection ping failed (%s). Reconnecting...", e)
                    try:
                        if self._mysql_conn:
                            try:
                                self._mysql_conn.close()
                            except Exception:
                                pass
                        self._mysql_conn = None
                        if not self._init_mysql():
                            logger.warning("MySQL reconnect failed. Falling back to SQLite.")
                            self.is_mysql_active = False
                            if not self._sqlite_conn:
                                self._init_sqlite()
                                self._init_tables()
                    except Exception as re_err:
                        logger.warning("MySQL reconnect exception: %s. Falling back to SQLite.", re_err)
                        self.is_mysql_active = False
                        self._mysql_conn = None
                        if not self._sqlite_conn:
                            self._init_sqlite()
                            self._init_tables()

    def _init_tables(self) -> None:
        """Create necessary tables if they do not exist."""
        if self.is_mysql_active and self._mysql_conn:
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
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS users (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            username VARCHAR(64) UNIQUE NOT NULL,
                            password_hash VARCHAR(256) NOT NULL,
                            salt VARCHAR(64) NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """
                    )
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS user_sessions (
                            session_token VARCHAR(128) PRIMARY KEY,
                            username VARCHAR(64) NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            expires_at TIMESTAMP NOT NULL,
                            INDEX idx_username (username),
                            INDEX idx_expires_at (expires_at)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """
                    )
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS `Authorized user` (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            client_id VARCHAR(64) UNIQUE NOT NULL,
                            name VARCHAR(128),
                            is_active TINYINT NOT NULL DEFAULT 1,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            INDEX idx_client_id (client_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """
                    )
                return
            except Exception as e:
                logger.warning("Failed creating MySQL tables: %s. Reverting to SQLite.", e)
                self.is_mysql_active = False
                self._mysql_conn = None
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
                self._sqlite_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        salt TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                self._sqlite_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        session_token TEXT PRIMARY KEY,
                        username TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TEXT NOT NULL
                    )
                    """
                )
                self._sqlite_conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS `Authorized user` (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        client_id TEXT UNIQUE NOT NULL,
                        name TEXT,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

    @_thread_safe
    def is_processed(self, seq_id: str) -> bool:
        """Check if an announcement has already been processed."""
        if not seq_id:
            return False
        self._ensure_connection()
        if self.is_mysql_active and self._mysql_conn:
            try:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM processed_filings WHERE seq_id = %s", (seq_id,))
                    return cursor.fetchone() is not None
            except Exception as e:
                logger.warning("Error checking is_processed in MySQL: %s", e)
                self._mysql_conn = None
        if self._sqlite_conn:
            try:
                cursor = self._sqlite_conn.cursor()
                cursor.execute("SELECT 1 FROM processed_filings WHERE seq_id = ?", (seq_id,))
                return cursor.fetchone() is not None
            except Exception as e:
                logger.warning("Error checking is_processed in SQLite: %s", e)
        return False

    @_thread_safe
    def mark_processed(self, seq_id: str, symbol: str, an_dt: str = "") -> None:
        """Record an announcement as processed."""
        if not seq_id:
            return
        self._ensure_connection()
        if self.is_mysql_active and self._mysql_conn:
            try:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT IGNORE INTO processed_filings (seq_id, symbol, an_dt) VALUES (%s, %s, %s)",
                        (seq_id, symbol, an_dt),
                    )
                return
            except Exception as e:
                logger.warning("Failed to mark_processed in MySQL: %s", e)
                self._mysql_conn = None
        if self._sqlite_conn:
            try:
                with self._sqlite_conn:
                    self._sqlite_conn.execute(
                        "INSERT OR IGNORE INTO processed_filings (seq_id, symbol, an_dt) VALUES (?, ?, ?)",
                        (seq_id, symbol, an_dt),
                    )
            except Exception as e:
                logger.warning("Failed to mark_processed in SQLite: %s", e)

    @_thread_safe
    def get_processed_seq_ids(self, limit: int = 2000) -> Set[str]:
        """Preload recently processed sequence IDs into a Python set."""
        self._ensure_connection()
        try:
            if self.is_mysql_active and self._mysql_conn:
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
            if self.is_mysql_active:
                self._mysql_conn = None
        return set()

    @_thread_safe
    def save_audit(self, seq_id: str, symbol: str, audit: FilingAudit) -> None:
        """Save an AI filing audit."""
        self._ensure_connection()
        if self.is_mysql_active and self._mysql_conn:
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
                return
            except Exception as e:
                logger.warning("Failed to save audit in MySQL: %s", e)
                self._mysql_conn = None
        if self._sqlite_conn:
            try:
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
            except Exception as e:
                logger.warning("Failed to save audit in SQLite: %s", e)

    @_thread_safe
    def get_recent_audits(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent AI audits from the database."""
        self._ensure_connection()
        results: List[Dict[str, Any]] = []
        try:
            if self.is_mysql_active and self._mysql_conn:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT seq_id, symbol, sentiment, confidence, catalyst_type, material_impact, summary, created_at
                        FROM audit_logs
                        ORDER BY id DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                    for row in cursor.fetchall():
                        results.append({
                            "seq_id": str(row[0]),
                            "symbol": str(row[1]),
                            "sentiment": str(row[2]),
                            "confidence": int(row[3]),
                            "catalyst_type": str(row[4]),
                            "material_impact": bool(row[5]),
                            "summary": str(row[6]),
                            "created_at": str(row[7]),
                        })
                    return results
            elif self._sqlite_conn:
                cursor = self._sqlite_conn.cursor()
                cursor.execute(
                    """
                    SELECT seq_id, symbol, sentiment, confidence, catalyst_type, material_impact, summary, created_at
                    FROM audit_logs
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                for row in cursor.fetchall():
                    results.append({
                        "seq_id": str(row[0]),
                        "symbol": str(row[1]),
                        "sentiment": str(row[2]),
                        "confidence": int(row[3]),
                        "catalyst_type": str(row[4]),
                        "material_impact": bool(row[5]),
                        "summary": str(row[6]),
                        "created_at": str(row[7]),
                    })
                return results
        except Exception as e:
            logger.warning("Error fetching recent audits: %s", e)
            if self.is_mysql_active:
                self._mysql_conn = None
        return results

    @_thread_safe
    def save_trade(self, result: TradeResult) -> None:
        """Log a trade execution attempt."""
        self._ensure_connection()
        if self.is_mysql_active and self._mysql_conn:
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
                return
            except Exception as e:
                logger.warning("Failed to save trade in MySQL: %s", e)
                self._mysql_conn = None
        if self._sqlite_conn:
            try:
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
            except Exception as e:
                logger.warning("Failed to save trade in SQLite: %s", e)

    @_thread_safe
    def get_processed_count(self) -> int:
        """Return the total number of processed filings."""
        self._ensure_connection()
        if self.is_mysql_active and self._mysql_conn:
            try:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM processed_filings")
                    row = cursor.fetchone()
                    return int(row[0]) if row else 0
            except Exception as e:
                logger.warning("Failed querying processed count in MySQL: %s", e)
                self._mysql_conn = None
        if self._sqlite_conn:
            try:
                cursor = self._sqlite_conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM processed_filings")
                row = cursor.fetchone()
                return int(row[0]) if row else 0
            except Exception as e:
                logger.warning("Failed querying processed count in SQLite: %s", e)
        return 0

    @_thread_safe
    def get_today_order_count(self) -> int:
        """Return the number of successfully placed orders today in IST."""
        self._ensure_connection()
        today_prefix = get_ist_now().strftime("%Y-%m-%d")
        if self.is_mysql_active and self._mysql_conn:
            try:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM trade_executions WHERE DATE(timestamp) = %s AND order_id IS NOT NULL",
                        (today_prefix,),
                    )
                    row = cursor.fetchone()
                    return int(row[0]) if row else 0
            except Exception as e:
                logger.warning("Failed querying today order count in MySQL: %s", e)
                self._mysql_conn = None
        if self._sqlite_conn:
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

    @_thread_safe
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
            if self.is_mysql_active:
                self._mysql_conn = None
        return default

    @_thread_safe
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
            if self.is_mysql_active:
                self._mysql_conn = None

    @_thread_safe
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
            if self.is_mysql_active:
                self._mysql_conn = None
        return res

    @_thread_safe
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
            if self.is_mysql_active:
                self._mysql_conn = None
        return False
    # -------------------------------------------------------------------------
    # User Authentication & Session Management
    # -------------------------------------------------------------------------

    @_thread_safe
    def get_user(self, username: str) -> Optional[dict]:
        """Fetch user record by username."""
        if not username:
            return None
        self._ensure_connection()
        try:
            if self.is_mysql_active and self._mysql_conn:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT id, username, password_hash, salt, created_at FROM users WHERE username = %s",
                        (username.strip(),),
                    )
                    row = cursor.fetchone()
                    if row:
                        return {
                            "id": row[0],
                            "username": str(row[1]),
                            "password_hash": str(row[2]),
                            "salt": str(row[3]),
                            "created_at": str(row[4]),
                        }
            elif self._sqlite_conn:
                cursor = self._sqlite_conn.cursor()
                cursor.execute(
                    "SELECT id, username, password_hash, salt, created_at FROM users WHERE username = ?",
                    (username.strip(),),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "username": str(row[1]),
                        "password_hash": str(row[2]),
                        "salt": str(row[3]),
                        "created_at": str(row[4]),
                    }
        except Exception as e:
            logger.warning("Error fetching user '%s': %s", username, e)
            if self.is_mysql_active:
                self._mysql_conn = None
        return None

    @_thread_safe
    def create_user(self, username: str, password_hash: str, salt: str) -> bool:
        """Insert or update a user record."""
        if not username or not password_hash or not salt:
            return False
        self._ensure_connection()
        try:
            if self.is_mysql_active and self._mysql_conn:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO users (username, password_hash, salt)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash), salt = VALUES(salt)
                        """,
                        (username.strip(), password_hash, salt),
                    )
                    return True
            elif self._sqlite_conn:
                with self._sqlite_conn:
                    self._sqlite_conn.execute(
                        """
                        INSERT INTO users (username, password_hash, salt)
                        VALUES (?, ?, ?)
                        ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash, salt = excluded.salt
                        """,
                        (username.strip(), password_hash, salt),
                    )
                    return True
        except Exception as e:
            logger.warning("Error creating user '%s': %s", username, e)
            if self.is_mysql_active:
                self._mysql_conn = None
        return False

    @_thread_safe
    def seed_default_user(self, username: str = "amit", password: str = "Kls@1982") -> None:
        """Seed default user if not already present in the database."""
        try:
            existing = self.get_user(username)
            if not existing:
                pwd_hash, salt = hash_password(password)
                self.create_user(username, pwd_hash, salt)
                logger.info("Seeded default application user '%s' in database.", username)
        except Exception as e:
            logger.warning("Could not seed default user '%s': %s", username, e)

    @_thread_safe
    def verify_user_credentials(self, username: str, plain_password: str) -> bool:
        """Verify plain password against stored user hash."""
        if not username or not plain_password:
            return False
        user = self.get_user(username)
        if not user:
            return False
        return verify_password(plain_password, user["salt"], user["password_hash"])

    @_thread_safe
    def create_session(self, username: str, max_age_days: int = 7) -> str:
        """Create a new user session token in the database."""
        if not username:
            return ""
        self._ensure_connection()
        session_token = secrets.token_urlsafe(48)
        expires_at = (get_ist_now() + timedelta(days=max_age_days)).strftime("%Y-%m-%d %H:%M:%S")
        try:
            if self.is_mysql_active and self._mysql_conn:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO user_sessions (session_token, username, expires_at) VALUES (%s, %s, %s)",
                        (session_token, username.strip(), expires_at),
                    )
            elif self._sqlite_conn:
                with self._sqlite_conn:
                    self._sqlite_conn.execute(
                        "INSERT INTO user_sessions (session_token, username, expires_at) VALUES (?, ?, ?)",
                        (session_token, username.strip(), expires_at),
                    )
            return session_token
        except Exception as e:
            logger.warning("Error creating session for user '%s': %s", username, e)
            if self.is_mysql_active:
                self._mysql_conn = None
            return ""

    @_thread_safe
    def validate_session(self, session_token: str) -> Optional[str]:
        """Validate session token and return username if active and not expired."""
        if not session_token:
            return None
        self._ensure_connection()
        now_str = get_ist_now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            if self.is_mysql_active and self._mysql_conn:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT username FROM user_sessions WHERE session_token = %s AND expires_at > %s",
                        (session_token.strip(), now_str),
                    )
                    row = cursor.fetchone()
                    return str(row[0]) if row else None
            elif self._sqlite_conn:
                cursor = self._sqlite_conn.cursor()
                cursor.execute(
                    "SELECT username FROM user_sessions WHERE session_token = ? AND expires_at > ?",
                    (session_token.strip(), now_str),
                )
                row = cursor.fetchone()
                return str(row[0]) if row else None
        except Exception as e:
            logger.warning("Error validating session: %s", e)
            if self.is_mysql_active:
                self._mysql_conn = None
        return None

    @_thread_safe
    def delete_session(self, session_token: str) -> bool:
        """Delete session token on logout."""
        if not session_token:
            return False
        self._ensure_connection()
        try:
            if self.is_mysql_active and self._mysql_conn:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute("DELETE FROM user_sessions WHERE session_token = %s", (session_token.strip(),))
                    return cursor.rowcount > 0
            elif self._sqlite_conn:
                with self._sqlite_conn:
                    cursor = self._sqlite_conn.cursor()
                    cursor.execute("DELETE FROM user_sessions WHERE session_token = ?", (session_token.strip(),))
                    return cursor.rowcount > 0
        except Exception as e:
            logger.warning("Error deleting session: %s", session_token, e)
            if self.is_mysql_active:
                self._mysql_conn = None
        return False

    @_thread_safe
    def seed_authorized_clients(self, default_client_id: str = "1104872040") -> None:
        """Seed default authorized client ID into `Authorized user` table if not present."""
        try:
            ids_to_seed = [default_client_id]
            if settings.dhan_client_id and settings.dhan_client_id not in ids_to_seed:
                ids_to_seed.append(settings.dhan_client_id)
            for cid in ids_to_seed:
                if cid and not self.is_client_authorized(cid):
                    self.add_authorized_client(cid, name="Primary Authorized Account", is_active=1)
                    logger.info("Seeded authorized client '%s' in `Authorized user` table.", cid)
        except Exception as e:
            logger.warning("Could not seed authorized client: %s", e)

    @_thread_safe
    def is_client_authorized(self, client_id: str) -> bool:
        """Check if a Dhan client ID is present and active in `Authorized user` table."""
        if not client_id:
            return False
        self._ensure_connection()
        cid = str(client_id).strip()
        try:
            if self.is_mysql_active and self._mysql_conn:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT 1 FROM `Authorized user` WHERE client_id = %s AND is_active = 1",
                        (cid,),
                    )
                    return cursor.fetchone() is not None
            elif self._sqlite_conn:
                cursor = self._sqlite_conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM `Authorized user` WHERE client_id = ? AND is_active = 1",
                    (cid,),
                )
                return cursor.fetchone() is not None
        except Exception as e:
            logger.warning("Error checking is_client_authorized for '%s': %s", cid, e)
            if self.is_mysql_active:
                self._mysql_conn = None
        return False

    @_thread_safe
    def add_authorized_client(self, client_id: str, name: str = "", is_active: int = 1) -> bool:
        """Add or update an authorized client ID in `Authorized user` table."""
        if not client_id:
            return False
        self._ensure_connection()
        cid = str(client_id).strip()
        try:
            if self.is_mysql_active and self._mysql_conn:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO `Authorized user` (client_id, name, is_active)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE name = VALUES(name), is_active = VALUES(is_active)
                        """,
                        (cid, name.strip(), int(is_active)),
                    )
                    return True
            elif self._sqlite_conn:
                with self._sqlite_conn:
                    self._sqlite_conn.execute(
                        """
                        INSERT INTO `Authorized user` (client_id, name, is_active)
                        VALUES (?, ?, ?)
                        ON CONFLICT(client_id) DO UPDATE SET name = excluded.name, is_active = excluded.is_active
                        """,
                        (cid, name.strip(), int(is_active)),
                    )
                    return True
        except Exception as e:
            logger.warning("Error adding authorized client '%s': %s", cid, e)
            if self.is_mysql_active:
                self._mysql_conn = None
        return False

    @_thread_safe
    def get_authorized_clients(self) -> List[Dict[str, Any]]:
        """Return all authorized client records from `Authorized user` table."""
        self._ensure_connection()
        try:
            if self.is_mysql_active and self._mysql_conn:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute("SELECT id, client_id, name, is_active, created_at FROM `Authorized user` ORDER BY id ASC")
                    rows = cursor.fetchall()
                    return [
                        {
                            "id": r[0],
                            "client_id": str(r[1]),
                            "name": r[2] or "",
                            "is_active": bool(r[3]),
                            "created_at": str(r[4]),
                        }
                        for r in rows
                    ]
            elif self._sqlite_conn:
                cursor = self._sqlite_conn.cursor()
                cursor.execute("SELECT id, client_id, name, is_active, created_at FROM `Authorized user` ORDER BY id ASC")
                rows = cursor.fetchall()
                return [
                    {
                        "id": r[0],
                        "client_id": str(r[1]),
                        "name": r[2] or "",
                        "is_active": bool(r[3]),
                        "created_at": str(r[4]),
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.warning("Error fetching authorized clients: %s", e)
            if self.is_mysql_active:
                self._mysql_conn = None
        return []

    @_thread_safe
    def remove_authorized_client(self, client_id: str) -> bool:
        """Remove or deactivate an authorized client ID from `Authorized user` table."""
        if not client_id:
            return False
        self._ensure_connection()
        cid = str(client_id).strip()
        try:
            if self.is_mysql_active and self._mysql_conn:
                with self._mysql_conn.cursor() as cursor:
                    cursor.execute("DELETE FROM `Authorized user` WHERE client_id = %s", (cid,))
                    return cursor.rowcount > 0
            elif self._sqlite_conn:
                with self._sqlite_conn:
                    cursor = self._sqlite_conn.cursor()
                    cursor.execute("DELETE FROM `Authorized user` WHERE client_id = ?", (cid,))
                    return cursor.rowcount > 0
        except Exception as e:
            logger.warning("Error removing authorized client '%s': %s", cid, e)
            if self.is_mysql_active:
                self._mysql_conn = None
        return False

    @_thread_safe
    def get_status_description(self) -> str:
        """Return human-readable connection description for CLI banner."""
        count = self.get_processed_count()
        if self.is_mysql_active:
            return f"MySQL ({self.host}:{self.port}/{self.database} | {count} stored filings)"
        return f"SQLite ({self.db_path} | {count} stored filings)"

    @_thread_safe
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


__all__ = ["StrategyStorage", "hash_password", "verify_password"]
