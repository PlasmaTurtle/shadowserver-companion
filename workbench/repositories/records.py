"""Dictionary reads over a caller-owned SQLite connection; never commits."""


class Records:
    def __init__(self, db):
        self.db = db

    def all(self, sql, args=()):
        return [dict(row) for row in self.db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        row = self.db.execute(sql, args).fetchone()
        return dict(row) if row is not None else None
