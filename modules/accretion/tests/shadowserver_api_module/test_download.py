"""All acquisition tests use synthetic bytes and in-memory unsigned openers."""

from tests.filesystem_helpers import create_test_symlink

from dataclasses import replace
from contextlib import contextmanager
import errno
import gzip
import hashlib
from http.client import IncompleteRead
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from modules.accretion.components.shadowserver_reports.control import Operation
from modules.accretion.components.shadowserver_reports.download import ReportDownloader, iter_rows
from modules.accretion.components.shadowserver_reports.errors import (
    BudgetExceeded,
    Cancelled,
    DownloadError,
    StorageError,
)
from modules.accretion.components.shadowserver_reports.models import ReportDescriptor


CSV = b'"timestamp","ip","hostname","new_column"\r\n"2026-11-08 12:00:00","192.0.2.8","example.test","unknown\nmultiline"\r\n'


class Response(io.BytesIO):
    def __init__(self, body, *, status=200, headers=None, url=None):
        super().__init__(body)
        self.status = status
        self.headers = (
            {"Content-Type": "text/csv", "Content-Length": str(len(body))}
            if headers is None
            else headers
        )
        self.url = url

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, body=CSV, *, status=200, headers=None, response_type=Response, url=None):
        self.body = body
        self.status = status
        self.headers = headers
        self.response_type = response_type
        self.url = url
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        return self.response_type(
            self.body, status=self.status, headers=self.headers, url=self.url or request.full_url
        )


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.report = ReportDescriptor(
            "2026-11-08-scan_http_vulnerable-example.csv",
            "example",
            "scan_http_vulnerable",
            "2026-11-08",
            "opaque-ID?secret_part=a+b/c&next=value",
        )

    def downloader(self, body=CSV, **kwargs):
        opener = kwargs.pop("opener", None) or Opener(body)
        return ReportDownloader(self.root, opener=opener, **kwargs)

    def assert_no_published_files(self):
        self.assertEqual(list((self.root / "reports").glob("*")), [])
        self.assertEqual(list((self.root / "receipts").glob("*")), [])
        self.assertEqual(list((self.root / ".partial").glob("*")), [])

    def test_preserves_original_bytes_unknown_columns_and_source_date(self):
        receipt = self.downloader().download_report(self.report)
        self.assertEqual(Path(receipt.path).read_bytes(), CSV)
        self.assertEqual(receipt.sha256, hashlib.sha256(CSV).hexdigest())
        self.assertEqual(receipt.size_bytes, len(CSV))
        self.assertEqual(receipt.report_date, "2026-11-08")
        self.assertEqual(list(iter_rows(receipt.path))[0]["new_column"], "unknown\nmultiline")
        stored = json.loads(next((self.root / "receipts").glob("*.json")).read_text())
        self.assertEqual(stored, receipt.public_dict())
        self.assertNotIn(self.report.download_id, json.dumps(stored))
        self.assertNotIn("secret_part", repr(receipt))

    def test_valid_csv_is_not_rejected_for_a_mislabeled_content_type(self):
        # The live download endpoint serves CSV attachments as text/html.
        # Acceptance must depend on the complete file, not its MIME label.
        for content_type in (
            "text/html; charset=UTF-8",
            "application/json",
            "text/xml",
            "",
        ):
            with self.subTest(content_type=content_type):
                opener = Opener(
                    headers={
                        "Content-Type": content_type,
                        "Content-Length": str(len(CSV)),
                        "Content-Disposition": 'attachment; filename="report.csv"',
                    }
                )
                receipt = self.downloader(opener=opener).download_report(self.report)
                self.assertEqual(Path(receipt.path).read_bytes(), CSV)
                self.assertEqual(receipt.sha256, hashlib.sha256(CSV).hexdigest())
                self.assertEqual(len(list(iter_rows(receipt.path))), 1)
                self.assertEqual(len(opener.calls), 1)

    def test_error_documents_are_rejected_regardless_of_mime_or_attachment(self):
        for body in (
            b"<!doctype html><html>Error, expired</html>",
            b'{"error":"expired","status":401}',
            b'<?xml version="1.0"?><error>expired, denied</error>',
            b"\xef\xbb\xbf  <html>error, expired</html>",
        ):
            for content_type in ("text/html", "text/csv", "application/octet-stream"):
                with self.subTest(body=body, content_type=content_type):
                    opener = Opener(
                        body,
                        headers={
                            "Content-Type": content_type,
                            "Content-Length": str(len(body)),
                            "Content-Disposition": 'attachment; filename="report.csv"',
                        },
                    )
                    with self.assertRaises(DownloadError):
                        self.downloader(opener=opener).download_report(self.report)
                    self.assert_no_published_files()

    def test_error_document_bytes_never_reach_staging_files(self):
        original_fdopen = os.fdopen
        written = []

        @contextmanager
        def monitored_fdopen(*args, **kwargs):
            with original_fdopen(*args, **kwargs) as output:

                class Monitor:
                    def write(self, value):
                        written.append(bytes(value))
                        return output.write(value)

                    def flush(self):
                        return output.flush()

                    def fileno(self):
                        return output.fileno()

                yield Monitor()

        bad = b'<html><script src="https://untrusted.invalid/example.js"></script></html>'
        for compressed in (False, True):
            with self.subTest(compressed=compressed):
                report = (
                    replace(self.report, filename=self.report.filename + ".gz")
                    if compressed
                    else self.report
                )
                body = gzip.compress(bad) if compressed else bad
                written.clear()
                with patch(
                    "modules.accretion.components.shadowserver_reports.download.os.fdopen",
                    monitored_fdopen,
                ):
                    with self.assertRaises(DownloadError):
                        self.downloader(body).download_report(report)
                self.assertFalse(any(written))
                self.assert_no_published_files()

    def test_split_header_and_compressed_prefix_preserve_valid_bytes(self):
        class ByteResponse(Response):
            def read1(self, size):
                return super().read1(min(size, 1))

        for compressed in (False, True):
            with self.subTest(compressed=compressed):
                body = gzip.compress(CSV) if compressed else CSV
                report = (
                    replace(self.report, filename=self.report.filename + ".gz")
                    if compressed
                    else self.report
                )
                receipt = self.downloader(
                    opener=Opener(body, response_type=ByteResponse)
                ).download_report(report)
                self.assertEqual(Path(receipt.path).read_bytes(), body)
                self.assertEqual(len(list(iter_rows(receipt.path))), 1)

    def test_download_is_unsigned_and_preserves_query_punctuation(self):
        opener = Opener()
        self.downloader(opener=opener).download_report(self.report)
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url, "https://dl.shadowserver.org/" + self.report.download_id)
        self.assertIsNone(request.data)
        self.assertEqual(request.method, "GET")
        self.assertFalse(
            {"hmac2", "authorization", "apikey"} & {k.lower() for k, _ in request.header_items()}
        )
        self.assertLessEqual(timeout, 20)

    def test_repeated_bytes_reused_with_each_acquisition_preserved(self):
        downloader = self.downloader()
        first = downloader.download_report(self.report)
        second = downloader.download_report(
            replace(self.report, download_id="refreshed-capability")
        )
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.path, second.path)
        self.assertEqual(first.logical_id, second.logical_id)
        self.assertNotEqual(first.source_fingerprint, second.source_fingerprint)
        self.assertEqual(len(list((self.root / "reports").iterdir())), 1)
        self.assertEqual(len(list((self.root / "receipts").iterdir())), 2)

    def test_corrected_content_preserves_old_version(self):
        first = self.downloader().download_report(self.report)
        corrected = CSV.replace(b"192.0.2.8", b"192.0.2.9")
        second = self.downloader(corrected).download_report(self.report)
        self.assertNotEqual(first.path, second.path)
        self.assertEqual(Path(first.path).read_bytes(), CSV)
        self.assertEqual(Path(second.path).read_bytes(), corrected)
        self.assertEqual(first.logical_id, second.logical_id)

    def test_duplicate_storage_is_rehashed_and_corruption_is_not_overwritten(self):
        downloader = self.downloader()
        first = downloader.download_report(self.report)
        Path(first.path).write_bytes(b"corruption")
        with self.assertRaises(StorageError):
            downloader.download_report(self.report)
        self.assertEqual(Path(first.path).read_bytes(), b"corruption")
        self.assertEqual(len(list((self.root / "receipts").glob("*"))), 1)
        self.assertEqual(list((self.root / ".partial").glob("*")), [])

    def test_same_bytes_different_subscription_keep_provenance(self):
        downloader = self.downloader()
        first = downloader.download_report(self.report)
        second = downloader.download_report(replace(self.report, subscription="second"))
        self.assertEqual(first.path, second.path)
        self.assertNotEqual(first.logical_id, second.logical_id)
        self.assertEqual(len(list((self.root / "receipts").glob("*"))), 2)

    def test_gzip_preserved_and_streamed_with_unknown_columns(self):
        body = gzip.compress(CSV, mtime=0)
        report = replace(self.report, filename=self.report.filename + ".gz")
        receipt = self.downloader(body).download_report(report)
        self.assertEqual(Path(receipt.path).read_bytes(), body)
        self.assertEqual(list(iter_rows(receipt.path))[0]["hostname"], "example.test")

    def test_gzip_expansion_limit(self):
        body = gzip.compress(b"a,b\n" + b"1,2\n" * 1000, mtime=0)
        report = replace(self.report, filename=self.report.filename + ".gz")
        with self.assertRaises(BudgetExceeded):
            self.downloader(body, max_file_bytes=1000).download_report(report)
        self.assert_no_published_files()

    def test_invalid_and_truncated_gzip(self):
        for body in (b"\x1f\x8binvalid", gzip.compress(CSV, mtime=0)[:-8]):
            with self.subTest(body=body[:10]), self.assertRaises(DownloadError):
                self.downloader(body).download_report(
                    replace(self.report, filename=self.report.filename + ".gz")
                )
            self.assert_no_published_files()

    def test_compression_filename_mismatch_rejected(self):
        with self.assertRaises(DownloadError):
            self.downloader(gzip.compress(CSV)).download_report(self.report)
        with self.assertRaises(DownloadError):
            self.downloader().download_report(
                replace(self.report, filename=self.report.filename + ".gz")
            )
        self.assert_no_published_files()

    def test_unsafe_windows_metadata_names_rejected_before_request(self):
        opener = Opener()
        for filename in (
            "../report.csv",
            "..\\report.csv",
            "C:report.csv",
            "AUX.csv",
            "con.csv",
            "COM1.csv",
            "LPT².csv",
            "report.csv.",
            "report.csv ",
            "report\n.csv",
            "report.csv:extra",
            "/report.csv",
            "CONOUT$.csv",
            "report.zip",
        ):
            with self.subTest(filename=filename), self.assertRaises(DownloadError):
                self.downloader(opener=opener).download_report(
                    replace(self.report, filename=filename)
                )
        self.assertEqual(opener.calls, [])

    def test_invalid_tokens_rejected_before_request(self):
        opener = Opener()
        for token in (
            "",
            "https://elsewhere.example/file",
            "//elsewhere.example/file",
            "../file",
            "file#fragment",
            "file\nsecret",
            "file\\secret",
            "?query-only",
            "%2fescape",
            "%2e%2e",
            "white space",
            "tökén",
        ):
            with self.subTest(token=token), self.assertRaises(DownloadError):
                self.downloader(opener=opener).download_report(
                    replace(self.report, download_id=token)
                )
        self.assertEqual(opener.calls, [])

    def test_catalog_documentation_url_is_ignored(self):
        opener = Opener()
        self.downloader(opener=opener).download_report(
            replace(self.report, metadata={"url": "https://unrelated.example/"})
        )
        self.assertTrue(opener.calls[0][0].full_url.startswith("https://dl.shadowserver.org/"))

    def test_html_and_json_masquerades_rejected(self):
        for body in (
            b"<!doctype html><html>Expired token</html>",
            b'{"error":"expired"}',
            b'["unauthorized"]',
            b"Expired download link",
        ):
            with self.subTest(body=body), self.assertRaises(DownloadError):
                self.downloader(body).download_report(self.report)
            self.assert_no_published_files()

    def test_csv_headers_rows_and_encoding_validation(self):
        for body in (
            b"",
            b"a,a\n1,2\n",
            b"a,\n1,2\n",
            b"a,b\n1,2,3\n",
            b'a,b\n"unterminated,2\n',
            b"a,b\n\xff,2\n",
        ):
            with self.subTest(body=body), self.assertRaises(DownloadError):
                self.downloader(body).download_report(self.report)
            self.assert_no_published_files()

    def test_header_only_csv_is_valid_empty_report(self):
        receipt = self.downloader(b"timestamp,ip\r\n").download_report(self.report)
        self.assertEqual(list(iter_rows(receipt.path)), [])

    def test_unknown_content_length_still_bounded(self):
        with self.assertRaises(BudgetExceeded):
            self.downloader(opener=Opener(headers={}), max_file_bytes=20).download_report(
                self.report
            )
        self.assert_no_published_files()

    def test_content_length_mismatch(self):
        with self.assertRaises(DownloadError):
            self.downloader(
                opener=Opener(headers={"Content-Length": str(len(CSV) + 1)})
            ).download_report(self.report)
        self.assert_no_published_files()

    def test_byte_budget_shared_with_whole_operation(self):
        operation = Operation(max_bytes=len(CSV) + 1)
        operation.consume_bytes(10)
        with self.assertRaises(BudgetExceeded):
            self.downloader().download_report(self.report, operation=operation)
        self.assertEqual(operation.requests, 1)
        self.assert_no_published_files()

    def test_cancelled_before_request(self):
        event = threading.Event()
        event.set()
        opener = Opener()
        with self.assertRaises(Cancelled):
            self.downloader(opener=opener).download_report(
                self.report, operation=Operation(cancel_event=event)
            )
        self.assertEqual(opener.calls, [])

    def test_cancelled_midtransfer_cleans_partial(self):
        event = threading.Event()

        class CancelResponse(Response):
            def read1(self, size):
                event.set()
                return super().read1(size)

        with self.assertRaises(Cancelled):
            self.downloader(opener=Opener(response_type=CancelResponse)).download_report(
                self.report, operation=Operation(cancel_event=event)
            )
        self.assert_no_published_files()

    def test_partial_transfer_is_not_published(self):
        class BrokenResponse(Response):
            def read1(self, size):
                if self.tell():
                    raise IncompleteRead(b"upstream private data")
                return super().read1(10)

        with self.assertRaises(DownloadError) as error:
            self.downloader(opener=Opener(response_type=BrokenResponse)).download_report(
                self.report
            )
        self.assertNotIn("private data", str(error.exception))
        self.assert_no_published_files()

    def test_server_errors_and_redirects_have_no_retry_or_leak(self):
        for status in (302, 403, 404, 429, 503):
            opener = Opener(status=status)
            with self.subTest(status=status), self.assertRaises(DownloadError):
                self.downloader(opener=opener).download_report(self.report)
            self.assertEqual(len(opener.calls), 1)
            self.assert_no_published_files()
        opener = Opener(url="https://unapproved.example/private-token")
        with self.assertRaises(DownloadError):
            self.downloader(opener=opener).download_report(self.report)
        self.assert_no_published_files()

    def test_http_exception_never_exposes_capability(self):
        class ErrorOpener:
            def open(self, request, timeout):
                raise HTTPError(request.full_url, 403, "private-capability", {}, None)

        with self.assertRaises(DownloadError) as error:
            self.downloader(opener=ErrorOpener()).download_report(self.report)
        self.assertNotIn("private-capability", str(error.exception))
        self.assertNotIn(self.report.download_id, str(error.exception))
        self.assert_no_published_files()

    def test_disk_full_cleans_partial_and_redacts_path(self):
        with patch(
            "modules.accretion.components.shadowserver_reports.download.os.fsync",
            side_effect=OSError(errno.ENOSPC, "private-path"),
        ):
            with self.assertRaises(StorageError) as error:
                self.downloader().download_report(self.report)
        self.assertNotIn("private-path", str(error.exception))
        self.assert_no_published_files()

    def test_report_internal_directory_symlink_rejected(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        create_test_symlink(self.root / "reports", elsewhere, target_is_directory=True)
        with self.assertRaises(StorageError):
            self.downloader().download_report(self.report)
        self.assertEqual(list(elsewhere.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
