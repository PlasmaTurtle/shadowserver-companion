"""Versioned technical explanations for source-scoped findings."""

from hashlib import sha256

BANK = {
    "http_eol_component": {
        "format": "snippet",
        "title": "Reported component past its support period",
        "body": "The source reports an end-of-life condition for a software "
        "component or device associated with this web endpoint. A "
        "component that no longer receives security maintenance can retain "
        "weaknesses for which the original supplier no longer provides "
        "fixes.",
        "limitations": "This concerns the reported component, not the HTTP "
        "protocol itself. The tag alone does not identify an "
        "applicable CVE or establish compromise; some maintained "
        "vendor packages receive backported fixes without changing "
        "the upstream version number.",
        "review": "Confirm the product, installed build, maintenance provider and "
        "support status against the supplier's lifecycle and security "
        "information. Assess a supported replacement or other documented "
        "protective measures.",
        "id": "http_eol_component",
        "revision": "finding-explainers-2026-11-10-v1",
        "category": "lifecycle",
        "match_rules": [
            {
                "report_types": ["scan_http_vulnerable", "scan6_http_vulnerable"],
                "tags": ["eol"],
                "tag_prefixes": ["eol-"],
                "exclude_tags": ["eol-php", "eol-iis", "eos-iis", "eol-exchange"],
            }
        ],
        "sources": [
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Vulnerable HTTP Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/vulnerable-http-report/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "record": {
                    "summary": "HTTP report lifecycle observations use "
                    "eol or eol-prefixed tags; a reported "
                    "component is not the HTTP protocol."
                },
                "revision_id": "finding-explainers-2026-11-10-v1-5ce6d5026c30",
                "partition": "C",
                "referenced_by": ["EX-VULNERABILITY"],
                "capture_method": "Reviewed technical reference extract; not the full source.",
            },
            {
                "publisher": "National Institute of Standards and Technology",
                "title": "SP 800-53 Rev. 5, Control SA-22: Unsupported System Components",
                "public_url": "https://csrc.nist.gov/CSRC/media/Projects/risk-management/800-53%20Downloads/800-53r5/SP_800-53_v5_1-derived-OSCAL.pdf",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "record": {
                    "summary": "SA-22 discusses support availability, "
                    "security patching, alternative "
                    "maintenance sources and risk controls "
                    "for unsupported components. Used as "
                    "technical context, not as a compliance "
                    "requirement imposed on the recipient."
                },
                "revision_id": "finding-explainers-2026-11-10-v1-c9b9e3fa9341",
                "partition": "C",
                "referenced_by": ["EX-VULNERABILITY"],
                "capture_method": "Reviewed technical reference extract; not the full source.",
            },
            {
                "publisher": "Red Hat",
                "title": "Backporting Security Fixes",
                "public_url": "https://access.redhat.com/security/updates/backporting",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "record": {
                    "summary": "Vendor packages may include security "
                    "fixes backported to an older upstream "
                    "version. Version-number-only "
                    "vulnerability assessments can be false "
                    "positives."
                },
                "revision_id": "finding-explainers-2026-11-10-v1-d1d51c708132",
                "partition": "C",
                "referenced_by": ["EX-VULNERABILITY"],
                "capture_method": "Reviewed technical reference extract; not the full source.",
            },
        ],
        "keep_tags_separate": True,
    },
    "http_eol_php": {
        "format": "snippet",
        "title": "PHP branch past upstream support",
        "body": "The eol-php tag reports a lifecycle concern for PHP, the software that "
        "runs application code on the server. A branch past the PHP project's "
        "support period no longer receives routine project fixes, which can "
        "leave security weaknesses unaddressed.",
        "limitations": "The observed version alone does not establish whether a "
        "distribution or support provider maintains a patched build. It "
        "also does not prove that a particular CVE applies.",
        "review": "Confirm the installed PHP branch and vendor package, applicable "
        "security updates and support coverage. Review compatibility and a "
        "move to a maintained branch with the application or hosting provider.",
        "id": "http_eol_php",
        "revision": "finding-explainers-2026-11-10-v1",
        "category": "lifecycle",
        "match_rules": [
            {"report_types": ["scan_http_vulnerable", "scan6_http_vulnerable"], "tags": ["eol-php"]}
        ],
        "sources": [
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Vulnerable HTTP Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/vulnerable-http-report/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "record": {
                    "summary": "The eol-php tag identifies a reported PHP lifecycle condition."
                },
                "revision_id": "finding-explainers-2026-11-10-v1-5ce6d5026c30",
                "partition": "C",
                "referenced_by": ["EX-VULNERABILITY"],
                "capture_method": "Reviewed technical reference extract; not the full source.",
            },
            {
                "publisher": "The PHP Group",
                "title": "Supported Versions",
                "public_url": "https://www.php.net/supported-versions.php",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "record": {
                    "summary": "The PHP project distinguishes active "
                    "support, security-only support and end of "
                    "life."
                },
                "revision_id": "finding-explainers-2026-11-10-v1-3297a096d124",
                "partition": "C",
                "referenced_by": ["EX-VULNERABILITY"],
                "capture_method": "Reviewed technical reference extract; not the full source.",
            },
            {
                "publisher": "The PHP Group",
                "title": "Unsupported Branches",
                "public_url": "https://www.php.net/eol.php",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "record": {
                    "summary": "Lists unsupported PHP branches and their "
                    "end-of-life dates. No hard-coded version "
                    "threshold or individual CVE inference is "
                    "made by this snippet."
                },
                "revision_id": "finding-explainers-2026-11-10-v1-86310d8814c5",
                "partition": "C",
                "referenced_by": ["EX-VULNERABILITY"],
                "capture_method": "Reviewed technical reference extract; not the full source.",
            },
            {
                "publisher": "Red Hat",
                "title": "Backporting Security Fixes",
                "public_url": "https://access.redhat.com/security/updates/backporting",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "record": {
                    "summary": "A distribution's older upstream PHP version "
                    "may contain vendor-backported security "
                    "fixes; confirm package and advisory "
                    "history."
                },
                "revision_id": "finding-explainers-2026-11-10-v1-d1d51c708132",
                "partition": "C",
                "referenced_by": ["EX-VULNERABILITY"],
                "capture_method": "Reviewed technical reference extract; not the full source.",
            },
        ],
    },
    "http_iis_support": {
        "format": "snippet",
        "title": "IIS and Windows support status",
        "body": "IIS is a Windows component whose support follows the host operating "
        "system. Shadowserver uses eol-iis for a lifecycle concern and "
        "eos-iis for systems it assesses as beyond the Extended Security "
        "Update period as well; without applicable security updates, "
        "weaknesses may remain unpatched.",
        "limitations": "The IIS version alone does not establish the Windows "
        "edition, servicing channel or effective support coverage. "
        "Neither tag identifies a particular exploitable CVE or "
        "proves intrusion.",
        "review": "Confirm the Windows edition and build, installed updates and any "
        "applicable extended-security coverage. Compare the source "
        "observation with Microsoft's lifecycle information and assess a "
        "supported migration.",
        "id": "http_iis_support",
        "revision": "finding-explainers-2026-11-10-v1",
        "category": "lifecycle",
        "match_rules": [
            {
                "report_types": ["scan_http_vulnerable", "scan6_http_vulnerable"],
                "tags": ["eol-iis", "eos-iis"],
            }
        ],
        "sources": [
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Vulnerable HTTP Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/vulnerable-http-report/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "record": {
                    "summary": "The source distinguishes eol-iis from "
                    "eos-iis; eos-iis additionally signifies "
                    "an assessment beyond the Extended "
                    "Security Update cycle."
                },
                "revision_id": "finding-explainers-2026-11-10-v1-5ce6d5026c30",
                "partition": "C",
                "referenced_by": ["EX-VULNERABILITY"],
                "capture_method": "Reviewed technical reference extract; not the full source.",
            },
            {
                "publisher": "Microsoft",
                "title": "Internet Information Services (IIS) - Microsoft Lifecycle",
                "public_url": "https://learn.microsoft.com/en-us/lifecycle/products/internet-information-services-iis",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "record": {
                    "summary": "IIS follows the host Windows "
                    "operating-system lifecycle. Identical "
                    "IIS major versions occur on Windows "
                    "releases with different support dates."
                },
                "revision_id": "finding-explainers-2026-11-10-v1-c04f2d695a05",
                "partition": "C",
                "referenced_by": ["EX-VULNERABILITY"],
                "capture_method": "Reviewed technical reference extract; not the full source.",
            },
            {
                "publisher": "Microsoft",
                "title": "Product Lifecycle FAQ - Extended Security Updates",
                "public_url": "https://learn.microsoft.com/en-us/lifecycle/faq/extended-security-updates",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "record": {
                    "summary": "Extended Security Updates supply defined "
                    "security fixes for eligible products "
                    "beyond ordinary support; entitlement and "
                    "period must be checked for the actual "
                    "deployment."
                },
                "revision_id": "finding-explainers-2026-11-10-v1-e7be22478b8f",
                "partition": "C",
                "referenced_by": ["EX-VULNERABILITY"],
                "capture_method": "Reviewed technical reference extract; not the full source.",
            },
        ],
    },
    "exchange-eol": {
        "format": "snippet",
        "title": "End-of-life Microsoft Exchange",
        "body": "Shadowserver's end-of-life tag flags an Exchange release as beyond its "
        "usual support period. Continued operation without applicable security "
        "maintenance can leave newly discovered weaknesses uncorrected in "
        "business email infrastructure.",
        "limitations": "A scan's version label does not establish the installed "
        "security-update level, eligibility for an extended update "
        "program, or any particular CVE. This finding alone does not "
        "demonstrate compromise.",
        "review": "Confirm the installed Exchange build and Security/Hotfix Updates "
        "using Microsoft's build guidance. Check the release's support "
        "lifecycle and any documented, current entitlement to security "
        "updates; evaluate a supported upgrade or migration and interim "
        "exposure controls with the email administrator.",
        "id": "exchange-eol",
        "revision": "finding-explainers-2026-11-10-v1",
        "category": "lifecycle",
        "match_rules": [
            {"report_types": ["scan_exchange", "scan6_exchange"], "tags": ["eol"]},
            {
                "report_types": ["scan_http_vulnerable", "scan6_http_vulnerable"],
                "tags": ["eol-exchange"],
            },
        ],
        "sources": [
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Vulnerable Exchange Server Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/vulnerable-exchange-server-report/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "record": {
                    "summary": "The Exchange report uses the eol tag for "
                    "older Exchange releases; most assessments "
                    "use observed version information."
                },
                "revision_id": "finding-explainers-2026-11-10-v1-bb860b73c279",
                "partition": "C",
                "referenced_by": ["EX-VULNERABILITY"],
                "capture_method": "Reviewed technical reference extract; not the full source.",
            },
            {
                "publisher": "Microsoft",
                "title": "Exchange Server supportability matrix",
                "public_url": "https://learn.microsoft.com/en-us/exchange/plan-and-deploy/supportability-matrix",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "record": {
                    "summary": "Microsoft identifies supported Exchange "
                    "versions and configurations; Exchange 2016 "
                    "and 2019 reached end of support in October "
                    "2025."
                },
                "revision_id": "finding-explainers-2026-11-10-v1-e026824644ac",
                "partition": "C",
                "referenced_by": ["EX-VULNERABILITY"],
                "capture_method": "Reviewed technical reference extract; not the full source.",
            },
            {
                "publisher": "Microsoft",
                "title": "Exchange Server build numbers and release dates",
                "public_url": "https://learn.microsoft.com/en-us/exchange/new-features/build-numbers-and-release-dates",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "record": {
                    "summary": "Provides methods to verify installed "
                    "Exchange builds and security/hotfix updates. "
                    "Enrolled Exchange 2016/2019 ESU customers "
                    "can receive specified post-support security "
                    "updates."
                },
                "revision_id": "finding-explainers-2026-11-10-v1-81ec7b824478",
                "partition": "C",
                "referenced_by": ["EX-VULNERABILITY"],
                "capture_method": "Reviewed technical reference extract; not the full source.",
            },
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Vulnerable HTTP Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/vulnerable-http-report/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "record": {
                    "summary": "The vulnerable HTTP report documents the "
                    "exact eol-exchange tag among its end-of-life "
                    "product observations."
                },
                "revision_id": "finding-explainers-2026-11-10-v1-5ce6d5026c30",
                "partition": "C",
                "referenced_by": ["EX-VULNERABILITY"],
                "capture_method": "Reviewed technical reference extract; not the full source.",
            },
        ],
    },
}

# These extracts describe public report definitions and operator guidance. A case pins
# the selected text and sources together when it adopts this edition of the bank.
LIFECYCLE_EDITION = "finding-explainers-2026-11-10-v1"
PREVIOUS_EDITION = "finding-explainers-2026-11-22-v1"
CURRENT_EDITION = "finding-explainers-2026-11-22-v2"


def _reference(publisher, title, url, summary, *, edition=PREVIOUS_EDITION):
    digest = sha256((url + "\n" + summary).encode("utf-8")).hexdigest()[:12]
    return {
        "publisher": publisher,
        "title": title,
        "public_url": url,
        "retrieved_at": "2026-11-22T00:00:00Z",
        "record": {"summary": summary},
        "revision_id": f"{edition}-{digest}",
        "partition": "C",
        "referenced_by": ["EX-VULNERABILITY"],
        "capture_method": "Reviewed technical reference extract; not the full source.",
    }


def _report_reference(title, slug, summary):
    return _reference(
        "The Shadowserver Foundation",
        title,
        "https://www.shadowserver.org/what-we-do/network-reporting/" + slug + "/",
        summary,
    )


def _condition(
    identifier,
    *,
    title,
    category,
    family,
    tags,
    body,
    limitations,
    review,
    sources,
    fields=None,
):
    rule = {"report_types": ["scan_" + family, "scan6_" + family], "tags": tags}
    if fields:
        rule["fields"] = fields
    return {
        "id": identifier,
        "revision": PREVIOUS_EDITION,
        "format": "snippet",
        "category": category,
        "title": title,
        "match_rules": [rule],
        "body": body,
        "limitations": limitations,
        "review": review,
        "sources": sources,
    }


_HTTP_REFERENCE = _report_reference(
    "Vulnerable HTTP Report",
    "vulnerable-http-report",
    "Shadowserver distinguishes Basic authentication on plain HTTP, exposed Git configuration "
    "and two confidence levels for identifying a MegaRAC management interface. The latter "
    "check cannot establish firmware patch status. vcenter-dcerpc-exposed separately records "
    "RPC reachability alongside a vCenter version assessment.",
)

_CONDITIONS = [
    _condition(
        "http_basic_auth",
        title="Basic authentication offered over plain HTTP",
        category="configuration",
        family="http_vulnerable",
        tags=["basic-auth"],
        body="Shadowserver observed an HTTP endpoint requesting Basic authentication without "
        "transport encryption. A client that answers this challenge sends a reversibly encoded "
        "username and password. Anyone able to observe that traffic could recover them.",
        limitations="The challenge shows what the server offered. It does not show that a user "
        "submitted credentials, that anyone intercepted them, or that a login succeeded.",
        review="Check the virtual host and reverse proxy handling this request. Require HTTPS "
        "before sending an authentication challenge. Review access and authentication records "
        "for the exposure period and rotate credentials if their use over plain HTTP is confirmed.",
        sources=[
            _HTTP_REFERENCE,
            _reference(
                "Internet Engineering Task Force",
                "RFC 7617: The 'Basic' HTTP Authentication Scheme",
                "https://www.rfc-editor.org/rfc/rfc7617",
                "Basic authentication encodes the username and password with Base64. Section 4 "
                "requires an external protection mechanism such as TLS for confidentiality.",
            ),
        ],
    ),
    _condition(
        "http_git_config",
        title="Git repository configuration exposed by a web server",
        category="exposure",
        family="http_vulnerable",
        tags=["git-config-file", "git-config-file."],
        body="Shadowserver reports that a public web endpoint returned Git repository "
        "configuration. Other repository files deployed in the same web directory could expose "
        "source code, revision history or credentials.",
        limitations="The observed configuration file does not establish which other files were "
        "available, whether the repository contained a secret, or whether anyone downloaded it.",
        review="Check the deployed web root and build artifact for repository metadata. Remove "
        "that metadata from public deployments and deny web access to it. Review access logs "
        "and repository history to identify credentials that need replacement.",
        sources=[
            _HTTP_REFERENCE,
            _reference(
                "Swiss National Cyber Security Centre",
                "Unprotected .git folders on the internet pose a security risk",
                "https://www.bacs.admin.ch/en/git-en",
                "Git metadata can disclose source code, historical changes and embedded secrets. "
                "The NCSC recommends preventing web access to Git directories and keeping secrets "
                "out of source control.",
            ),
        ],
    ),
    _condition(
        "http_megarac_management",
        title="Public server management interface",
        category="exposure",
        family="http_vulnerable",
        tags=["megarac", "potential-megarac"],
        body="Shadowserver observed a public Redfish management endpoint. Its megarac and "
        "potential-megarac tags express different confidence levels in the identification of "
        "AMI MegaRAC firmware. This interface can provide hardware administration independently "
        "of the host operating system.",
        limitations="A response does not establish the exact controller, firmware revision, "
        "patch status or a successful administrative login. The potential-megarac tag is a "
        "tentative product identification.",
        review="Identify the hardware model and management-controller firmware in the asset "
        "inventory. Compare the installed revision with the hardware supplier's security "
        "updates and restrict management access to a dedicated, trusted network.",
        sources=[
            _HTTP_REFERENCE,
            _reference(
                "National Security Agency and Cybersecurity and Infrastructure Security Agency",
                "Harden Baseboard Management Controllers",
                "https://media.defense.gov/2023/Jun/14/2003241405/-1/-1/0/CSI_HARDEN_BMCS.PDF",
                "The agencies advise isolating management controllers from other network traffic, "
                "restricting administrative access and maintaining controller firmware.",
            ),
        ],
    ),
    _condition(
        "vcenter_dcerpc_exposed",
        title="vCenter RPC service reachable from the internet",
        category="exposure",
        family="http_vulnerable",
        tags=["vcenter-dcerpc-exposed"],
        body="Shadowserver separately reports that the vCenter DCERPC service was reachable "
        "from the internet. The tag adds evidence about access to a management service beyond "
        "what the web interface's software version alone can establish.",
        limitations="Reachability does not establish which operations the service would allow, "
        "whether someone used it without authorization, or the installed patch level. Assess "
        "any accompanying CVE against its own evidence.",
        review="Identify the vCenter appliance, verify its installed build and review the "
        "networks permitted to reach its management services. Restrict access to required "
        "management clients and review the supplier's advisory for any separately reported CVE.",
        sources=[
            _HTTP_REFERENCE,
            _reference(
                "Broadcom",
                "Configure the VAMI firewall to restrict vCenter access to specified IP addresses or subnets",
                "https://knowledge.broadcom.com/external/article/412016/configure-the-vami-firewall-to-restrict.html",
                "Broadcom documents the appliance firewall controls for restricting access to "
                "vCenter Server by source address or subnet.",
            ),
        ],
    ),
    _condition(
        "mongodb_noauth",
        title="MongoDB database names visible without authentication",
        category="configuration",
        family="mongodb",
        tags=["mongodb-noauth"],
        body="Shadowserver reports that the MongoDB service allowed its unauthenticated "
        "database-listing check. The visible_databases field can record up to five returned "
        "names. Database names can reveal which applications use the service.",
        limitations="This observation does not demonstrate document reads, writes or deletion. "
        "It does not identify who accessed the service or establish any separate version-based CVE.",
        review="Check which networks can reach the database and whether the deployment enforces "
        "authentication and least-privilege roles. Restrict client access to trusted networks, "
        "review available database audit records and verify the effective access policy.",
        sources=[
            _report_reference(
                "Open MongoDB Report",
                "open-mongodb-report",
                "The provider distinguishes a reachable MongoDB service from an unauthenticated "
                "database listing. It records up to five database names for a successful listing.",
            ),
            _reference(
                "MongoDB",
                "Security Checklist for Self-Managed Deployments",
                "https://www.mongodb.com/docs/manual/administration/security-checklist/",
                "MongoDB recommends enforcing access control, limiting roles and network access, "
                "and retaining audit records for review.",
            ),
        ],
    ),
    _condition(
        "smtp_exim_21nails",
        title="Exim banner associated with the 21Nails advisory",
        category="version_assessment",
        family="smtp_vulnerable",
        tags=["21nails"],
        body="Shadowserver associated the version advertised by the SMTP service with the "
        "21Nails group of Exim mail-server vulnerabilities. This is a banner-based indication "
        "for the mail administrator to compare with the installed package.",
        limitations="The banner does not identify installed distributor backports or establish "
        "that a particular member of the advisory group applies. It supplies no evidence of "
        "message access or compromise.",
        review="Identify the running Exim package, its distributor and complete package revision. "
        "Compare that revision with the distributor's advisory and install the applicable "
        "security update. Retain the package record when documenting a backported fix.",
        sources=[
            _report_reference(
                "Vulnerable SMTP Report",
                "vulnerable-smtp-report",
                "The provider maps SMTP banner versions to the 21nails tag and warns that banner "
                "information alone can misclassify patched systems.",
            ),
            _reference(
                "Canonical",
                "USN-4934-2: Exim vulnerabilities",
                "https://ubuntu.com/security/notices/USN-4934-2",
                "Ubuntu published distribution-specific Exim security package revisions. The "
                "appropriate fixed package depends on the Ubuntu release and support channel.",
            ),
        ],
    ),
    _condition(
        "isakmp_softether",
        title="SoftEther VPN service reported as a traffic reflector",
        category="exposure",
        family="isakmp",
        tags=["softether"],
        body="Shadowserver identified an internet-facing SoftEther VPN service associated with "
        "a documented L2TP response behavior. In an affected configuration, the service can "
        "send unwanted traffic to a third party.",
        limitations="The report does not establish that the VPN participated in an attack. "
        "An IKE protocol version is separate from the installed SoftEther software release.",
        review="Check the installed SoftEther edition and build and whether L2TP is required. "
        "Compare the installed package with the maintainer's fixed release for the applicable "
        "branch. Disable unneeded L2TP access or apply the appropriate corrected build.",
        sources=[
            _report_reference(
                "Vulnerable ISAKMP Report",
                "vulnerable-isakmp-report",
                "The softether tag identifies SoftEther VPN endpoints reported for potential "
                "reflection and amplification. The version field describes the IKE protocol.",
            ),
            _reference(
                "SoftEther VPN Project",
                "SoftEther VPN L2TP amplification advisory",
                "https://github.com/SoftEtherVPN/SoftEtherVPN/security/advisories/GHSA-j35p-p8pj-vqxq",
                "The maintainer describes the affected L2TP configuration and identifies a corrected "
                "software release in its package advisory.",
            ),
        ],
    ),
    _condition(
        "badsecrets_secret_found",
        title="Known weak application secret identified",
        category="configuration",
        family="badsecrets",
        tags=["badsecret"],
        fields={"badsecret_type": "SecretFound"},
        body="The detector reports a match between application output and a known weak "
        "cryptographic secret. Its module and location fields identify the check and where "
        "the matching evidence appeared. The security effect depends on what the application "
        "uses that secret to protect.",
        limitations="This result does not establish who used the secret, whether a session "
        "was forged, or which other systems share the key.",
        review="Identify the application and key purpose using its configuration and the "
        "reported module. Replace the weak secret, retire the old value and invalidate affected "
        "sessions or tokens where applicable. Review relevant authentication or application logs.",
        sources=[
            _report_reference(
                "Badsecrets Report",
                "badsecrets-report",
                "The provider documents a SecretFound result, with separate fields for the detection "
                "module and location in the application's response.",
            ),
            _reference(
                "OWASP Foundation",
                "Secrets Management Cheat Sheet",
                "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html",
                "OWASP describes rotating, revoking and auditing secrets throughout their lifecycle, "
                "including revoking compromised keys and tokens.",
            ),
        ],
    ),
    _condition(
        "rdp_native_security",
        title="Remote Desktop responded with native RDP security",
        category="configuration",
        family="rdp",
        tags=["rdp"],
        fields={"rdp_protocol": "RDP"},
        body="Shadowserver classified the responding Remote Desktop connection as native RDP "
        "security. Its report distinguishes that response from TLS-enforced security and from "
        "a connection requiring Network Level Authentication.",
        limitations="The negotiation result describes the endpoint at the observation time. "
        "It does not identify the operating system, demonstrate a successful sign-in, or "
        "determine which accounts could connect.",
        review="Review the effective Remote Desktop security policy on the identified host "
        "and any gateway. Require Network Level Authentication on supported clients and hosts, "
        "and restrict the networks and users allowed to reach the service.",
        sources=[
            _report_reference(
                "Accessible RDP Report",
                "accessible-rdp-report",
                "The rdp_protocol field distinguishes native RDP security, enforced TLS, enforced "
                "CredSSP, unsupported negotiation and a server that ignores negotiation.",
            ),
            _reference(
                "Microsoft",
                "Enable Remote Desktop on your PC",
                "https://learn.microsoft.com/en-us/windows-server/remote/remote-desktop-services/remotepc/remote-desktop-allow-access",
                "Microsoft recommends Network Level Authentication, describes how it authenticates "
                "users before establishing a remote session, and documents authorized remote users.",
            ),
        ],
    ),
]
BANK.update({condition["id"]: condition for condition in _CONDITIONS})


# Older case drafts can still resolve the edition from which their excerpts were selected.
PREVIOUS_BANK = BANK

# Each entry pairs Shadowserver's observation with the limits of the evidence and
# product or protocol context from the retained citations. No action is prescribed.
_WORDING = {
    "http_eol_component": (
        "Shadowserver's lifecycle tag identifies a reported component or device associated with "
        "the web service. Suppliers generally stop issuing routine fixes after a support period ends.",
        "The tag alone identifies neither a particular CVE nor the security-update coverage "
        "of the installed package.",
        "A supplier's lifecycle notice describes the covered release and dates. Red Hat explains "
        "how a maintained package can receive security fixes while retaining an older upstream "
        "version number.",
    ),
    "http_eol_php": (
        "Shadowserver uses eol-php for a reported PHP release past its upstream support period. "
        "PHP publishes the support dates for each branch of its server-side software.",
        "An externally visible PHP version does not identify the distributor's installed package "
        "or establish whether a specific CVE applies.",
        "The PHP project lists supported and retired branches. A distributor may maintain "
        "a package separately. Its package revision and security advisories identify that coverage.",
    ),
    "http_iis_support": (
        "Microsoft identifies IIS as a Windows component. Shadowserver uses eol-iis and eos-iis "
        "to distinguish its assessments of Windows and extended-security-update support.",
        "An IIS version alone does not identify the Windows edition, installed updates, or "
        "extended-support coverage.",
        "Microsoft's lifecycle documentation links IIS support to the host operating system. "
        "The Windows release and its eligibility for Extended Security Updates affect how a "
        "lifecycle tag applies.",
    ),
    "exchange-eol": (
        "Shadowserver's lifecycle tag identifies an Exchange release that it associates "
        "with the end of its usual support period.",
        "The externally reported version leaves the installed update level and any separate "
        "support entitlement unresolved. The tag supplies no evidence of unauthorized access.",
        "Microsoft lists Exchange build numbers and release dates. Its supportability matrix "
        "describes support conditions for particular releases.",
    ),
    "http_basic_auth": (
        "Shadowserver uses basic-auth when a plain HTTP endpoint requests Basic authentication. "
        "RFC 7617 explains that Basic encodes the username and password without encrypting them. "
        "If a client responds over this connection, someone observing the traffic could read them.",
        "The observation records the server's challenge. It does not show whether anyone "
        "sent credentials, intercepted traffic, or signed in.",
        "RFC 7617 describes TLS as a way to protect the exchange in transit. Whether a client "
        "used a particular connection is a separate question from what the server offered.",
    ),
    "http_git_config": (
        "Shadowserver uses this tag when a web endpoint returns a Git repository configuration "
        "file. Git configuration can identify a repository and its remote location.",
        "The response shows which file was available at the observation time. It does not establish "
        "that other files or credentials were exposed or downloaded.",
        "The Swiss National Cyber Security Centre describes how repository metadata published "
        "with a website can reveal development history or sensitive information. The contents of "
        "the deployment determine which information was accessible.",
    ),
    "http_megarac_management": (
        "Shadowserver uses megarac and potential-megarac for a public Redfish management endpoint. "
        "The tags indicate different degrees of confidence in identifying AMI MegaRAC firmware.",
        "The response alone does not establish the exact firmware revision, patch status, "
        "or a successful administrative login.",
        "NSA and CISA describe baseboard management controllers as components that can administer "
        "hardware independently of the host operating system. The hardware model and controller "
        "firmware identify the relevant supplier documentation.",
    ),
    "vcenter_dcerpc_exposed": (
        "Shadowserver uses vcenter-dcerpc-exposed when it reports that the vCenter DCERPC service "
        "was reachable from the internet.",
        "Reachability does not establish which operations the service allowed, the installed patch "
        "level, or unauthorized use. An accompanying CVE has its own evidence.",
        "Broadcom documents how firewall rules affect which clients can reach vCenter "
        "management services. Installed build and access configuration are separate from the "
        "response visible to Shadowserver.",
    ),
    "mongodb_noauth": (
        "Shadowserver uses mongodb-noauth when its request receives a list of database names "
        "without authentication. The visible_databases field can contain up to five names.",
        "The listing supplies no evidence about document reads, writes, deletion or access "
        "by another party.",
        "MongoDB documents authentication, role-based authorization and network exposure as "
        "separate controls. A list of names alone does not describe which operations any database "
        "would have permitted.",
    ),
    "smtp_exim_21nails": (
        "Shadowserver associates the SMTP service's advertised Exim version with the group "
        "of vulnerabilities known as 21Nails.",
        "The greeting does not identify installed distributor fixes or establish which issue, "
        "if any, applies to the running mail server.",
        "Canonical's advisory identifies corrected package revisions for the Ubuntu releases "
        "it covers. The running distributor package, including its revision, determines whether "
        "that advisory describes the installation.",
    ),
    "isakmp_softether": (
        "Shadowserver associates this SoftEther VPN service with a documented L2TP response "
        "behavior. In an affected configuration the service can send unwanted traffic to a third party.",
        "The report does not establish that the service participated in an attack. An IKE "
        "protocol version does not identify the installed SoftEther software release.",
        "The SoftEther maintainer's advisory identifies the software releases and L2TP service "
        "conditions associated with this finding.",
    ),
    "badsecrets_secret_found": (
        "In Shadowserver's report, SecretFound identifies a detector match between application "
        "output and a known weak secret. The module and location fields describe the matched check.",
        "The result does not identify who used the secret, whether a session was forged, or "
        "which other systems might share the value.",
        "OWASP describes how applications use and manage secrets. Whether this finding affects "
        "sessions, tokens or other application data depends on the purpose of the matched key.",
    ),
    "rdp_native_security": (
        "Shadowserver recorded native RDP security in the Remote Desktop negotiation. Its "
        "rdp_protocol field distinguishes this response from TLS or enforced CredSSP.",
        "The negotiation records the response at the observation time. It does not establish "
        "a successful sign-in, the operating system, or which accounts could connect.",
        "Microsoft describes Network Level Authentication as authentication before a remote "
        "session is established. The scan records a protocol response rather than an account's "
        "actual sign-in history.",
    ),
}
BANK = {
    key: {
        **PREVIOUS_BANK[key],
        "revision": CURRENT_EDITION,
        "body": body,
        "limitations": limits,
        "review": reference,
        "review_heading": "Source context",
    }
    for key, (body, limits, reference) in _WORDING.items()
}
BANK["http_megarac_management"]["sources"] = [
    _HTTP_REFERENCE,
    _reference(
        "National Security Agency",
        "NSA and CISA Release Guide To Protect Baseboard Management Controllers",
        "https://www.nsa.gov/Press-Room/Press-Releases-Statements/Press-Release-View/Article/3426648/nsa-and-cisa-release-guide-to-protect-baseboard-management-controllers/",
        "NSA describes a baseboard management controller's privileged hardware and "
        "firmware access. Its operating environment is separate from the host operating system.",
        edition=CURRENT_EDITION,
    ),
]
BANK["http_iis_support"]["sources"] = [
    source
    for source in PREVIOUS_BANK["http_iis_support"]["sources"]
    if source["public_url"]
    != "https://learn.microsoft.com/en-us/lifecycle/faq/extended-security-updates"
] + [
    _reference(
        "Microsoft",
        "Product Lifecycle FAQ - Extended Security Updates",
        "https://learn.microsoft.com/en-us/lifecycle/faq/extended-security-updates",
        "Microsoft describes product-specific eligibility, coverage periods and program terms "
        "for security updates after ordinary support ends.",
        edition=CURRENT_EDITION,
    )
]
