"""Conservative extraction of contacts explicitly published in visible content."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

from .policy import DiscoveryError, approved_url

EMAIL = re.compile(
    r"(?<![\w.+-])[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9.-]*[A-Z0-9])?\.[A-Z]{2,63}(?![\w-]|\.[A-Z0-9])",
    re.I,
)
PHONE = re.compile(
    r"(?:\+\d[\d .()/-]{5,}\d|\(?\d{2,4}\)?[ .-]\d[\d .()/-]{4,}\d)(?:\s*(?:ext\.?|extension|x)\s*\d{1,8})?",
    re.I,
)
ROLE = re.compile(
    r"\b(?:chief (?:information security|information|technology|executive) officer|(?:IT|information technology|security|technical|technology|network) (?:director|manager|officer|team|department|support)|(?:director|head) of (?:IT|information technology|security|technology)|CISO|CIO|CTO|CEO|president|managing director|owner)\b",
    re.I,
)
BLOCK = {
    "p",
    "li",
    "address",
    "td",
    "section",
    "article",
    "div",
    "footer",
    "header",
    "body",
    "form",
}
SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "object"}
VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def clean(value):
    return " ".join(value.split())


class Node:
    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs or []), parent
        self.children = []
        self.closed = False

    def text(self):
        return clean(
            " ".join(item if isinstance(item, str) else item.text() for item in self.children)
        )

    def descendants(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.descendants()


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = Node("body")
        self.stack = [self.root]
        self.skip = []
        self.count = 0
        self.limited = False
        self.script_count = 0
        self.javascript_notice = bool(re.search(r"enable[^<]{0,60}javascript", text, re.I))
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.script_count += 1
        style = attrs.get("style", "").lower().replace(" ", "")
        hidden = (
            "hidden" in attrs
            or attrs.get("aria-hidden") == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        )
        if self.skip or tag in SKIP or hidden:
            if tag not in VOID:
                self.skip.append(tag)
            return
        self.count += 1
        if self.count > 20000 or len(self.stack) >= 96:
            self.limited = True
            return
        node = Node(tag, attrs.items(), self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.skip:
            if tag in self.skip:
                self.skip = self.skip[: self.skip.index(tag)]
            return
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack[index].closed = True
                del self.stack[index:]
                return

    def handle_data(self, value):
        if not self.skip:
            self.stack[-1].children.append(value)


HEADINGS = {"h2", "h3", "h4", "h5", "h6"}
NONROUTINE = {"privacy", "hr", "media", "investor", "compliance", "physical_emergency"}
PURPOSE_PRIORITY = {
    "security": 0,
    "it": 1,
    "product_support": 2,
    "management": 3,
    "general": 4,
    "other": 5,
    "privacy": 6,
    "hr": 7,
    "media": 8,
    "investor": 9,
    "compliance": 10,
    "physical_emergency": 11,
}


def _has_contact(node):
    return any(
        n.tag == "form" or n.attrs.get("href", "").lower().startswith(("mailto:", "tel:"))
        for n in (node, *node.descendants())
    ) or bool(EMAIL.search(node.text()))


def _local_heading(node):
    headings = [n for n in (node, *node.descendants()) if n.tag in HEADINGS]
    if headings:
        return headings[-1].text()[:200]
    # Some contact directories use a short bold paragraph as a department label
    # before a list of phone/email values. Accept only a wholly bold label, not
    # a highlighted word inside a paragraph or an unrelated content card.
    if node.tag in {"p", "b", "strong"}:
        text = node.text()
        bold = [n.text() for n in (node, *node.descendants()) if n.tag in {"b", "strong"}]
        if 0 < len(text) <= 180 and text in bold and not EMAIL.search(text):
            return text
    return ""


def captured_element(node):
    """A closing boundary proves this element ended before a capture cutoff."""
    while node is not None:
        if node.closed:
            return True
        node = node.parent
    return False


def context_for(node, *, complete_only=False):
    """Use the contact's block and its nearest local heading, never a page heading."""
    block = node
    while block.parent is not None and block.tag not in BLOCK:
        block = block.parent
    if complete_only and not captured_element(block):
        # A complete anchor can survive in an unfinished paragraph/card, but
        # the unfinished wrapper must not supply purpose, identity or role.
        block = node
    if block.tag in {"body", "header"}:
        return block, node.text()[:600] if node is not block else ""
    context = block.text()[:4000]
    # A paragraph or inner contact wrapper often follows a heading in its card.
    # Stop at another contact or a content boundary so a neighboring department
    # cannot classify this value. No h1 or document-global heading is inherited.
    cursor = node
    for _ in range(5):
        parent = cursor.parent
        if parent is None or parent.tag in {"body", "header", "footer", "main", "nav"}:
            break
        siblings = parent.children
        before = siblings[: siblings.index(cursor)]
        for sibling in reversed(before):
            if isinstance(sibling, str):
                if EMAIL.search(sibling):
                    break
                continue
            if complete_only and not captured_element(sibling):
                break
            if _has_contact(sibling):
                break
            heading = _local_heading(sibling)
            if heading:
                if heading:
                    if context.startswith(heading):
                        context = heading + " — " + context[len(heading) :].lstrip()
                    else:
                        context = heading + " — " + context
                return block, context
            if sibling.tag in {"section", "article", "form", "nav", "main"}:
                break
        # A card that already contains multiple contacts must not inherit a
        # surrounding section's purpose. Individual explicit labels still work.
        if (
            parent is not block
            and _has_contact(parent)
            and len(set(EMAIL.findall(parent.text()))) > 1
        ):
            break
        cursor = parent
    return block, context


def purpose_role(context):
    role = ROLE.search(context)
    role_text = role.group(0) if role else ""
    checks = (
        (
            "physical_emergency",
            r"\b(?:pipeline emergencies|pipeline emergency|gas leak|medical emergency|physical security|emergency\s*[:—-]|emergency (?:line|number|hotline)|life[- ]threatening|immediate danger)(?=\W|$)",
        ),
        (
            "hr",
            r"\b(?:human resources|people support|recruit(?:ing|ment)|careers?|employment inquiries|job applicants?)\b",
        ),
        (
            "media",
            r"\b(?:media\s*[:—-]|media (?:relations|inquiries|contact)|press (?:(?:&|and) analyst )?(?:relations|contact|inquiries|office)|public relations|corporate communications)(?=\W|$)",
        ),
        ("investor", r"\binvestor (?:relations|inquiries|contact)\b"),
        (
            "privacy",
            r"\b(?:privacy\s*[:—-]|privacy (?:office|officer|questions|inquiries|notice|policy|preferences|contact)|data protection officer|privacy@)",
        ),
        (
            "compliance",
            r"\b(?:ethics|whistleblower|compliance\s*[:—-]|compliance (?:office|hotline|contact|inquiries)|compliance\s*(?:&|and)\s*security inquiries)(?=\W|$)",
        ),
        (
            "general",
            r"(?:^|[;—])\s*(?:general\s*:|general (?:inquiries|enquiries|contact)|customer (?:service|support)|sales (?:inquiries|contact|support))(?=\W|$)",
        ),
        (
            "security",
            r"\b(?:cyber(?:security| security) (?:issue|incident|concern|contact|team|report|reporting)|information security|security\s*(?::|[-–—]|\b(?:contact|team|department|officer|manager|director|support|issue|concern)\b)|(?:report|disclose|reporting)\s+(?:a\s+)?(?:cybersecurity|security|vulnerabilit(?:y|ies))|(?:responsible|coordinated) disclosure|vulnerability (?:report|contact|disclosure)|PSIRT|CSIRT|CISO|incident response)(?=\W|$)",
        ),
        (
            "product_support",
            r"\b(?:tech support|(?:product|application|app|portal|software|platform|shipper|carrier)[^.;]{0,60}(?:support|help)|(?:support|help)[^.;]{0,60}(?:product|application|app|portal|software|platform|shipper|carrier))\b",
        ),
        (
            "it",
            r"\b(?:IT\s*[:—-]|IT (?:department|team|director|manager|support|service desk|help desk|helpdesk)|information technology|technical (?:support|assistance|issues?|problems?|help)|computer support|webmaster|network (?:team|manager)|CTO|CIO)(?=\W|$)",
        ),
        ("management", r"\b(?:CEO|president|owner|managing director|chief executive officer)\b"),
    )
    for purpose, pattern in checks:
        if re.search(pattern, context, re.I):
            return purpose, role_text
    return "general", role_text


def contact_identity(kind, value):
    """Within-run dedupe only; never changes persisted candidate_key semantics."""
    if kind != "phone":
        return kind, value.casefold() if kind == "email" else value
    text = re.sub(r"(?:;ext=|\b(?:ext\.?|extension)|\bx)\s*", "x", value.lower())
    number, _, extension = text.partition("x")
    digits = re.sub(r"\D", "", number)
    # Normalize conventional NANP local/+1 forms only. Other country codes and
    # extensions remain distinct, and the original published value is retained.
    nanp = digits[1:] if len(digits) == 11 and digits.startswith("1") else digits
    if re.fullmatch(r"[2-9]\d{2}[2-9]\d{6}", nanp) and (
        not number.strip().startswith("+") or digits.startswith("1")
    ):
        number = "+1" + nanp
    else:
        number = ("+" if number.strip().startswith("+") else "") + digits
    return kind, number + ("x" + re.sub(r"\D", "", extension) if extension else "")


def candidate_key(kind, value):
    """Stable value identity shared by discovery and persistence validation."""
    normalized = value.lower() if kind == "email" else value
    if kind == "phone":
        normalized = re.sub(
            r"[^\d+x]", "", re.sub(r"\b(?:ext\.?|extension)\s*", "x", value.lower())
        )
    return hashlib.sha256((kind + "\0" + normalized).encode()).hexdigest()


def candidate(kind, value, context, *, purpose=None, name="", role=""):
    key = candidate_key(kind, value)
    classified, inferred_role = purpose_role(context)
    return {
        "key": key,
        "kind": kind,
        "value": value,
        "name": name,
        "role": role or inferred_role,
        "purpose": purpose or classified,
        "excerpt": clean(context)[:600],
        "recommended_for_outreach": (purpose or classified) not in NONROUTINE,
    }


def excerpt_for(context, value):
    where = context.lower().find(value.lower())
    if where < 0:
        return context[:600]
    return context[max(0, where - 180) : where + len(value) + 220]


def fax_number(value, context, label=""):
    """Honor the label next to this number, including a trailing '(Fax)'."""
    identity = contact_identity("phone", value)
    matches = [
        m for m in PHONE.finditer(context) if contact_identity("phone", m.group()) == identity
    ]
    if matches:
        match = matches[0]
        before, after = context[: match.start()], context[match.end() :]
    else:
        # A tel: value can have a different visible format, or use 'Fax us'.
        if re.search(r"\b(?:fax|facsimile)\b", label, re.I):
            return True
        where = context.find(label) if label else -1
        before = context[:where] if where >= 0 else context
        after = context[where + len(label) :] if where >= 0 else ""
    if re.match(r"\s*[([]?\s*(?:fax|facsimile)\b", after, re.I):
        return True
    # A label belonging to the previous number must not leak into this one.
    prior = list(PHONE.finditer(before))
    local = before[prior[-1].end() :] if prior else before
    local = re.sub(r"^\s*\([^)]*\)", "", local)
    labels = list(
        re.finditer(r"\b(?:fax|facsimile|phone|telephone|tel|mobile|call)\b", local, re.I)
    )
    return bool(labels and labels[-1].group().lower() in {"fax", "facsimile"})


def restricted_mailbox(value):
    # These explicit recipient restrictions can disqualify a broad support-card
    # label. Never infer a positive security/technical role from an address.
    local = value.partition("@")[0]
    return bool(
        re.search(
            r"(?:^|[._+-])(?:recruiting|recruitment|careers?|jobs?|hr)(?:$|[._+-])", local, re.I
        )
    )


def _local_identity(block, context):
    # An explicit role plus one short name heading in this same contact block.
    # Do not assign names across cards, pages or multiple email recipients.
    _, role = purpose_role(context)
    if not role or len(set(EMAIL.findall(context))) > 1:
        return "", ""
    headings = [n.text() for n in block.descendants() if n.tag in {"h2", "h3", "h4", "strong"}]
    names = [
        x
        for x in headings
        if re.fullmatch(r"[A-Z][A-Za-z'’-]+(?: [A-Z][A-Za-z'’-]+){1,3}", x)
        and not ROLE.search(x)
        and not re.search(
            r"\b(?:contact|team|department|support|security|leadership|management|company|office|information|technology)\b",
            x,
            re.I,
        )
    ]
    if len(names) == 1:
        return names[0], role
    match = re.search(
        r"\bName:\s*([A-Z][A-Za-z'’-]+(?: [A-Z][A-Za-z'’-]+){1,3})(?=\s*(?:[,;|]|Role:|$))", context
    )
    return (match.group(1), role) if match else ("", "")


def review_url(value):
    """Validate a published HTTPS destination without fetching or trusting its host.

    Query-bearing routes are reviewable, but unknown queries never become crawl
    targets. The original URL remains evidence even when tracking is removable.
    """
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    try:
        return approved_url(value, {host})
    except DiscoveryError as error:
        if error.code != "query_not_supported":
            raise
        base = approved_url(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")), {host})
        return base + "?" + parsed.query


def _form_context(node):
    # Options describing the person filling out a form are not its recipient.
    return clean(
        " ".join(
            child if isinstance(child, str) else _form_context(child)
            for child in node.children
            if isinstance(child, str) or child.tag not in {"select", "option"}
        )
    )


def _form_options(node, nodes):
    choices = []
    for select in (n for n in node.descendants() if n.tag == "select"):
        label = next(
            (
                n.text()
                for n in nodes
                if n.tag == "label"
                and n.attrs.get("for") == select.attrs.get("id")
                and select.attrs.get("id")
            ),
            "",
        )
        if not label and select.parent and select.parent.tag == "label":
            label = clean(" ".join(c for c in select.parent.children if isinstance(c, str)))
        label = clean(label)[:120] or "Routing option"
        if re.search(
            r"\b(?:your role|job title|country|region|language|company size|frequency)\b",
            label,
            re.I,
        ):
            continue
        for option in select.descendants():
            if option.tag != "option" or "disabled" in option.attrs:
                continue
            text = option.text()[:180]
            if (
                not text
                or option.attrs.get("value") == ""
                or re.match(r"^(?:please )?(?:select|choose)(?:\b|[ .-])", text, re.I)
            ):
                continue
            purpose, _ = purpose_role(text)
            entry = {"label": text, "purpose": purpose, "field_label": label}
            if entry not in choices:
                choices.append(entry)
            if len(choices) >= 30:
                return choices
    return choices


def _published_route(target, original, label, hosts, *, partial=False, purpose=None):
    purpose = purpose or purpose_role(label)[0]
    if purpose in NONROUTINE or re.search(
        r"\b(?:customer (?:login|sign[- ]?in|service|support)|general (?:contact|inquiries|enquiries)|privacy policy|demos?|webinars?|white papers?|case stud(?:y|ies)|sales|product tours?|videos?)\b",
        label + " " + unquote(urlsplit(target).path).replace("-", " ").replace("_", " "),
        re.I,
    ):
        return None
    if purpose == "security" and not re.search(
        r"\b(?:report(?:ing)?|disclos(?:e|ure)|contact|support|PSIRT|CSIRT|incident response|security (?:portal|site|center|centre|team)|dedicated[^.]{0,40}security)\b",
        label,
        re.I,
    ):
        return None
    if purpose not in {"security", "it", "product_support"}:
        # A security portal is a useful published lead, not a verified recipient.
        if score_link(target, label) < 100 or not re.search(
            r"\b(?:security (?:portal|site|center|centre)|dedicated[^.]{0,40}security|trust (?:portal|center|centre))\b",
            label,
            re.I,
        ):
            return None
        purpose = "security"
    item = candidate("form", target, label or target, purpose=purpose)
    item.update(
        route_type="published_link",
        routing_label=label[:240] or "Published reporting route",
        original_url=original,
        external_destination=urlsplit(target).hostname not in hosts,
        requires_review=True,
        review_reason="Published by the source page; destination suitability and acceptance have not been verified.",
    )
    if partial:
        item["partial_source"] = True
    return item


def parse_html(text, url, hosts, *, partial=False):
    document = Document(text)
    nodes = list(document.root.descendants())
    titles = [n.text() for n in nodes if n.tag == "title"]
    candidates, links = [], []
    seen = set()

    def add(kind, value, node):
        if len(candidates) >= 100:
            return
        block, context = context_for(node, complete_only=partial)
        if not context:
            context = value
        if re.search(
            r"(?:website|web|site) (?:design|develop|by)|designed by|powered by", context, re.I
        ):
            return
        if kind == "phone" and fax_number(value, context, node.text()):
            return
        signature = (kind, value, context)
        if signature in seen:
            return
        seen.add(signature)
        broad = (
            block.tag in {"body", "header"}
            or len(context) >= 1500
            or any(
                n.tag in {"main", "nav", "aside", "footer", "header", "section", "article"}
                for n in block.descendants()
            )
        )
        name, role = ("", "") if broad else _local_identity(block, context)
        excerpt = excerpt_for(context, value)
        classification_context = excerpt
        if kind == "email" and value in context:
            matches = list(EMAIL.finditer(context))
            prior = [match.end() for match in matches if match.end() <= context.find(value)]
            if len(matches) > 1:
                classification_context = context[
                    max(prior, default=0) : context.find(value) + len(value)
                ]
                name, role = "", ""
        purpose, local_role = purpose_role(classification_context)
        if broad:
            purpose, local_role = "general", ""
        restricted = kind == "email" and restricted_mailbox(value)
        if restricted:
            purpose, local_role = "hr", ""
        item = candidate(kind, value, excerpt, name=name, role=role or local_role, purpose=purpose)
        if restricted:
            item["routing_label"] = "Recruiting / employment address"
        if not role and not local_role:
            item["role"] = ""
        if partial:
            item["partial_source"] = True
        candidates.append(item)
        return item

    for node in nodes:
        href = node.attrs.get("href", "") or ""
        complete = not partial or captured_element(node)
        if node.tag == "a" and href and complete:
            if href.lower().startswith("mailto:"):
                for email in EMAIL.findall(unquote(href[7:].split("?", 1)[0])):
                    add("email", email, node)
            elif href.lower().startswith("tel:"):
                value = clean(unquote(href[4:]))
                if (
                    re.fullmatch(r"[+\d(). /-]+(?:(?:;ext=|\s*(?:ext\.?|x)\s*)\d+)?", value, re.I)
                    and 7 <= len(re.sub(r"\D", "", value)) <= 23
                ):
                    add("phone", value.replace(";ext=", " ext. "), node)
            else:
                visible_label = clean(node.text())[:300]
                accessible_label = clean(node.attrs.get("aria-label", ""))[:300]
                label = (
                    clean(accessible_label + " " + visible_label)[:600]
                    if accessible_label and accessible_label != visible_label
                    else visible_label or accessible_label
                )
                original = urljoin(url, href)
                try:
                    destination = review_url(original)
                except DiscoveryError, ValueError:
                    continue
                route = _published_route(destination, original, label, hosts, partial=partial)
                if route and len(candidates) < 100:
                    signature = (route["kind"], route["value"], route["routing_label"])
                    if signature not in seen:
                        seen.add(signature)
                        candidates.append(route)
                try:
                    linked = approved_url(original, hosts)
                except DiscoveryError:
                    continue
                if len(links) < 1000 and (linked, label) not in links:
                    links.append((linked, label))
        if node.tag == "form" and complete:
            context = node.text()
            choices = _form_options(node, [n for n in nodes if not partial or captured_element(n)])
            if re.search(
                r"\b(?:contact|message|inquiry|enquiry|support|security)\b", context, re.I
            ) or any(
                option["purpose"] in {"security", "it", "product_support"} for option in choices
            ):
                item = add("form", url, node)
                if item:
                    form_purpose = purpose_role(_form_context(node))[0]
                    item.update(
                        route_type="form",
                        routing_options=choices,
                        purpose=form_purpose,
                        name="",
                        role="",
                        recommended_for_outreach=form_purpose not in NONROUTINE,
                    )
                    if len(choices) >= 30:
                        document.limited = True
                    if choices:
                        selected = min(
                            choices, key=lambda option: PURPOSE_PRIORITY.get(option["purpose"], 5)
                        )
                        item["purpose"] = selected["purpose"]
                        item["routing_label"] = selected["field_label"] + ": " + selected["label"]
                        item["recommended_for_outreach"] = item["purpose"] not in NONROUTINE
        # Scan only direct visible text, preventing parent blocks from leaking
        # another card's name, role or purpose into this contact.
        for child in node.children if complete else []:
            if len(candidates) >= 100:
                break
            if not isinstance(child, str):
                continue
            for email in EMAIL.findall(child):
                add("email", email, node)
            for match in PHONE.finditer(child):
                value = clean(match.group(0))
                if not (7 <= len(re.sub(r"\D", "", value)) <= 23):
                    continue
                if value.startswith(("+", "(")) or re.search(
                    r"\b(?:phone|telephone|tel|call|mobile|fax|emergency|hotline)\b",
                    child[: match.start()],
                    re.I,
                ):
                    add("phone", value, node)
    # HTML fragments can have direct text under the synthetic body node.
    for child in [] if partial else document.root.children:
        if len(candidates) >= 100:
            break
        if isinstance(child, str):
            for email in EMAIL.findall(child):
                add("email", email, document.root)
    return {
        "title": titles[0][:200] if titles else "",
        "candidates": candidates,
        "links": links,
        "limited": document.limited or len(candidates) >= 100 or len(links) >= 1000,
        "render_required": bool(
            document.script_count
            and len(document.root.text()) < 250
            and (
                document.javascript_notice
                or any(
                    n.attrs.get("id", "").lower() in {"root", "app", "__next", "app-root"}
                    and len(n.text()) < 40
                    for n in nodes
                )
            )
        ),
    }


def parse_security(text, url, hosts, now=None):
    fields = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        name, value = line.split(":", 1)
        fields.setdefault(name.strip().lower(), []).append(value.strip())
    issues = []
    valid = True
    expires = fields.get("expires", [])
    try:
        if len(expires) != 1:
            raise ValueError()
        expiry = datetime.fromisoformat(expires[0].replace("Z", "+00:00"))
        if expiry.tzinfo is None or expiry <= (now or datetime.now(timezone.utc)):
            raise ValueError()
    except ValueError, TypeError:
        valid = False
        issues.append(
            {
                "code": "security_expiry",
                "message": "security.txt is expired or lacks one valid expiration date; contact suitability requires review.",
                "url": url,
            }
        )
    canonical = fields.get("canonical", [])
    if canonical:
        try:
            normalized = [approved_url(x, hosts) for x in canonical]
            if url not in normalized:
                raise ValueError()
        except ValueError, DiscoveryError:
            valid = False
            issues.append(
                {
                    "code": "security_canonical",
                    "message": "security.txt canonical scope does not match this retrieval URL; review required.",
                    "url": url,
                }
            )
    contacts = []
    for value in fields.get("contact", [])[:50]:
        if value.lower().startswith("mailto:"):
            emails = EMAIL.findall(unquote(value[7:].split("?", 1)[0]))
            for email in emails:
                contacts.append(
                    candidate(
                        "email",
                        email,
                        "Contact: " + value,
                        purpose="security" if valid else "other",
                    )
                )
        elif value.lower().startswith("https://"):
            try:
                target = review_url(value)
            except DiscoveryError, ValueError:
                issues.append(
                    {
                        "code": "security_invalid_contact",
                        "message": "A security.txt Contact URL was malformed or unsupported; it was not followed.",
                        "url": url,
                    }
                )
                continue
            item = candidate(
                "form", target, "Contact: " + value, purpose="security" if valid else "other"
            )
            item.update(
                route_type="published_link",
                routing_label="security.txt Contact",
                original_url=value,
                external_destination=urlsplit(target).hostname not in hosts,
                requires_review=True,
                review_reason="Published security.txt destination; suitability and acceptance require review.",
            )
            contacts.append(item)
            if item["external_destination"]:
                issues.append(
                    {
                        "code": "security_external_contact",
                        "message": "An externally hosted security contact URL was retained as a reviewable published route; it was not followed.",
                        "url": url,
                    }
                )
    if not fields.get("contact"):
        issues.append(
            {
                "code": "security_no_contact",
                "message": "security.txt has no supported Contact field.",
                "url": url,
            }
        )
    if len(fields.get("contact", [])) > 50:
        issues.append(
            {
                "code": "security_contact_limit",
                "message": "Additional security.txt Contact fields were omitted at the extraction limit.",
                "url": url,
            }
        )
    return {"title": "security.txt", "candidates": contacts, "links": [], "issues": issues}


def score_link(url, label):
    path = urlsplit(url).path.lower()
    extension = path.rsplit("/", 1)[-1].rsplit(".", 1)
    if len(extension) == 2 and extension[1] not in {"html", "htm", "php", "asp", "aspx"}:
        return 0
    text = unquote(path).replace("-", " ").replace("_", " ") + " " + label.lower()
    if re.search(
        r"(?:responsible|coordinated) disclosure|vulnerability (?:report|disclosure)|report (?:a )?(?:security|cybersecurity|vulnerability)|PSIRT|CSIRT",
        text,
        re.I,
    ):
        return 140
    if re.search(
        r"\b(?:careers?|jobs?|recruit|admissions|patients?|dialysis|telehealth|team members?|our people|culture|staff professionals)\b",
        text,
        re.I,
    ):
        return 0
    if re.search(r"/(?:blog|news|articles?|resources)/", path):
        return 0
    if re.search(
        r"/(?:[^/]*[-_])?(?:press|media|investor|privacy)(?:[-_/]|$)|\b(?:media inquiries|press inquiries|investor relations|privacy policy)\b",
        path + " " + label.lower(),
    ):
        return 0
    # Directory landing pages remain a low-priority fallback. Individual bios
    # and unrelated about subpages do not consume the limited contact budget.
    if re.search(r"/(?:leadership|leaders|team|people|management|board|directors)/[^/]+", path):
        return 0
    if re.search(r"\b(?:security|trust) (?:portal|center|centre|site)\b", text, re.I):
        return 125
    destination = path.rstrip("/").rsplit("/", 1)[-1]
    if destination in {
        "support",
        "help",
        "help-center",
        "support-center",
        "customer-support",
        "technical-support",
    }:
        return 105
    if destination == "trust":
        return 115
    scores = {
        # Product security pages and advisories often describe a feature, not
        # a reporting channel. Explicit portals/disclosure routes rank above
        # them; the bounded lookup can still reach a useful support page.
        "security": 85,
        "webmaster": 105,
        "technical support": 105,
        "trust": 20,
        "support": 20,
    }
    score = max(
        (
            score
            for keyword, score in scores.items()
            if re.search(r"(?:^|[^a-z])" + keyword + r"(?:[^a-z]|$)", text)
        ),
        default=0,
    )
    if score:
        return score
    if re.search(r"\bcontact(?: us)?\b", label, re.I) or destination in {
        "contact",
        "contact-us",
        "contactus",
        "contacts",
        "contact.html",
        "contact.aspx",
    }:
        return 95
    return {
        "team": 35,
        "our-team": 35,
        "leadership": 30,
        "management": 30,
        "about": 25,
        "about-us": 25,
        "company": 25,
    }.get(destination, 0)
