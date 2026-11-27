"""Conexión a Oracle con python-oracledb (modo thin, sin Oracle Client)."""
import os
from contextlib import contextmanager

import oracledb

_pool = None


def get_pool():
    global _pool
    if _pool is None:
        _pool = oracledb.create_pool(
            user=os.environ["ORACLE_USER"],
            password=os.environ["ORACLE_PASSWORD"],
            dsn=os.environ.get("ORACLE_DSN", "localhost:1521/XEPDB1"),
            min=1,
            max=5,
            increment=1,
        )
    return _pool


def _filas(cur):
    columnas = [c[0].lower() for c in cur.description]
    return [dict(zip(columnas, fila)) for fila in cur.fetchall()]


def query(sql, params=None):
    """SELECT: devuelve una lista de diccionarios."""
    with get_pool().acquire() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            return _filas(cur)


def query_one(sql, params=None):
    filas = query(sql, params)
    return filas[0] if filas else None


def execute(sql, params=None):
    """INSERT/UPDATE/DELETE de una sola sentencia, con commit."""
    with get_pool().acquire() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            conn.commit()
            return cur.rowcount


@contextmanager
def transaction():
    """Varias sentencias en una sola transacción (commit o rollback)."""
    conn = get_pool().acquire()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_returning(cur, sql, params, columna_id):
    """INSERT que devuelve el id generado por la columna IDENTITY."""
    nuevo = cur.var(int)
    cur.execute(f"{sql} RETURNING {columna_id} INTO :nuevo_id", {**params, "nuevo_id": nuevo})
    return nuevo.getvalue()[0]
