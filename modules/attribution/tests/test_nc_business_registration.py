"""Check the published NC export's identity relationships using fictional records."""

from contextlib import closing
import sqlite3

import pytest

from modules.attribution.tools.create_nc_registry import create_database


def test_empty_mirror_keeps_registration_and_people_distinct(tmp_path):
    path = tmp_path / "registry.sqlite3"
    create_database(path)
    with closing(sqlite3.connect(path)) as db:
        tables = {
            name for (name,) in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        }
        assert tables == {
            "Names",
            "NameTypes",
            "Addresses",
            "AddressTypes",
            "Corporations",
            "CorpStatus",
            "Filings",
            "PendingFilings",
            "Stock",
            "NameReservations",
            "Officers",
            "Partners",
            "Directors",
            "CorpOfficers",
            "EntityTypes",
            "DocTypes",
            "CitizenshipTypes",
            "CorpTypes",
        }
        assert not db.execute("SELECT 1 FROM Corporations").fetchall()
        db.executemany(
            """INSERT INTO Corporations
               (PItemId,EntityID,CorpType,CorpNum,Status,Citzenship,OfficeAddressID,
                OfficeMailingID,AgentEntityID) VALUES (?,?,?,?,?,?,?,?,?)""",
            [
                (21, 10, "TEST", "00012", 1, "D", 7, 8, 11),
                (22, 12, "TEST", "00012", 1, "D", None, None, None),
            ],
        )
        db.executemany(
            "INSERT INTO Names (ENameID,EntityID,EName,NTypeID) VALUES (?,?,?,?)",
            [
                (101, 10, "Fixture Corp", 1),
                (102, 10, "Former name", 3),
                (103, 11, "Fixture Agent", 1),
                (104, 12, "Second Corp", 1),
            ],
        )
        db.executemany(
            "INSERT INTO Addresses (AddressID,EntityID,Addr1) VALUES (?,?,?)",
            [(7, 10, "Example Office"), (8, 10, "Example Mail"), (9, 11, "Example Agent Office")],
        )
        db.execute(
            "INSERT INTO CorpOfficers (PitemId,Title,Ename) VALUES (21,'President','Fixture Officer')"
        )
        details = db.execute(
            """SELECT c.CorpNum, n.EName, site.Addr1, mail.Addr1, agent.EName, officer.Ename
               FROM Corporations c
               JOIN Names n ON n.EntityID=c.EntityID AND n.NTypeID=1
               JOIN Addresses site ON site.AddressID=c.OfficeAddressID
               JOIN Addresses mail ON mail.AddressID=c.OfficeMailingID
               JOIN Names agent ON agent.EntityID=c.AgentEntityID AND agent.NTypeID=1
               JOIN CorpOfficers officer USING (PItemId)
               WHERE c.PItemId=21"""
        ).fetchall()
        assert details == [
            (
                "00012",
                "Fixture Corp",
                "Example Office",
                "Example Mail",
                "Fixture Agent",
                "Fixture Officer",
            )
        ]
        assert db.execute("SELECT count(*) FROM Corporations WHERE CorpNum='00012'").fetchone() == (
            2,
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO Corporations SELECT * FROM Corporations WHERE PItemId=21")


def test_existing_database_is_preserved(tmp_path):
    path = tmp_path / "existing.sqlite3"
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE original (id INTEGER)")
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        create_database(path)
    assert path.read_bytes() == before
