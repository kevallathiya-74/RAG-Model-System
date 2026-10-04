import os
import psycopg2
from psycopg2.extras import RealDictCursor

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
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password
        )
        return conn
    except Exception as e:
        raise RuntimeError(f"CRITICAL: Failed to connect to PostgreSQL database '{dbname}' on {host}:{port}. Error: {e}")
