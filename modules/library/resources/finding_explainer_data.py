"""Versioned technical lifecycle snippets for reported HTTP and Exchange findings."""

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
