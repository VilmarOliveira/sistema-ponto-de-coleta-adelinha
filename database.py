"""Conexão compatível com SQLite local e PostgreSQL/Neon."""
import sqlite3


def is_postgres(database):
    return str(database).startswith(("postgres://", "postgresql://"))


class DatabaseIntegrityError(Exception):
    pass


class DatabaseConnection:
    """Adapta parâmetros e linhas sem expor credenciais ou alterar o schema."""

    def __init__(self, database):
        self.postgres = is_postgres(database)
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row

            self.connection = psycopg.connect(database, row_factory=dict_row)
        else:
            self.connection = sqlite3.connect(database)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")

    def execute(self, sql, params=()):
        if self.postgres:
            import psycopg

            try:
                return self.connection.execute(sql.replace("?", "%s"), params)
            except psycopg.IntegrityError as error:
                raise DatabaseIntegrityError from error
        try:
            return self.connection.execute(sql, params)
        except sqlite3.IntegrityError as error:
            raise DatabaseIntegrityError from error

    def begin_write(self):
        self.execute("BEGIN" if self.postgres else "BEGIN IMMEDIATE")

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()
