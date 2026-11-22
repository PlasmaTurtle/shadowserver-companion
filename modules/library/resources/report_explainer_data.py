"""Versioned recipient information pages for supported Shadowserver report families."""

CURRENT_EDITION = "report-explainers-2026-11-22-v1"

ROLE_SOURCE = {
    "publisher": "National Institute of Standards and Technology",
    "title": "Building Your Small Business's Cybersecurity Team: From In-House to Outsourcing",
    "public_url": "https://www.nist.gov/itl/smallbusinesscyber/guidance-topic/building-your-team",
    "retrieved_at": "2026-11-22T00:00:00Z",
    "revision_id": CURRENT_EDITION + "-business-team",
    "partition": "D",
    "referenced_by": ["EX-INFORMATION"],
    "record": {
        "summary": "NIST describes how small businesses organize technology support through internal staff, external providers, or a combination. The role examples are illustrative."
    },
}

BANK = {
    "vulnerable_http": {
        "id": "vulnerable_http",
        "revision": CURRENT_EDITION,
        "format": "one_pager",
        "title": "Understanding the Vulnerable HTTP Report",
        "report_types": ["scan_http_vulnerable", "scan6_http_vulnerable"],
        "source_types": ["Vulnerable HTTP", "IPv6 Vulnerable HTTP"],
        "priority": "priority",
        "intro": "Shadowserver checks web services reachable from the internet for security "
        "concerns. These services include websites, webmail sign-in pages, "
        "remote-access gateways, and equipment control panels. The concern may be "
        "behind the page visitors normally see.",
        "examples_heading": "Examples This Report Can Flag",
        "examples": [
            [
                "Known software flaws",
                "A service's version or response matches a published security problem. "
                "Depending on the flaw, an attacker may be able to read files, bypass "
                "sign-in, or run commands.",
            ],
            [
                "Software past its supported life",
                "A component, such as PHP or a web server, appears to be past its normal "
                "support period. The website may still work while that software no longer "
                "receives routine security fixes.",
            ],
            [
                "Exposed information or insecure sign-in",
                "Files meant for developers are available online, or a sign-in method "
                "sends passwords without encryption. The concern is what an outsider can "
                "retrieve or intercept.",
            ],
        ],
        "why_heading": "What the report establishes",
        "why": "The report identifies the service address, observation time and finding tag. The "
        "tag distinguishes a reported software version from a response that revealed "
        "information or offered a particular sign-in method.",
        "routes": [
            [
                "No internal IT",
                "The company that set up a website, mail service or device may hold its "
                "hosting and maintenance records.",
            ],
            [
                "Outside IT provider",
                "A hosting or support provider may know which part of the service it maintains.",
            ],
            [
                "Internal IT team",
                "An asset inventory and installed-package records can connect the reported "
                "address to a particular application and build.",
            ],
        ],
        "sources": [
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Vulnerable HTTP Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/vulnerable-http-report/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "revision_id": "report-explainers-2026-11-10-v1-vulnerable_http",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "Internet-facing HTTP services with reported "
                    "weaknesses; report includes service details and "
                    "finding tags. Version-based observations need "
                    "evaluation of the installed build and controls."
                },
            }
        ],
    },
    "badsecrets": {
        "id": "badsecrets",
        "revision": CURRENT_EDITION,
        "format": "one_pager",
        "title": "Understanding the Badsecrets Report",
        "report_types": ["scan_badsecrets", "scan6_badsecrets"],
        "source_types": ["Badsecrets", "IPv6 Badsecrets"],
        "priority": "priority",
        "intro": "Shadowserver examines publicly returned web application data for signs of weak or "
        "known secrets. The result type and detector name explain what matched. An "
        "application may use a secret to sign data such as a session cookie.",
        "examples_heading": "What the Report Helps Identify",
        "examples": [
            [
                "A key that is no longer secret",
                "An application may use a value copied from sample code or public "
                "documentation. A key intended to protect the application can then be known to "
                "outsiders.",
            ],
            [
                "The affected application feature",
                "The detection module identifies the kind of protected data involved, such as "
                "a signed cookie or application page data. The effect depends on how that "
                "application uses the key.",
            ],
            [
                "Where the evidence appeared",
                "The service address, request path and response location help a developer "
                "trace the finding. Shadowserver analyzes collected responses; this report "
                "does not require entering a protected account.",
            ],
        ],
        "why_heading": "What the report establishes",
        "why": "The finding type and detector identify the level of evidence. A SecretFound result "
        "records a match to a known secret. The purpose of the key depends on how the "
        "application uses it.",
        "routes": [
            [
                "No internal IT",
                "The application developer or host may know which service generated the response.",
            ],
            [
                "Outside IT provider",
                "A support provider may have deployment records identifying the application "
                "and its maintainer.",
            ],
            [
                "Internal IT team",
                "Application configuration records can identify the feature that uses a "
                "key. Authentication records describe a separate question about its use.",
            ],
        ],
        "sources": [
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Badsecrets Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/badsecrets-report/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "revision_id": "report-explainers-2026-11-10-v1-badsecrets",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "Known or weak application cryptographic secrets "
                    "identified by analyzing previously collected public "
                    "responses. The documented CSV field badsecret_type uses "
                    "the result SecretFound."
                },
            },
            {
                "publisher": "Black Lantern Security",
                "title": "Badsecrets library",
                "public_url": "https://github.com/blacklanternsecurity/badsecrets",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "revision_id": "report-explainers-2026-11-10-v1-badsecrets-2",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "Known-key detection for public cryptographic products "
                    "such as signed cookies and tokens; capabilities vary by "
                    "application framework."
                },
            },
        ],
    },
    "compromised_website": {
        "id": "compromised_website",
        "revision": CURRENT_EDITION,
        "format": "one_pager",
        "title": "Understanding the Compromised Website Report",
        "report_types": ["compromised_website", "compromised_website6"],
        "source_types": ["Compromised Website", "IPv6 Compromised Website"],
        "priority": "incident",
        "intro": "Shadowserver and its partners report website indicators associated with "
        "compromise. Examples include altered page content, webshells or other indicators "
        "identified in the source record.",
        "examples_heading": "Examples This Report Can Identify",
        "examples": [
            [
                "A website used to harm visitors",
                "Injected code can redirect visitors or present deceptive "
                "instructions intended to make them install malware. The legitimate "
                "site may still look familiar.",
            ],
            [
                "Hidden access to a server",
                "A webshell or implant is software placed on a system to give an "
                "intruder access. The affected system may be a website, mail server, "
                "or network appliance.",
            ],
            [
                "A specific indicator to examine",
                "The tag, category, URL and detail explain the reason for reporting. "
                "A page that now returns 'not found' does not by itself establish "
                "that the system is clean.",
            ],
        ],
        "why_heading": "What the report establishes",
        "why": "The tag, category, URL and observation time identify the indicator that "
        "Shadowserver or its partner reported. They do not establish who was responsible, "
        "the affected site's full history or the extent of any incident.",
        "routes": [
            [
                "No internal IT",
                "A website host or maintainer may hold the server logs for the time in the report.",
            ],
            [
                "Outside IT provider",
                "A hosting provider's records can identify which site or customer was using "
                "a shared address.",
            ],
            [
                "Internal IT team",
                "Server and application records can add context about when content changed "
                "and which services were involved.",
            ],
        ],
        "sources": [
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Compromised Website Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/compromised-website-report/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "revision_id": "report-explainers-2026-11-10-v1-compromised_website",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "Web-related compromise indicators, with tag, "
                    "category, URL and detail describing the "
                    "observation. Retain possible or probable "
                    "qualifications supplied in individual "
                    "records."
                },
            }
        ],
    },
    "compromised_iot": {
        "id": "compromised_iot",
        "revision": CURRENT_EDITION,
        "format": "one_pager",
        "title": "Understanding the Compromised IoT Device Report",
        "report_types": ["compromised_iot", "compromised_iot6"],
        "source_types": [
            "Compromised IoT Device",
            "IPv6 Compromised IoT Device",
            "Compromised IoT",
        ],
        "priority": "incident",
        "intro": "Connected equipment can be used by intruders without an obvious change in how "
        "it works. This report brings together observations associated with "
        "compromised devices, including network equipment and systems with "
        "remote-access services.",
        "examples_heading": "What the Report Can Reveal",
        "examples": [
            [
                "An indicator with a known limitation",
                "Shadowserver suspended its eleven11bot reporting after learning that normal "
                "device software could produce the same response. A historical tag alone "
                "cannot establish that the device was under botnet control.",
            ],
            [
                "A device involved in attacks",
                "Other entries come from activity against monitored systems and are "
                "matched to an identified device. The source type distinguishes scanning "
                "evidence from observed attack activity.",
            ],
            [
                "Where to begin tracing it",
                "The report includes the address, time and available device details. A "
                "shared internet connection may serve several different devices.",
            ],
        ],
        "why_heading": "What the report establishes",
        "why": "The source type distinguishes a detector response from activity observed against a "
        "monitored system. A public address can represent several devices. The report alone "
        "does not establish the identity of a person or the full scope of an incident.",
        "routes": [
            [
                "No internal IT",
                "A device installer or network provider may hold the equipment and service "
                "records.",
            ],
            [
                "Outside IT provider",
                "Provider records can describe which site held an address at the observation time.",
            ],
            [
                "Internal IT team",
                "Address assignments and network records can distinguish the public gateway "
                "from equipment behind it.",
            ],
        ],
        "sources": [
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Compromised IoT Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/compromised-iot-report/",
                "retrieved_at": "2026-11-22T00:00:00Z",
                "revision_id": CURRENT_EDITION + "-compromised_iot",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "The report distinguishes scan observations and honeypot "
                    "activity. Shadowserver says it suspended eleven11bot reporting because "
                    "normal HiSilicon software may produce the same response."
                },
            }
        ],
    },
    "smtp_vulnerable": {
        "id": "smtp_vulnerable",
        "revision": CURRENT_EDITION,
        "format": "one_pager",
        "title": "Understanding the Vulnerable SMTP Report",
        "report_types": ["scan_smtp_vulnerable", "scan6_smtp_vulnerable"],
        "source_types": ["Vulnerable SMTP", "IPv6 Vulnerable SMTP"],
        "priority": "priority",
        "intro": "SMTP is the service mail servers use to exchange email. This report flags "
        "mail-server software whose advertised version matches a known security "
        "concern. Its documented checks include Exim, a mail server commonly managed "
        "by an IT or hosting provider.",
        "examples_heading": "What the Report Tells Us",
        "examples": [
            [
                "Mail software identity",
                "The server's greeting, called a banner, can identify the software and "
                "version answering at the reported address.",
            ],
            [
                "A published security concern",
                "Tags identify the reported issue, such as the Exim vulnerability group "
                "known as 21Nails or a specific CVE number.",
            ],
            [
                "What needs confirmation",
                "The advertised version may not reflect security fixes supplied by the "
                "server's operating-system vendor. The installed package and patch "
                "history matter.",
            ],
        ],
        "why_heading": "What the report establishes",
        "why": "The SMTP greeting describes the software identity advertised by the server. It may "
        "omit distributor-specific security fixes. Installed package details are separate "
        "evidence about the reported concern.",
        "routes": [
            [
                "No internal IT",
                "A business email or hosting provider may operate the mail service named in "
                "the report.",
            ],
            [
                "Outside IT provider",
                "Service records can identify which organization operates the mail server "
                "and maintains its software.",
            ],
            [
                "Internal IT team",
                "An inventory of mail servers and their installed packages can connect a "
                "banner to a particular deployment.",
            ],
        ],
        "sources": [
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Vulnerable SMTP Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/vulnerable-smtp-report/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "revision_id": "report-explainers-2026-11-10-v1-smtp_vulnerable",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "Documented checks concern Exim 21Nails and "
                    "CVE-2020-28020, inferred from SMTP banner versions; "
                    "vendor backports can make version-only conclusions "
                    "wrong. Exchange uses a separate report."
                },
            }
        ],
    },
    "exchange": {
        "id": "exchange",
        "revision": CURRENT_EDITION,
        "format": "one_pager",
        "title": "Understanding the Vulnerable Exchange Server Report",
        "report_types": ["scan_exchange", "scan6_exchange"],
        "source_types": ["Vulnerable Exchange Server", "IPv6 Vulnerable Exchange Server"],
        "priority": "priority",
        "intro": "Microsoft Exchange is software used to run business email and calendars. This report "
        "identifies internet-facing Exchange services associated with published security "
        "weaknesses or older unsupported releases.",
        "examples_heading": "Examples This Report Can Flag",
        "examples": [
            [
                "Known Exchange flaws",
                "The observed service or version matches a published concern. Depending on the "
                "flaw, an attacker may be able to gain access or run commands on the server.",
            ],
            [
                "Older unsupported releases",
                "An end-of-life tag identifies an older Exchange release. Installed updates "
                "and support entitlements are information held by the operator or supplier.",
            ],
            [
                "A concern with qualifications",
                "A tag marked possible can depend on a protective setting that an outside scan "
                "cannot establish. That qualification remains part of the finding.",
            ],
        ],
        "why_heading": "What the report establishes",
        "why": "A release label can identify a product family or build. A reported possible "
        "vulnerability may depend on a configuration setting, security update or support "
        "arrangement that is not visible to the scan.",
        "routes": [
            [
                "No internal IT",
                "A business email provider may operate the server used by staff email "
                "applications.",
            ],
            [
                "Outside IT provider",
                "Mail-service records can identify the operator and its responsibility for "
                "updates.",
            ],
            [
                "Internal IT team",
                "Exchange build and update records can give the installed version at a "
                "particular time.",
            ],
        ],
        "sources": [
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Vulnerable Exchange Server Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/vulnerable-exchange-server-report/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "revision_id": "report-explainers-2026-11-10-v1-exchange",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "Most assessments use the observed version; CVE-2021-26855 "
                    "has a specific check. A possible-CVE-2024-21410 tag "
                    "retains uncertainty about Extended Protection. Address, "
                    "timestamp, version, server name, URL and tags help locate "
                    "the installation."
                },
            }
        ],
    },
    "isakmp_vulnerable": {
        "id": "isakmp_vulnerable",
        "revision": CURRENT_EDITION,
        "format": "one_pager",
        "title": "Understanding the Vulnerable ISAKMP Report",
        "report_types": ["scan_isakmp", "scan6_isakmp"],
        "source_types": ["Vulnerable ISAKMP", "IPv6 Vulnerable ISAKMP"],
        "priority": "priority",
        "intro": "ISAKMP and related IKE services help establish protected VPN connections. "
        "This report identifies an internet-facing VPN service with a specific "
        "reported weakness, such as affected device software or a response that can "
        "be abused to generate attack traffic.",
        "examples_heading": "Different Concerns in This Report",
        "examples": [
            [
                "A flaw in VPN equipment",
                "Some tags identify known vulnerabilities in a firewall or VPN device. "
                "Version-based checks need comparison with the actual firmware and "
                "vendor advisory.",
            ],
            [
                "Traffic amplification",
                "Other findings concern a service that can produce larger replies to "
                "small requests. Attackers may misuse that behavior to direct unwanted "
                "traffic at someone else.",
            ],
            [
                "The affected endpoint",
                "The address, UDP port, observation time and finding tag help the "
                "network operator identify which gateway and which concern need "
                "review.",
            ],
        ],
        "why_heading": "What the report establishes",
        "why": "A vulnerability identifier refers to a published product issue. A reflection "
        "finding describes an observed response pattern. The software build and the "
        "protocol version are separate details.",
        "routes": [
            [
                "No internal IT",
                "The company that set up remote access may know which gateway provides that "
                "service.",
            ],
            [
                "Outside IT provider",
                "A network provider may hold the gateway model, firmware and service "
                "configuration.",
            ],
            [
                "Internal IT team",
                "Gateway inventory and network records can connect an address and reported "
                "response to the VPN installation.",
            ],
        ],
        "sources": [
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Vulnerable ISAKMP Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/vulnerable-isakmp-report/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "revision_id": "report-explainers-2026-11-10-v1-isakmp_vulnerable",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "Version-based WatchGuard CVE findings are marked "
                    "critical; SoftEther tags concern UDP "
                    "reflection/amplification. Do not treat the "
                    "protocol version field as device firmware. Do not "
                    "route population_isakmp here."
                },
            },
            {
                "publisher": "Internet Engineering Task Force",
                "title": "RFC 2408: Internet Security Association and Key Management Protocol",
                "public_url": "https://www.rfc-editor.org/rfc/rfc2408",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "revision_id": "report-explainers-2026-11-10-v1-isakmp_vulnerable-2",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "ISAKMP defines procedures and message formats for "
                    "security associations and key-management "
                    "negotiation."
                },
            },
        ],
    },
    "accessible_rdp": {
        "id": "accessible_rdp",
        "revision": CURRENT_EDITION,
        "format": "one_pager",
        "title": "Understanding the Accessible RDP Report",
        "report_types": ["scan_rdp", "scan6_rdp"],
        "source_types": [
            "Accessible RDP Report",
            "IPv6 Accessible RDP Report",
            "Accessible RDP",
            "IPv6 Accessible RDP",
        ],
        "priority": "targeted",
        "intro": "Remote Desktop Protocol (RDP) lets a person work on a computer from another "
        "location. This report identifies RDP services that answered from the public "
        "internet. A response establishes reachability, not that someone signed in.",
        "examples_heading": "What This Report Helps Identify",
        "examples": [
            [
                "A remote-access entry point",
                "The address, port and observation time help locate the computer or server "
                "offering remote desktop access.",
            ],
            [
                "Connection protections",
                "The response can show the security mode negotiated by the service, "
                "including whether Network Level Authentication is required. It does not "
                "reveal every account or network safeguard.",
            ],
            [
                "Clues to the responsible system",
                "A hostname or certificate can help identify a responding service. Local "
                "asset records provide additional evidence of its operator.",
            ],
        ],
        "why_heading": "What the report establishes",
        "why": "The report records that a remote desktop service answered from the internet. "
        "Negotiation fields describe the security mode the service reported. The "
        "observation alone does not identify who could sign in or establish that anyone "
        "did.",
        "routes": [
            [
                "No internal IT",
                "The person or company supporting remote access may hold records for the service.",
            ],
            [
                "Outside IT provider",
                "A provider may know whether a gateway or other access control formed part "
                "of the connection.",
            ],
            [
                "Internal IT team",
                "Endpoint inventory and sign-in records can distinguish the responding "
                "system from evidence of an actual session.",
            ],
        ],
        "sources": [
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Accessible RDP Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/accessible-rdp-report/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "revision_id": "report-explainers-2026-11-10-v1-accessible_rdp",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "The report records reachability and negotiated "
                    "protocol/certificate details; it does not establish "
                    "successful authentication, absent MFA, a vulnerable "
                    "operating-system build, or compromise. "
                    "CredSSP_Enforced indicates Network Level "
                    "Authentication; it is not evidence of MFA or a "
                    "complete security assessment. The "
                    "certificate-derived or reverse-DNS hostname is an "
                    "attribution lead, not proof of business ownership."
                },
            },
            {
                "publisher": "Microsoft",
                "title": "Enable Remote Desktop on your PC",
                "public_url": "https://learn.microsoft.com/en-us/windows-server/remote/remote-desktop-services/remotepc/remote-desktop-allow-access",
                "retrieved_at": "2026-11-22T00:00:00Z",
                "revision_id": CURRENT_EDITION + "-accessible_rdp-2",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "Microsoft describes permitted users, network access and "
                    "Network Level Authentication as separate parts of a Remote Desktop deployment."
                },
            },
        ],
    },
    "open_mongodb": {
        "id": "open_mongodb",
        "revision": CURRENT_EDITION,
        "format": "one_pager",
        "title": "Understanding the Open MongoDB Service Report",
        "report_types": ["scan_mongodb", "scan6_mongodb"],
        "source_types": ["Open MongoDB Service", "IPv6 Open MongoDB Service"],
        "priority": "priority",
        "intro": "MongoDB is database software used behind applications and websites. This report "
        "identifies database services reachable from the internet and records what they "
        "disclose. The concern may be in the application's data storage even when the "
        "public website looks normal.",
        "examples_heading": "What the Report Can Distinguish",
        "examples": [
            [
                "A reachable database",
                "The address, port and software version help technical staff locate the "
                "database service. Public reachability alone does not establish that its "
                "records can be read.",
            ],
            [
                "A missing sign-in check",
                "The mongodb-noauth tag means Shadowserver obtained a database listing "
                "without authentication. The report can include the first five database "
                "names, not the contents of those databases.",
            ],
            [
                "A version-linked concern",
                "A vulnerability tag can identify software associated with a published "
                "flaw. The installed package and its supplier's security updates affect "
                "whether that flaw applies.",
            ],
        ],
        "why_heading": "What the report establishes",
        "why": "The tag distinguishes a reachable service, a listing of database names and a "
        "possible version-related concern. MongoDB documents network access, authentication "
        "and authorization separately.",
        "routes": [
            [
                "No internal IT",
                "The company hosting an application may know which service operates its database.",
            ],
            [
                "Outside IT provider",
                "A database provider may hold account, deployment and network-access records.",
            ],
            [
                "Internal IT team",
                "Deployment configuration and audit records can add context about client "
                "access to individual databases.",
            ],
        ],
        "sources": [
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Open MongoDB Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/open-mongodb-report/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "revision_id": "report-explainers-2026-11-10-v1-open_mongodb",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "The no-auth check retrieves a database listing, not "
                    "the full records inside each database. "
                    "visible_databases='none visible' also covers errors; "
                    "it does not prove authentication or safety. "
                    "CVE-2025-14847 detection is version-based and "
                    "backported fixes can produce false positives."
                },
            },
            {
                "publisher": "MongoDB",
                "title": "Security Checklist for Self-Managed Deployments",
                "public_url": "https://www.mongodb.com/docs/manual/administration/security-checklist/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "revision_id": "report-explainers-2026-11-10-v1-open_mongodb-2",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "MongoDB deployment security guidance covers "
                    "authentication, authorization and limits on network "
                    "exposure."
                },
            },
        ],
    },
    "accessible_msrpc": {
        "id": "accessible_msrpc",
        "revision": CURRENT_EDITION,
        "format": "one_pager",
        "title": "Understanding the Accessible MS-RPC Service Report",
        "report_types": ["scan_msrpc", "scan6_msrpc"],
        "source_types": ["Accessible MS-RPC Service", "IPv6 Accessible MS-RPC Service"],
        "priority": "targeted",
        "intro": "Microsoft Remote Procedure Call (MS-RPC) lets software request services on "
        "another computer. This report identifies MS-RPC services that responded from "
        "the public internet. It concerns a system-to-system connection, rather than "
        "the page a customer sees in a browser.",
        "examples_heading": "What This Report Helps Identify",
        "examples": [
            [
                "A service directory",
                "Port 135 can provide the connection details another computer needs to "
                "reach an RPC service. The report may identify this endpoint-mapping "
                "service.",
            ],
            [
                "A direct service connection",
                "The scan also checks selected higher ports. A response there identifies "
                "a directly reachable RPC service, so reviewing only port 135 may miss "
                "the reported exposure.",
            ],
            [
                "A location to review",
                "The address, port, observation time and protocol response help "
                "administrators locate the endpoint. The protocol version is not a "
                "finding about a particular Windows security update.",
            ],
        ],
        "why_heading": "What the report establishes",
        "why": "The responding port and protocol fields identify the endpoint that answered. Those "
        "details alone do not establish whether its public availability was intended, which "
        "operations it permitted or whether a particular Windows update was installed.",
        "routes": [
            [
                "No internal IT",
                "The network or Windows service provider may hold records for the "
                "responding address.",
            ],
            [
                "Outside IT provider",
                "A provider may have records of the public address, the service it fronts "
                "and the applicable network rules.",
            ],
            [
                "Internal IT team",
                "Endpoint and firewall records can identify the Windows service behind the "
                "reported port.",
            ],
        ],
        "sources": [
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Accessible MS-RPC Service Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/accessible-ms-rpc-service-report/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "revision_id": "report-explainers-2026-11-10-v1-accessible_msrpc",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "The MS-RPC protocol version is not the Windows "
                    "operating-system version or a CVE finding. A bind "
                    "acknowledgement or authentication-field length "
                    "does not establish unauthenticated administrative "
                    "access. The reported port may be 135 or a directly "
                    "probed higher port; do not reduce all findings to "
                    "port 135."
                },
            },
            {
                "publisher": "Microsoft Learn",
                "title": "Configure Firewall Rules With Group Policy",
                "public_url": "https://learn.microsoft.com/en-us/windows/security/threat-protection/windows-firewall/create-inbound-rules-to-support-rpc",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "revision_id": "report-explainers-2026-11-10-v1-accessible_msrpc-2",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "Windows firewall guidance distinguishes the RPC "
                    "endpoint mapper and the separate ports used by RPC "
                    "services."
                },
            },
        ],
    },
}

# The Library browser and the recipient page share the source for organizational roles.
for page in BANK.values():
    page["sources"].append(ROLE_SOURCE)
    page["roles_heading"] = "Who may hold service records"

DEFERRED = {
    "scan_http": {
        "name": "Accessible HTTP",
        "reason": "This inventory records web services that responded from the internet. A response "
        "alone establishes reachability. It supplies no separate evidence of a "
        "vulnerability.",
        "source_url": "https://www.shadowserver.org/what-we-do/network-reporting/accessible-http-report/",
    },
    "scan6_http": {
        "name": "IPv6 Accessible HTTP",
        "reason": "This inventory records web services that responded from the internet. A response "
        "alone establishes reachability. It supplies no separate evidence of a "
        "vulnerability.",
        "source_url": "https://www.shadowserver.org/what-we-do/network-reporting/accessible-http-report/",
    },
    "population_isakmp": {
        "name": "Accessible ISAKMP",
        "reason": "This inventory records VPN-related services that responded from the internet. The "
        "response alone does not identify a specific weakness.",
        "source_url": "https://www.shadowserver.org/what-we-do/network-reporting/accessible-isakmp-report/",
    },
    "population6_isakmp": {
        "name": "IPv6 Accessible ISAKMP",
        "reason": "This inventory records VPN-related services that responded from the internet. The "
        "response alone does not identify a specific weakness.",
        "source_url": "https://www.shadowserver.org/what-we-do/network-reporting/accessible-isakmp-report/",
    },
    "scan_gtp": {
        "name": "Accessible GPRS Tunneling Protocol (GTP)",
        "reason": "GTP is used in mobile networks. The report records an accessible service. The "
        "network operator's configuration and intended connectivity determine how that "
        "observation applies.",
        "source_url": "https://www.shadowserver.org/what-we-do/network-reporting/accessible-gprs-tunneling-protocol-gtp-report/",
    },
    "population_ntrip": {
        "name": "Accessible NTRIP",
        "reason": "NTRIP distributes positioning-correction data. Public availability can be part of "
        "the service's intended operation. Reachability alone does not identify a specific "
        "vulnerability.",
        "source_url": "https://www.shadowserver.org/what-we-do/network-reporting/accessible-ntrip-report/",
    },
}
