"""Streaming workbook/CSV readers shared by intake and read-only observatory views."""

from __future__ import annotations
import csv
import gzip
import io
from pathlib import Path
from zipfile import ZipFile
from collections.abc import Generator
from openpyxl import load_workbook
from .domains import REQUIRED_COLUMNS
from .records import UnvalidatedEntry, ValidatedEntry

MAX_CSV_EXPANDED = 512 * 1024 * 1024


class _LimitedReader(io.RawIOBase):
    """Bound decompressed bytes, including a single pathological CSV line."""

    def __init__(self, stream, limit):
        self.stream, self.limit, self.total = stream, limit, 0

    def readable(self):
        return True

    def readinto(self, buffer):
        data = self.stream.read(min(len(buffer), self.limit - self.total + 1))
        self.total += len(data)
        if self.total > self.limit:
            raise ValueError("Expanded CSV exceeds the 512 MiB limit")
        buffer[: len(data)] = data
        return len(data)


class ExcelReader:
    def read(
        self, path: Path, sheet_name: str | None = None, *, required_columns=REQUIRED_COLUMNS
    ) -> Generator[UnvalidatedEntry, None, None]:
        workbook = load_workbook(path, read_only=True, data_only=False)
        try:
            worksheets = {sheet.title: sheet for sheet in workbook.worksheets}
            if not worksheets:
                raise ValueError("Workbook has no worksheets")
            if sheet_name is not None and sheet_name not in worksheets:
                raise ValueError(f"Worksheet {sheet_name!r} was not found")
            sheet = (
                worksheets[sheet_name]
                if sheet_name is not None
                else next(iter(worksheets.values()))
            )
            rows = sheet.iter_rows(values_only=True)
            header = list(next(rows, ()))
            while header and header[-1] in (None, ""):
                header.pop()
            missing = [name for name in required_columns if name not in header]
            if missing:
                raise ValueError(
                    f"Worksheet {sheet.title!r} is missing columns: {', '.join(missing)}"
                )
            if not header or any(not isinstance(name, str) or not name for name in header):
                raise ValueError(f"Worksheet {sheet.title!r} has an unnamed or non-text header")
            if len(set(header)) != len(header):
                raise ValueError(f"Worksheet {sheet.title!r} has duplicate column names")

            for row_number, values in enumerate(rows, start=2):
                if any(value not in (None, "") for value in values[len(header) :]):
                    raise ValueError(
                        f"Worksheet {sheet.title!r} row {row_number} has data without a column name"
                    )
                yield UnvalidatedEntry(
                    workbook=str(path),
                    sheet=sheet.title,
                    row=row_number,
                    fields={
                        name: values[index] if index < len(values) else None
                        for index, name in enumerate(header)
                    },
                )
        finally:
            workbook.close()


def read_entries(path, sheet, *, max_csv_bytes=MAX_CSV_EXPANDED):
    path = Path(path)
    if path.name.lower().endswith((".csv", ".csv.gz")):
        opener = gzip.open if path.name.lower().endswith(".csv.gz") else open
        with (
            opener(path, "rb") as raw,
            io.TextIOWrapper(
                io.BufferedReader(_LimitedReader(raw, max_csv_bytes)),
                encoding="utf-8-sig",
                newline="",
            ) as handle,
        ):
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            if not headers or len(headers) != len(set(headers)) or any(not h for h in headers):
                raise ValueError("CSV has duplicate or blank column names")
            for index, row in enumerate(reader, 2):
                if None in row:
                    raise ValueError(f"CSV row {index} has more values than column names")
                yield UnvalidatedEntry(str(path), "CSV", index, row)
    else:
        with ZipFile(path) as archive:
            if sum(i.file_size for i in archive.infolist()) > 250 * 1024 * 1024:
                raise ValueError("Expanded workbook exceeds the 250 MB limit")
        yield from ExcelReader().read(path, sheet or None, required_columns=())


def restore_entry(data):
    return ValidatedEntry(
        source=UnvalidatedEntry(**data["source"]),
        ip=data["ip"],
        private_ip=data["private_ip"],
        normalized=data.get("normalized", {}),
    )
