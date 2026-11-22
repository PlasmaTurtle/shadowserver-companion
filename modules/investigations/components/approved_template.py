"""Approved report wording. Only bracketed values in NARRATIVE are substituted.

Provenance: user's finished six-page report (pages 2, 5, 6), with the
Introduction and finding narrative superseded by the user's builder screenshot.
No source lookup or generative rewriting occurs here.
"""
from collections import OrderedDict
from datetime import date
import hashlib
import re

REVISION = 'approved-2026-11-06-v1'
ADDRESSEE_REVISION = 'addressee-2026-11-08-v2'
ADDRESSEE = 'Principal Executive / IT Director'
LEGACY_ADDRESSEE = 'Principle Executive / IT Director'
SUBJECT = 'Shadowserver - Cybersecurity Vulnerability Notification'
INTRO = ('The United States Secret Service, Charlotte Field Office, is reaching out to notify you of a potential cybersecurity vulnerability associated with the information listed below. '
         'This notification is part of our ongoing effort to help organizations safeguard their infrastructure and prevent cyber incidents. '
         'The underlying data was provided by the Shadowserver Foundation, a nonprofit security organization that monitors the global internet for malicious activity and vulnerabilities. '
         'Please let us know if you have any questions.')
NARRATIVE = ("On [TODAY'S DATE], the United States Secret service, Charlotte Cyber Fraud Task Force, received a Shadowserver Notification related to a critical security finding detected on [ASSET IP's]. "
             'The reported services were accessible over [ASSET PROTOCOL][ASSET PORT] and are associated with the domain [ASSET HOSTNAME]. '
             'The identified vulnerability is [VULNERABILITIES], which are associated with [ASSET SOFTWARE]. '
             'The reported software version is [ASSET SOFTWARE VERSION], which may fall within the affected ranges of [CVE AFFECTED VERSIONS]. '
             'Open source searches indicate the reported asset is associated with [ORGANIZATION] in [ENTITY CITY],[ENTITY STATE]. '
             'If confirmed, remediation should be prioritized in accordance with critical vulnerability handling procedures.')
ATTRIBUTION = ('This notification is based on an internet-facing system identified in a Shadowserver report. Before notifying your organization, we reviewed publicly available information, such as domain registration, DNS records, internet-routing data, business websites, and other open-source information, to associate the reported IP address, hostname, or service with your organization. Public-facing systems may be hosted, managed, or shared by a third party. Please validate that the identified asset belongs to your organization or an authorized service provider and confirm responsibility for remediation. This notification does not by itself establish ownership, vulnerability, or compromise.')
SECURITY_INTRO = ('As part of our mission to protect local businesses and the financial infrastructure of the Carolinas, the Secret Service provides this voluntary advisory. We suggest your technical team consider the following protective measures:')
NEXT_STEPS = ("Validate the Asset and Finding: Verify if the reported IP address, hostname, or service is associated with your organization's digital footprint, and confirm whether the reported software version, configuration, or end-of-life condition is currently active.\n"
              'Mitigate Exposure: Consider applying vendor-recommended patches, updating configurations, or implementing temporary mitigations. Evaluating whether public internet access is strictly necessary for the identified asset can help limit your public-facing attack surface.\n'
              'Coordinate Internally: Share this advisory with your internal IT staff, cybersecurity personnel, system owners, or external managed service providers (MSPs) who manage these assets on your behalf.\n'
              'Review for Indicators of Compromise: If the asset is confirmed to have been exposed, your technical team may wish to review system logs and security alerts for unusual activity. Common indicators to monitor include unfamiliar sign-ins, unexpected configuration changes, unauthorized email-forwarding rules, or unusual outbound network traffic.')
FRAUD_INTRO = 'Securing public-facing infrastructure is a critical defense against cyber-enabled financial crimes. Malicious actors frequently exploit these exposures to gain unauthorized access, which can lead to severe operational and financial impacts, including:'
FRAUD_RISKS = ['Business Email Compromise (BEC): Unauthorized access to email systems to intercept communications and divert legitimate payments (such as wire transfers or ACH payments) to fraudulent accounts.',
               'Ransomware & Extortion: Encryption of vital business data, operational halting, and demands for payment.']
FRAUD_STATS_INTRO = 'To assist organizations in assessing risk priorities, the FBI Internet Crime Complaint Center (IC3) highlights the impact of these threats across the private sector. In 2025, the IC3 received:'
# These are the user's supplied template figures, not refreshed live statistics.
FRAUD_STATS = ['Business Email Compromise (BEC): 24,768 complaints resulting in over $3.0 billion in reported losses (averaging approximately $123,000 per complaint).',
               'Ransomware: 3,611 complaints reporting more than $32 million in direct losses (not including indirect costs such as business interruption or system recovery).']
PARTNERSHIP = 'This notification is provided strictly as a voluntary, non-regulatory information-sharing initiative. This outreach does not constitute a legal directive, a formal audit, or a determination of regulatory compliance. The information reflects technical observations captured at a specific point in time and is shared solely to help your organization make informed risk-management decisions and protect against cyber-enabled financial fraud.'
RESPONSIBILITY = 'The United States Secret Service personnel are not authorized to access or modify your systems. Remediation decisions and actions are the responsibility of your organization. This notification is provided for informational purposes only and does not constitute a requirement or mandate for remediation. The United States Secret Service is not liable for any actions taken or not taken by your organization in response to this notification.'
CLOSING = 'Thank you for your attention to this matter.'
RESOURCES = '\n'.join(['https://www.cisa.gov/resources-tools/resources/free-cybersecurity-services-and-tools',
 'https://www.cisa.gov/news-events/news/traffic-light-protocol-tlp-definitions-and-usage',
 'https://www.cisa.gov/known-exploited-vulnerabilities-catalog',
 'https://www.shadowserver.org/what-we-do/network-reporting/get-reports/',
 'https://www.secretservice.gov/investigations/cyberincident', 'https://nvd.nist.gov/',
 'https://cve.org/', 'https://www.cvedetails.com/'])
SYSTEM_BLOCKS = {'attribution', 'financial_crime', 'responsibility', 'eol', 'cve'}
CVE = re.compile(r'CVE-\d{4}-\d{4,}', re.I)
TOKENS = re.compile(r'\[([^\]]+)\]')


def entity_profile(lead):
    return lead.get('entity_profile', {})


def affected_text(records, cves):
    """Display explicit CNA ranges only. No version applicability inference."""
    values = []
    for record in records:
        if record.get('id') not in cves or record.get('verification_status') != 'published':
            continue
        for product in record.get('affected', []):
            for version in product.get('versions', []):
                if version.get('status') != 'affected':
                    continue
                value = str(version.get('version', ''))
                if not value:
                    continue
                if version.get('lessThan'):
                    value += ' to before ' + str(version['lessThan'])
                elif version.get('lessThanOrEqual'):
                    value += ' through ' + str(version['lessThanOrEqual'])
                if version.get('changes'):
                    value += ' (status changes: ' + '; '.join(str(c.get('at', '')) + ': ' + str(c.get('status', '')) for c in version['changes']) + ')'
                values.append(record['id'] + ' — ' + str(product.get('product', '')) + ' ' + value)
    return '; '.join(dict.fromkeys(values))


def narrative_groups(lead, draft):
    """Group identical findings, retaining IP ↔ host ↔ service ↔ version association."""
    groups = OrderedDict()
    dispositions = draft.get('cve_dispositions', {})
    for entry in lead['entries']:
        f = entry['source']['fields']
        key_values = [str(f.get(k, '') or '') for k in ('hostname', 'protocol', 'port', 'tag', 'version')]
        key = hashlib.sha256('\0'.join(key_values).encode()).hexdigest()[:16]
        group = groups.setdefault(key, {'key': key, 'hostname': key_values[0], 'protocol': key_values[1],
              'port': key_values[2], 'tag': key_values[3], 'version': key_values[4], 'ips': [],
              'software': str(f.get('product') or f.get('application') or f.get('software') or '')})
        if entry['ip'] not in group['ips']:
            group['ips'].append(entry['ip'])
    for group in groups.values():
        all_cves = CVE.findall(group['tag'].upper())
        group['cves'] = list(dict.fromkeys(c for c in all_cves if dispositions.get(c, {}).get('action') != 'exclude'))
        # Excluded identifiers are kept in the asset inventory, not asserted in prose.
        if all_cves and not group['cves']:
            group['excluded'] = True
        if not group['software']:
            match = re.match(r'^(.+?)[ /_-]+v?\d', group['version'])
            if match:
                group['software'] = match[1]
            else:
                tokens = [x.strip() for x in re.split(r'[;,]', group['tag']) if x.strip()]
                group['software'] = next((x.removeprefix('eol-') for x in tokens if not CVE.fullmatch(x) and x.lower() not in ('eol', 'ssl', 'http', 'https', 'http-redirect', 'tcp', 'udp')), '')
        group['affected_versions'] = affected_text(draft.get('cve_records', []), group['cves'])
        override = draft.get('narrative_values', {}).get(group['key'], {})
        group.update({k: v for k, v in override.items() if k in ('software', 'affected_versions') and v.strip()})
    return list(groups.values())


def generate_narrative(lead, draft):
    profile = entity_profile(lead)
    stamp = date.fromisoformat(draft['report_date'])
    human_date = stamp.strftime('%B') + f' {stamp.day}, {stamp.year}'
    paragraphs = []
    for group in narrative_groups(lead, draft):
        if group.get('excluded'):
            continue
        values = {
            "TODAY'S DATE": human_date, "ASSET IP's": ', '.join(group['ips']),
            'ASSET PROTOCOL': (group['protocol'] or 'protocol not reported') + ' ',
            'ASSET PORT': group['port'] or 'port not reported',
            'ASSET HOSTNAME': group['hostname'],
            'VULNERABILITIES': ', '.join(group['cves']) or group['tag'],
            'ASSET SOFTWARE': group['software'] or 'software not identified in the source record',
            'ASSET SOFTWARE VERSION': group['version'] or 'not supplied in the source record',
            'CVE AFFECTED VERSIONS': group['affected_versions'] or ('not supplied in the selected source' if group['cves'] else 'not applicable; no CVE reported'),
            'ORGANIZATION': draft.get('company') or lead['company'] or lead['domain'],
            'ENTITY CITY': profile.get('city') or 'city not recorded',
            'ENTITY STATE': ' ' + (profile.get('state') or 'state not recorded'),
        }
        paragraphs.append(TOKENS.sub(lambda m: str(values[m.group(1)]), NARRATIVE))
    return '\n\n'.join(paragraphs)


def apply_template(lead, draft, settings):
    """Authoritative fields are computed on the server, never trusted from a form."""
    profile = entity_profile(lead)
    draft.update(template_revision=REVISION, subject=SUBJECT, intro=INTRO,
        contact_name=ADDRESSEE if draft.get('addressee_revision') == ADDRESSEE_REVISION else LEGACY_ADDRESSEE, contact_title='', contact_email='',
        sender_name=settings['analyst_name'], sender_title=settings['analyst_title'],
        company=lead['company'] or lead['domain'], address=profile.get('address', draft.get('address', '')),
        recommendations=NEXT_STEPS, limitations=PARTNERSHIP, resources=RESOURCES, closing=CLOSING)
    draft['report_template'] = {**draft.get('report_template', {}), 'id':'standard', 'version':2}
    draft['narrative'] = generate_narrative(lead, draft)
    return draft
