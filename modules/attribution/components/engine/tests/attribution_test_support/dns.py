"""Reusable synthetic dns fixtures and builders."""

import dns.message
import dns.rcode
import dns.resolver
import dns.rrset


class Resolver:
    nameservers = ["192.0.2.53"]

    def __init__(self, records):
        self.records = records
        self.calls = []

    def resolve(self, name, kind, **kwargs):
        assert kwargs["search"] is False and kwargs["lifetime"] > 0
        self.calls.append((name, kind))
        values = self.records.get((name, kind), [])
        if isinstance(values, Exception):
            raise values
        request = dns.message.make_query(name, kind)
        reply = dns.message.make_response(request)
        if values == "NXDOMAIN":
            reply.set_rcode(dns.rcode.NXDOMAIN)
            raise dns.resolver.NXDOMAIN(
                qnames=[request.question[0].name], responses={request.question[0].name: reply}
            )
        if values:
            reply.answer.append(dns.rrset.from_text(name, 60, "IN", kind, *values))
        reply = dns.message.from_wire(reply.to_wire())
        return dns.resolver.Answer(
            request.question[0].name, request.question[0].rdtype, 1, reply, "192.0.2.53"
        )
