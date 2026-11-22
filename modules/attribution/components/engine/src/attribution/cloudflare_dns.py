"""Cloudflare's documented DNS JSON endpoint; provider-specific cache provenance."""
from urllib.parse import urlencode

from .google_dns import GooglePublicDnsProvider

ENDPOINT = "https://cloudflare-dns.com/dns-query"
SOURCE_NAME = "Cloudflare DNS"
DOCUMENTATION = "https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/dns-json/"


def query_url(name, kind):
    return ENDPOINT + "?" + urlencode({"name": name, "type": kind, "cd": "false", "do": "true"})


class CloudflareDnsProvider(GooglePublicDnsProvider):
    source_name = SOURCE_NAME
    endpoint = ENDPOINT
    documentation = DOCUMENTATION
    accept = "application/dns-json"
    query_url = staticmethod(query_url)

    def describe(self):
        result = super().describe()
        result.pop("edns_client_subnet", None)
        return result
