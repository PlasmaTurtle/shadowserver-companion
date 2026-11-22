"""Reusable synthetic intake profiles fixtures and builders."""

import csv
import io


class Registry:
    def __init__(self):
        self.calls = []

    def lookup(self, ip):
        self.calls.append(ip)
        return None

    def close(self):
        pass


def row(**kwargs):
    return {
        "hostname": "mail2.example.com",
        "ip": "8.8.8.8",
        "tag": "eol-php",
        "version": "Apache/2.4.6 PHP/7.3.25",
        "region": "North Carolina",
        "severity": "critical",
        "http_code": 200,
        **kwargs,
    }


def csv_bytes(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()
