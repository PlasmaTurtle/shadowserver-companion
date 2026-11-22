"""Provider-owned domains receiving reduced agency outreach priority.

Only the reported organization's own registrable domain is considered. ASN,
IP registration owner and hosting provider are never grounds to exclude a
customer business. These roots affect ranking and automatic contact work, not admission.
"""

from modules.tools.components.network_identity import root_domain

ISP_ROOTS = frozenset(
    {
        "att.com",
        "att.net",
        "sbcglobal.net",
        "bellsouth.net",
        "spectrum.com",
        "charter.com",
        "charter.net",
        "rr.com",
        "twc.com",
        "twcable.com",
        "twcbc.com",
        "comcast.com",
        "comcast.net",
        "xfinity.com",
        "verizon.com",
        "verizon.net",
        "frontier.com",
        "frontiernet.net",
        "windstream.com",
        "windstream.net",
        "kineticbywindstream.com",
        "brightspeed.com",
        "centurylink.com",
        "centurylink.net",
        "embarqhsd.net",
        "lumen.com",
        "level3.com",
        "level3.net",
        "cogentco.com",
        "zayo.com",
        "suddenlink.net",
        "optimum.com",
        "optimum.net",
        "optonline.net",
        "alticeusa.com",
        "earthlink.com",
        "earthlink.net",
        "tds.net",
        "tdstelecom.com",
        "consolidated.com",
        "googlefiber.net",
        "googlefiber.com",
        "gfiber.com",
        "webpass.net",
        "cox.com",
        "cox.net",
        "coxbusiness.com",
        "rcn.com",
        "rcn.net",
        "astound.com",
        "grandecom.net",
        "wavebroadband.com",
        "mediacomcable.com",
        "mchsi.com",
        "breezeline.com",
        "atlanticbb.net",
        "t-mobile.com",
        "tmodns.net",
    }
)

# A provider-branded subtree does not make every unrelated Google service an
# ISP lead. Likewise, a customer's own domain on these networks is unaffected.
ISP_SUBDOMAINS = frozenset({"fiber.google.com"})


def is_provider(hostname):
    value = str(hostname or "").strip().casefold().rstrip(".")
    return root_domain(value) in ISP_ROOTS or any(
        value == domain or value.endswith("." + domain) for domain in ISP_SUBDOMAINS
    )
