"""Migra os dados do SQLite (flowdesk.db) para o Postgres do Supabase.

Conexão: define SUPABASE_DB_URL no back/.env (ou variável de ambiente). Ex.:
    SUPABASE_DB_URL=postgresql://postgres:SENHA@db.<ref>.supabase.co:5432/postgres?sslmode=require

Uso:  .venv\\Scripts\\python migrate_to_supabase.py
Idempotente: usa "on conflict do nothing"; preserva os IDs e reajusta as sequences.
"""
from __future__ import annotations

import os
import sqlite3

import psycopg

# ordem que respeita as foreign keys
ORDER = [
    "organizations", "users", "project_folders", "projects", "stages", "edges",
    "source_files", "builds", "executions", "roles", "project_members",
    "env_vars", "api_keys", "connectors", "data_tables", "data_rows",
    "chat_messages", "pending_actions",
]


def pg_connect() -> psycopg.Connection:
    url = os.environ.get("SUPABASE_DB_URL")
    if url:
        return psycopg.connect(url, autocommit=False, connect_timeout=20)
    # fallback por componentes (senha em SBPW)
    return psycopg.connect(
        host=os.environ.get("SB_HOST", "db.jfgspkievxsqlupreiuv.supabase.co"),
        port=5432, user="postgres", password=os.environ["SBPW"],
        dbname="postgres", sslmode="require", connect_timeout=20, autocommit=False,
    )


def column_types(cur, table: str) -> dict[str, str]:
    cur.execute(
        "select column_name, data_type from information_schema.columns "
        "where table_schema='public' and table_name=%s order by ordinal_position",
        (table,),
    )
    return {r[0]: r[1] for r in cur.fetchall()}


def main() -> int:
    sq = sqlite3.connect("flowdesk.db")
    sq.row_factory = sqlite3.Row
    pg = pg_connect()
    cur = pg.cursor()

    for table in ORDER:
        types = column_types(cur, table)
        try:
            rows = sq.execute(f"select * from {table}").fetchall()
        except sqlite3.OperationalError:
            print(f"{table}: ausente no SQLite, pulando")
            continue
        if not rows:
            print(f"{table}: 0 linhas")
            continue
        cols = [c for c in rows[0].keys() if c in types]
        placeholders = ", ".join(
            "%s::jsonb" if types[c] == "jsonb" else "%s" for c in cols
        )
        collist = ", ".join(f'"{c}"' for c in cols)
        sql = f'insert into {table} ({collist}) values ({placeholders}) on conflict do nothing'
        data = []
        for r in rows:
            vals = []
            for c in cols:
                v = r[c]
                if v is None:
                    vals.append(None)
                elif types[c] == "boolean":
                    vals.append(bool(v))
                else:
                    vals.append(v)  # jsonb recebe texto JSON do SQLite (cast ::jsonb)
            data.append(vals)
        cur.executemany(sql, data)
        print(f"{table}: {len(data)} linha(s)")
    pg.commit()

    # reajusta as sequences das PKs identity para o max(id)
    for table in ORDER:
        if table == "executions":  # PK varchar, sem sequence
            continue
        cur.execute(
            f"select setval(pg_get_serial_sequence('{table}','id'), "
            f"coalesce((select max(id) from {table}), 1), "
            f"(select count(*) > 0 from {table}))"
        )
    pg.commit()
    pg.close()
    sq.close()
    print("Migração concluída.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
