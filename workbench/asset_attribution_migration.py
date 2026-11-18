"""Supplemental asset lookup history, separate from certified case attribution."""


def migrate_asset_attributions(db):
    db.execute("""CREATE TABLE IF NOT EXISTS case_asset_attributions (
      id TEXT PRIMARY KEY,
      case_id TEXT NOT NULL REFERENCES cases(id),
      entry_id TEXT NOT NULL REFERENCES entries(id),
      result_id TEXT NOT NULL UNIQUE,
      root_domain TEXT NOT NULL,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL)""")
    db.execute("""CREATE INDEX IF NOT EXISTS asset_attribution_case
      ON case_asset_attributions(case_id,entry_id,created_at)""")
    for operation in ("UPDATE", "DELETE"):
        db.execute(f"""CREATE TRIGGER IF NOT EXISTS immutable_asset_attributions_{operation.lower()}
          BEFORE {operation} ON case_asset_attributions BEGIN
          SELECT RAISE(ABORT, 'Asset attribution history is immutable'); END""")
