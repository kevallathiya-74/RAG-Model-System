import os
import sys
import types

# Driver resolution: prefer native psycopg2, gracefully fall back to pure-Python pg8000 if blocked by OS policy (e.g. Smart App Control)
_DRIVER = "psycopg2"
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:
    _DRIVER = "pg8000"
    import pg8000.dbapi as pg8000_api

    class RealDictCursor:
        pass

    # Register shim in sys.modules so any downstream 'import psycopg2' succeeds
    shim = types.ModuleType("psycopg2")
    shim.connect = pg8000_api.connect
    extras_mod = types.ModuleType("psycopg2.extras")
    extras_mod.RealDictCursor = RealDictCursor
    shim.extras = extras_mod

    sql_mod = types.ModuleType("psycopg2.sql")
    class Composable:
        def __init__(self, wrapped):
            self._wrapped = wrapped
        def as_string(self, context=None):
            return str(self._wrapped)
        def __str__(self):
            return str(self._wrapped)
    class SQL(Composable):
        def format(self, *args, **kwargs):
            return SQL(str(self._wrapped).format(*args, **kwargs))
        def join(self, seq):
            return SQL(str(self._wrapped).join(str(s) for s in seq))
    class Identifier(Composable):
        def as_string(self, context=None):
            return f'"{self._wrapped}"'
        def __str__(self):
            return f'"{self._wrapped}"'
    class Literal(Composable):
        def as_string(self, context=None):
            return repr(self._wrapped)
        def __str__(self):
            return repr(self._wrapped)
    sql_mod.Composable = Composable
    sql_mod.SQL = SQL
    sql_mod.Identifier = Identifier
    sql_mod.Literal = Literal
    shim.sql = sql_mod

    sys.modules["psycopg2"] = shim
    sys.modules["psycopg2.extras"] = extras_mod
    sys.modules["psycopg2.sql"] = sql_mod

    class Pg8000CursorWrapper:
        def __init__(self, raw_cursor, as_dict=False):
            self._cur = raw_cursor
            self._as_dict = as_dict

        def execute(self, operation, args=None):
            op_str = str(operation) if hasattr(operation, "as_string") or hasattr(operation, "_wrapped") else operation
            if args is None:
                return self._cur.execute(op_str)
            return self._cur.execute(op_str, args)

        def fetchone(self):
            row = self._cur.fetchone()
            if row is None:
                return None
            if self._as_dict:
                cols = [d[0] for d in self._cur.description]
                return dict(zip(cols, row))
            return row

        def fetchall(self):
            rows = self._cur.fetchall()
            if not rows:
                return []
            if self._as_dict:
                cols = [d[0] for d in self._cur.description]
                return [dict(zip(cols, r)) for r in rows]
            return rows

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self._cur.close()

        @property
        def rowcount(self):
            return self._cur.rowcount

        @property
        def description(self):
            return self._cur.description

        def __getattr__(self, name):
            return getattr(self._cur, name)

    class Pg8000ConnectionWrapper:
        def __init__(self, raw_conn):
            self._conn = raw_conn

        def cursor(self, cursor_factory=None):
            as_dict = cursor_factory is not None
            return Pg8000CursorWrapper(self._conn.cursor(), as_dict=as_dict)

        def commit(self):
            return self._conn.commit()

        def rollback(self):
            return self._conn.rollback()

        def close(self):
            return self._conn.close()

        @property
        def autocommit(self):
            return getattr(self._conn, "autocommit", False)

        @autocommit.setter
        def autocommit(self, val):
            self._conn.autocommit = val

        def __getattr__(self, name):
            return getattr(self._conn, name)

def load_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

def get_db_connection():
    load_env()
    host = os.environ.get("POSTGRES_HOST")
    port = os.environ.get("POSTGRES_PORT")
    dbname = os.environ.get("POSTGRES_DB")
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    
    if not all([host, port, dbname, user, password]):
        raise ValueError("Missing PostgreSQL connection variables in environment or .env file.")
    
    try:
        if _DRIVER == "psycopg2":
            conn = psycopg2.connect(
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=password
            )
            return conn
        else:
            raw = pg8000_api.connect(
                host=host,
                port=int(port),
                database=dbname,
                user=user,
                password=password
            )
            return Pg8000ConnectionWrapper(raw)
    except Exception as e:
        raise RuntimeError(f"CRITICAL: Failed to connect to PostgreSQL database '{dbname}' on {host}:{port}. Error: {e}")
