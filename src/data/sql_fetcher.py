"""
src/data/sql_fetcher.py
────────────────────────
Runs the three SQL queries against the Buckman production DB.
Uses env vars: SQL_SERVER, SQL_DATABASE, SQL_USERNAME, SQL_PASSWORD
"""

import os
import re
from pathlib import Path

import pandas as pd
import pyodbc
from dotenv import load_dotenv

load_dotenv()


def _get_connection() -> pyodbc.Connection:
    server   = os.environ["SQL_SERVER"]
    database = os.environ["SQL_DATABASE"]
    username = os.environ["SQL_USERNAME"]
    password = os.environ["SQL_PASSWORD"]

    # Azure SQL — works with the ODBC Driver 18 installed on most Windows machines
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str)


def _load_sql(filename: str) -> str:
    path = Path(__file__).parents[2] / "sql" / filename
    return path.read_text(encoding="utf-8")


def _bind(sql: str, params: dict) -> tuple:
    """Replace :name placeholders → ? for pyodbc positional binding."""
    ordered_values = []
    def replacer(m):
        ordered_values.append(params[m.group(1)])
        return "?"
    sql_out = re.sub(r":([a-zA-Z_]+)", replacer, sql)
    return sql_out, tuple(ordered_values)


def fetch_site_controllers(site_name: str) -> pd.DataFrame:
    raw_sql = _load_sql("get_site_controllers.sql")
    sql, vals = _bind(raw_sql, {"site_name": site_name})
    with _get_connection() as conn:
        return pd.read_sql(sql, conn, params=vals)


def fetch_service_notes(site_name: str, start_date: str, end_date: str) -> pd.DataFrame:
    raw_sql = _load_sql("get_service_notes.sql")
    sql, vals = _bind(raw_sql, {
        "site_name": site_name, "start_date": start_date, "end_date": end_date,
    })
    with _get_connection() as conn:
        df = pd.read_sql(sql, conn, params=vals)
    df["ServiceNotePlain"] = df["ServiceNote"].apply(_strip_html)
    return df


def fetch_ade_data(site_name: str, start_date: str, end_date: str) -> pd.DataFrame:
    raw_sql = _load_sql("get_ade_data.sql")
    sql, vals = _bind(raw_sql, {
        "site_name": site_name, "start_date": start_date, "end_date": end_date,
    })
    with _get_connection() as conn:
        df = pd.read_sql(sql, conn, params=vals)
    if "CreatedDateTime" in df.columns:
        df["CreatedDateTime"] = pd.to_datetime(df["CreatedDateTime"], errors="coerce")
    return df


def _strip_html(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    for ent, rep in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">")]:
        text = text.replace(ent, rep)
    return re.sub(r"\s{2,}", " ", text).strip()
