import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL")


class DBWrapper:
    def __init__(self):
        self.conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

    def execute(self, sql, params=()):
        sql = sql.replace("?", "%s").replace("datetime('now')", "NOW()")
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return cur

    def executescript(self, script):
        cur = self.conn.cursor()
        cur.execute(script)
        self.conn.commit()
        cur.close()

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def get_db():
    return DBWrapper()


def init_db(force=False):
    conn = get_db()
    with open(os.path.join(os.path.dirname(__file__), "schema.sql")) as f:
        conn.executescript(f.read())
    conn.close()
