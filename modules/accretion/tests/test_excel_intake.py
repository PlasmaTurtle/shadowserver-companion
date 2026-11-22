"""Source reader, structural validation and grouping contracts."""

import unittest
from contextlib import closing
from pathlib import Path
from modules.accretion.components.intake import (
    EntryValidator,
    ExcelReader,
    SourceObservation,
    CandidateGroup,
    root_domain,
)

FIXTURE = Path(__file__).resolve().parents[3] / "tests/fixtures" / "intake_fixture.xlsx"
REGION = {"North Carolina"}


def source(ip="8.8.8.8", hostname="example.com", row=2, **extra):
    fields = {
        "version": "7.3.25",
        "tag": "eol-php",
        "hostname": hostname,
        "ip": ip,
        "region": "North Carolina",
        "port": 443,
        "unknown_field": "keep",
        "optional": None,
    }
    fields.update(extra)
    return SourceObservation("original.xlsx", "Observations", row, fields)


def entries(*rows):
    return EntryValidator(REGION).validate(rows)


class ValidationTests(unittest.TestCase):
    def test_required_blanks_are_filtered_and_next_row_survives(self):
        for name in ("version", "tag", "hostname", "ip"):
            for blank in (None, ""):
                with self.subTest(field=name, value=blank):
                    good = source(row=3)
                    actual = entries(source(**{name: blank}), good)
                    self.assertEqual([e.source for e in actual], [good])

    def test_hostname_validity_and_jurisdiction_do_not_exclude_suffixes_or_numbers(self):
        rows = [
            source(hostname="1happy1horse1supply.com"),
            source(hostname="1xt3yrn7s.com"),
            source(hostname="example.org"),
            source(hostname="mail2.example.com"),
            source(region="Virginia"),
            source(ip="invalid"),
            source(hostname="mail.example.com"),
        ]
        self.assertEqual(len(entries(*rows)), 5)

    def test_unknown_fields_blanks_and_private_rows_are_preserved(self):
        for address in ("10.0.0.1", "172.16.1.1", "192.168.1.1", "fd00::1", "::ffff:192.168.1.1"):
            with self.subTest(ip=address):
                item = source(ip=address, new_column="new", blank_column=None)
                validated = entries(item)[0]
                self.assertTrue(validated.private_ip)
                self.assertEqual(validated.source, item)
                self.assertEqual(validated.source.fields["new_column"], "new")
                self.assertIn("blank_column", validated.source.fields)

    def test_unknown_condition_identifier_is_accepted(self):
        self.assertEqual(len(entries(source(tag="never-seen-this-tag"))), 1)


class GroupingTests(unittest.TestCase):
    def test_subdomains_group_under_root(self):
        grouped = CandidateGroup.group(
            entries(source(), source(hostname="mail.example.com"), source(hostname="sample.com"))
        )
        self.assertEqual([g.root_domain for g in grouped], ["example.com", "sample.com"])
        self.assertEqual(len(grouped[0].observations), 2)
        self.assertEqual(root_domain("mail.example.com"), "example.com")

    def test_distinct_private_suffix_tenants_do_not_merge(self):
        self.assertNotEqual(root_domain("alpha.blogspot.com"), root_domain("beta.blogspot.com"))


class WorkbookTests(unittest.TestCase):
    def test_real_xlsx_read_preserves_all_columns_and_provenance(self):
        with closing(ExcelReader().read(FIXTURE)) as stream:
            row = next(stream)
        self.assertEqual(len(row.fields), 12)
        self.assertEqual(row.fields["report_type"], "scan_http_vulnerable")
        self.assertEqual(row.fields["severity"], "critical")
        self.assertEqual(row.fields["future_column"], "preserve this")
        self.assertIsNone(row.fields["optional_column"])
        self.assertEqual(row.row, 2)
        self.assertEqual(row.sheet, "Observations")

    def test_schema_errors_are_explicit(self):
        for sheet in ("MissingHeaders", "DuplicateHeaders", "UnnamedHeader", "Absent"):
            with self.subTest(sheet=sheet), self.assertRaises(ValueError):
                list(ExcelReader().read(FIXTURE, sheet))
