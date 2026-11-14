"""Offline regression tests. Registry requests are mocked in every test."""

import hashlib
import json
import shutil
import tempfile
import unittest
from contextlib import closing, redirect_stderr
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from excel_intake import (
    EntryValidator,
    ExcelReader,
    LeadRuntime,
    QualifiedLeads,
    RdapWhoisClient,
    UnvalidatedEntry,
    ValidatedLeads,
    WhoisLookupError,
    WhoisRecord,
    discover_workbooks,
    main,
    root_domain,
)

FIXTURE = Path(__file__).parent / "fixtures" / "intake_fixture.xlsx"
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
    return UnvalidatedEntry("original.xlsx", "Observations", row, fields)


def entries(*rows):
    return EntryValidator(REGION).validate(rows)


def record(ip="8.8.8.8", domain="example.com"):
    return WhoisRecord(
        ip,
        "ARIN",
        f"https://rdap.arin.net/registry/ip/{ip}",
        "2026-11-05T00:00:00Z",
        {
            "objectClassName": "ip network",
            "startAddress": ip,
            "endAddress": ip,
            "entities": [{"vcardArray": ["vcard", [["email", {}, "text", f"abuse@{domain}"]]]}],
        },
    )


def response(status=200, data=None, **headers):
    result = requests.Response()
    result.status_code = status
    result.headers.update(headers)
    result._content = json.dumps(data).encode()
    result._content_consumed = True
    return result


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


class QualificationTests(unittest.TestCase):
    def test_subdomains_group_under_root(self):
        grouped = ValidatedLeads.group(
            entries(source(), source(hostname="mail.example.com"), source(hostname="sample.com"))
        )
        self.assertEqual([g.hostname for g in grouped], ["example.com", "sample.com"])
        self.assertEqual(len(grouped[0].entries), 2)
        self.assertEqual(root_domain("mail.example.com"), "example.com")

    def test_distinct_private_suffix_tenants_do_not_merge(self):
        self.assertNotEqual(root_domain("alpha.blogspot.com"), root_domain("beta.blogspot.com"))

    def test_one_match_keeps_seventy_rows_and_stops(self):
        original = entries(*(source(ip=f"8.8.4.{i}", row=i + 1) for i in range(1, 71)))
        group = ValidatedLeads.group(original)[0]
        lookup = Mock(
            side_effect=[
                record("8.8.4.1", "other.com"),
                record("8.8.4.2", "other.com"),
                record("8.8.4.3", "example.com"),
            ]
        )
        qualified = group.qualify(lookup)
        self.assertEqual(lookup.call_count, 3)
        self.assertEqual(len(qualified.validated_leads[0].entries), 70)
        self.assertIs(group.entries[0], original[2])
        self.assertEqual(group.entries[1:], original[:2] + original[3:])
        self.assertEqual(qualified.whois[0].ip, group.entries[0].ip)

    def test_duplicate_ip_queried_once_private_kept_and_skipped(self):
        group = ValidatedLeads.group(
            entries(
                source(ip="192.168.1.5"),
                source(),
                source(tag="second-observation"),
                source(ip="9.9.9.9"),
            )
        )[0]
        lookup = Mock(side_effect=[record(domain="other.com"), record("9.9.9.9")])
        qualified = group.qualify(lookup)
        self.assertEqual([call.args[0] for call in lookup.call_args_list], ["8.8.8.8", "9.9.9.9"])
        self.assertEqual(len(qualified.validated_leads[0].entries), 4)
        self.assertTrue(group.entries[1].private_ip)

    def test_failure_does_not_prevent_later_matching_ip(self):
        group = ValidatedLeads.group(entries(source(), source(ip="9.9.9.9")))[0]
        lookup = Mock(side_effect=[WhoisLookupError("timeout"), record("9.9.9.9")])
        self.assertIsNotNone(group.qualify(lookup))
        self.assertEqual(group.attempts[0]["status"], "lookup_error")

    def test_private_only_group_is_retained_but_not_qualified(self):
        group = ValidatedLeads.group(entries(source(ip="10.0.0.5")))[0]
        lookup = Mock()
        self.assertIsNone(group.qualify(lookup))
        lookup.assert_not_called()
        self.assertEqual(len(group.entries), 1)

    def test_domain_match_boundaries(self):
        for value, expected in [
            ("abuse@EXAMPLE.COM", True),
            ("https://mail.example.com/help", True),
            ("Our website is example.com.", True),
            ("notexample.com", False),
            ("example.com.attacker.net", False),
            ("other-example.com", False),
            ("example.com-backup", False),
        ]:
            with self.subTest(value=value):
                result = WhoisRecord(
                    "8.8.8.8",
                    "ARIN",
                    "https://rdap.arin.net/",
                    "2026-11-05T00:00:00Z",
                    {"text": value},
                )
                self.assertEqual(result.find_domain("example.com") is not None, expected)

    def test_json_parent_hierarchy_provenance_and_datetime(self):
        group = ValidatedLeads.group(entries(source(timestamp=datetime(2026, 11, 4))))[0]
        lead = group.qualify(lambda ip: record(ip))
        data = json.loads(QualifiedLeads.to_json([lead]))
        item = data[0]["validated_leads"][0]["entries"][0]
        self.assertEqual(item["source"]["fields"]["timestamp"], "2026-11-04T00:00:00")
        self.assertEqual(item["source"]["fields"]["unknown_field"], "keep")
        self.assertEqual(item["source"]["row"], 2)
        self.assertEqual(data[0]["whois"][0]["attribution"]["value"], "abuse@example.com")
        self.assertIn("entities", data[0]["whois"][0]["record"])

    def test_serializer_rejects_reordering_that_breaks_attribution(self):
        group = ValidatedLeads.group(entries(source(), source(ip="9.9.9.9")))[0]
        lead = group.qualify(lambda ip: record(ip))
        group.entries.reverse()
        with self.assertRaises(ValueError):
            QualifiedLeads.to_json([lead])


class RegistryTests(unittest.TestCase):
    def client(self, **kwargs):
        client = RdapWhoisClient(interval=0, **kwargs)
        self.addCleanup(client.close)
        client.session.get = Mock()
        return client

    def test_redirect_and_cache_use_actual_registry_and_original_timestamp(self):
        client = self.client()
        client.session.get.side_effect = [
            response(301, Location="https://rdap-bootstrap.arin.net/bootstrap/ip/8.8.8.8"),
            response(302, Location="https://rdap.arin.net/registry/ip/8.8.8.8"),
            response(data=record().record),
        ]
        first = client.lookup("8.8.8.8")
        self.assertIs(first, client.lookup("8.8.8.8"))
        self.assertEqual(client.session.get.call_count, 3)
        self.assertEqual(first.source_url, "https://rdap.arin.net/registry/ip/8.8.8.8")
        self.assertEqual(first.registry, "ARIN")
        self.assertTrue(first.retrieved_at.endswith("Z"))
        self.assertEqual(client.cache_hits, 1)

    def test_response_for_wrong_network_is_error(self):
        client = self.client()
        client.session.get.return_value = response(data=record("9.9.9.9").record)
        with self.assertRaises(WhoisLookupError):
            client.lookup("8.8.8.8")

    def test_nonpublic_addresses_never_make_requests(self):
        client = self.client()
        for ip in ("10.0.0.1", "127.0.0.1", "192.0.2.1", "224.0.0.1", "fd00::1"):
            with self.subTest(ip=ip), self.assertRaises(WhoisLookupError):
                client.lookup(ip)
        client.session.get.assert_not_called()

    def test_unexpected_redirect_is_not_followed(self):
        client = self.client()
        client.session.get.return_value = response(302, Location="http://127.0.0.1/private")
        with self.assertRaises(WhoisLookupError):
            client.lookup("8.8.8.8")
        self.assertEqual(client.session.get.call_count, 1)

    def test_not_found_is_cached_as_completed_lookup(self):
        client = self.client()
        client.session.get.return_value = response(404)
        self.assertIsNone(client.lookup("8.8.8.8"))
        self.assertIsNone(client.lookup("8.8.8.8"))
        self.assertEqual(client.session.get.call_count, 1)

    @patch("excel_intake.time.sleep")
    def test_timeout_retries_are_bounded_and_failure_cached(self, sleep):
        client = self.client(retries=1)
        client.session.get.side_effect = requests.Timeout("timed out")
        for _ in range(2):
            with self.assertRaises(WhoisLookupError):
                client.lookup("8.8.8.8")
        self.assertEqual(client.session.get.call_count, 2)

    @patch("excel_intake.time.sleep")
    def test_long_retry_after_does_not_sleep_or_hammer_next_ip(self, sleep):
        client = self.client(retries=1)
        client.session.get.return_value = response(429, **{"Retry-After": "120"})
        for ip in ("8.8.8.8", "9.9.9.9"):
            with self.assertRaises(WhoisLookupError):
                client.lookup(ip)
        self.assertEqual(client.session.get.call_count, 1)
        sleep.assert_not_called()

    def test_shared_ip_cache_is_reused_but_domain_match_is_per_group(self):
        client = self.client()
        client.session.get.return_value = response(data=record(domain="sample.com").record)
        groups = ValidatedLeads.group(entries(source(), source(hostname="sample.com")))
        self.assertIsNone(groups[0].qualify(client.lookup))
        self.assertIsNotNone(groups[1].qualify(client.lookup))
        self.assertEqual(client.session.get.call_count, 1)


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

    def test_end_to_end_groups_across_files_and_preserves_input_bytes(self):
        before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            copy = Path(temp) / "second.xlsx"
            shutil.copyfile(FIXTURE, copy)
            lookup = Mock(
                side_effect=lambda ip: record(ip, "example.com" if ip == "9.9.9.9" else "other.com")
            )
            runtime = LeadRuntime(REGION, lookup)
            leads = runtime.run([FIXTURE, copy])
        self.assertEqual(len(leads), 1)
        retained = leads[0].validated_leads[0].entries
        self.assertEqual(len(retained), 10)
        self.assertEqual(len({e.source.workbook for e in retained}), 2)
        self.assertEqual(retained[0].ip, "9.9.9.9")
        self.assertEqual(runtime.run_log["rows_read"], 28)
        self.assertEqual(runtime.run_log["validated_entries"], 16)
        self.assertEqual(runtime.run_log["rejected_entries"], 12)
        self.assertEqual(before, hashlib.sha256(FIXTURE.read_bytes()).hexdigest())

    def test_discovery_avoids_duplicate_files_and_excel_lock_files(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            shutil.copyfile(FIXTURE, folder / "one.xlsx")
            shutil.copyfile(FIXTURE, folder / "~$one.xlsx")
            (folder / "notes.txt").write_text("ignore")
            self.assertEqual(
                discover_workbooks([folder, folder / "one.xlsx"]), [(folder / "one.xlsx").resolve()]
            )

    def test_cli_writes_json_and_separate_run_log(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "leads.json"
            with (
                patch.object(RdapWhoisClient, "lookup", side_effect=lambda ip: record(ip)),
                redirect_stderr(StringIO()),
            ):
                code = main(
                    [str(FIXTURE), "--region", "North Carolina", "--output", str(output), "--quiet"]
                )
            self.assertEqual(code, 0)
            self.assertEqual(len(json.loads(output.read_text())), 1)
            self.assertEqual(
                json.loads(output.with_suffix(".run.json").read_text())["qualified_leads"], 1
            )

    def test_unavailable_lookup_is_logged_and_exit_status_is_two(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "leads.json"
            with (
                patch.object(RdapWhoisClient, "lookup", side_effect=WhoisLookupError("offline")),
                redirect_stderr(StringIO()),
            ):
                code = main(
                    [str(FIXTURE), "--region", "North Carolina", "--output", str(output), "--quiet"]
                )
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.read_text()), [])
            log = json.loads(output.with_suffix(".run.json").read_text())
            self.assertEqual(log["unresolved_leads"], 4)
            self.assertTrue(all(x["status"] == "lookup_error" for x in log["outcomes"]))

    def test_failed_input_does_not_replace_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "leads.json"
            output.write_text("previous result")
            with redirect_stderr(StringIO()):
                code = main(
                    [
                        str(FIXTURE),
                        "--region",
                        "North Carolina",
                        "--sheet",
                        "MissingHeaders",
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(code, 1)
            self.assertEqual(output.read_text(), "previous result")


if __name__ == "__main__":
    unittest.main()
