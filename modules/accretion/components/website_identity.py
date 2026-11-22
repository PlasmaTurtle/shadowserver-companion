"""Qualification policy for the rendered page selected by the browser."""

import re
from urllib.parse import urlsplit

from modules.investigations.components.website_evidence import related_capture
from modules.tools.components.network_identity import extract_domain


_PARKING = re.compile(
    r"\b(?:this domain (?:name )?is (?:for sale|parked)|buy this domain|"
    r"domain parking|parked free|this domain may be for sale)\b",
    re.I,
)
_GENERIC = set(
    "a an the in to of at for and site website web page home welcome default index "
    "sign signin login log account portal password username email enter your here "
    "please secure access dashboard authentication single on sso server test it "
    "under construction coming soon forbidden not found support services microsoft "
    "outlook office exchange webmail roundcube cpanel apache nginx iis ubuntu error "
    "redirecting powered by success works app application client management interface "
    "administrator admin control panel remote desktop gateway my new hosting "
    "authenticate authentication continue authentication identity verification "
    "saml single signon new hosted customer member members central company "
    "business organization corporation inc llc limited ltd group google accounts "
    "workspace okta auth0 keycloak adfs identity wordpress hosting godaddy default "
    "provider service member members cloud home homepages customer".split()
)
_HOSTING_PAGE = re.compile(
    r"\b(?:default (?:web ?site|server) page|welcome to (?:nginx|your new (?:hosting|website))|"
    r"apache2? .*default page|web ?site (?:coming soon|under construction))\b",
    re.I,
)
_LEGAL = re.compile(
    r"\b(?:llc|inc\.?|ltd\.?|corporation|foundation|university|city of|county of)\b", re.I
)
_LOGIN = re.compile(
    r"\b(?:sign[ -]?in|log[ -]?in|authenticate|single sign[ -]?on|authentication)\b", re.I
)


def rejection_reason(page, root):
    if not related_capture(page, root):
        return "website_identity_review"
    site_name, heading, title = (
        str(page.get(key) or "").strip() for key in ("site_name", "heading", "title")
    )
    labels = (site_name, heading, title)
    if _PARKING.search(" ".join([*labels, str(page.get("page_text") or "")])):
        return "website_parked"
    if _HOSTING_PAGE.search(" ".join(labels)):
        return "website_unidentified"
    host = urlsplit(page["final_url"]).hostname or ""
    brand = extract_domain(root).domain.casefold()
    login = page.get("capture_status") == "login_required" or any(_LOGIN.search(s) for s in labels)
    for label in labels:
        # Displaying only the destination hostname adds no independent page identity.
        normalized = label.casefold().replace(host.casefold(), " ").replace(root.casefold(), " ")
        tokens = re.findall(r"[^\W_]+", normalized)
        words = {word for word in tokens if len(word) > 1 and not word.isdigit()}
        if label == site_name and words - _GENERIC and not login:
            return None
        if label.isupper() and label.casefold() == brand:
            return None
        if (
            len(brand) >= 2
            and brand not in _GENERIC
            and any(
                "".join(tokens[i : i + size]) == brand
                for i in range(len(tokens))
                for size in (1, 2, 3)
            )
        ):
            return None
        if (
            words - _GENERIC
            and _LEGAL.search(label)
            and heading
            and title
            and (heading.casefold() in title.casefold() or title.casefold() in heading.casefold())
        ):
            return None
    return "website_unidentified"
