# db/queries.py
"""
Conexão com o banco SQLite, usando o padrão recomendado pelo Flask:
uma conexão por request, guardada em flask.g, fechada automaticamente
no final do request (via app.teardown_appcontext).
"""

import sqlite3
import os
from flask import g

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row  # permite acessar colunas por nome: row["nome"]
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()
