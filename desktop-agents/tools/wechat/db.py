import sqlite3
from pathlib import Path
from typing import Iterable


class DatabaseOpenError(Exception):
    pass


def open_sqlite(path: str | Path, sqlcipher_key: str | None = None) -> sqlite3.Connection:
    db_path = Path(path)
    if not db_path.exists():
        raise DatabaseOpenError(f"数据库文件不存在：{db_path}")

    if sqlcipher_key:
        module = _load_sqlcipher_module()
        try:
            conn = module.connect(str(db_path))
            escaped_key = sqlcipher_key.replace("'", "''")
            conn.execute(f"PRAGMA key = '{escaped_key}'")
            _validate_connection(conn)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as exc:
            raise DatabaseOpenError(f"SQLCipher 数据库打开失败：{exc}") from exc

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        _validate_connection(conn)
        return conn
    except sqlite3.Error as exc:
        raise DatabaseOpenError(f"SQLite 数据库打开失败：{exc}") from exc


def detect_tables(conn) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({_quote_identifier(table)})").fetchall()
    return {row[1] for row in rows}


def iter_rows(conn, table: str, columns: Iterable[str]):
    selected = ", ".join(_quote_identifier(column) for column in columns)
    query = f"SELECT {selected} FROM {_quote_identifier(table)}"
    yield from conn.execute(query)


def _validate_connection(conn) -> None:
    conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()


def _load_sqlcipher_module():
    try:
        import sqlcipher3  # type: ignore
        return sqlcipher3
    except ImportError:
        pass

    try:
        from pysqlcipher3 import dbapi2 as pysqlcipher3  # type: ignore
        return pysqlcipher3
    except ImportError as exc:
        raise DatabaseOpenError(
            "需要打开加密数据库，但未安装 sqlcipher3/pysqlcipher3。"
            "请优先使用手动导出的已解密 SQLite 数据库，或安装可选 SQLCipher 绑定后再提供 --sqlcipher-key。"
        ) from exc


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
