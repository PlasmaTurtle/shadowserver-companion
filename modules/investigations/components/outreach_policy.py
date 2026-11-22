"""Explicit case outreach holds; review dates never reopen or send a case."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def migrate_outreach_policy(db):
    db.execute("""CREATE TABLE IF NOT EXISTS case_outreach_policy(
      case_id TEXT PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
      state TEXT NOT NULL CHECK(state IN ('active','deferred','do_not_contact')),
      reason TEXT NOT NULL, review_on TEXT, changed_by TEXT NOT NULL, changed_at TEXT NOT NULL)""")
    db.execute(
        "CREATE INDEX IF NOT EXISTS outreach_policy_review ON case_outreach_policy(review_on)"
    )


class OutreachPolicyValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    state: Literal["active", "deferred", "do_not_contact"]
    reason: str = Field(min_length=1, max_length=2000)
    review_on: date | None = None

    @model_validator(mode="after")
    def valid_decision(self):
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("Record the reason for this outreach decision")
        if self.state == "deferred" and self.review_on is None:
            raise ValueError("Deferred outreach needs a reconsideration date")
        return self


def get_policy(db, case_id):
    row = db.execute("SELECT * FROM case_outreach_policy WHERE case_id=?", (case_id,)).fetchone()
    return dict(row) if row else {"state": "active", "reason": "", "review_on": None}


def entity_hold(db, entity_id):
    """Latest explicit business decision, also used before costly qualification."""
    if not entity_id:
        return None
    row = db.execute(
        "SELECT p.* FROM case_outreach_policy p JOIN cases c ON c.id=p.case_id "
        "WHERE c.entity_id=? ORDER BY p.changed_at DESC,p.rowid DESC LIMIT 1",
        (entity_id,),
    ).fetchone()
    return dict(row) if row and row["state"] != "active" else None
