"""Versioned recipient information pages for supported Shadowserver report families."""

BANK = {
    "vulnerable_http": {
        "id": "vulnerable_http",
        "revision": "report-explainers-2026-11-10-v1",
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
        "why_heading": "Why We Review This Report",
        "why": "The report supplies the address, service, observation time, and flagged "
        "concern. Those details let us focus outreach on a specific potential entry "
        "point for cybercrime and help your technical contact locate it.",
        "routes": [
            [
                "No internal IT",
                "Start with whoever set up or maintains the named website, email service, "
                "or equipment. Ask who can review the technical pages for that service.",
            ],
            [
                "Outside IT provider",
                "Send the technical pages to your provider. Ask whether the service is "
                "within their support, whether the concern applies, and what response they "
                "recommend.",
            ],
            [
                "Internal IT team",
                "Match the reported address, service, and observation time to your "
                "inventory. Check the installed build, relevant vendor advisory, and any "
                "existing protective measures.",
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
        "revision": "report-explainers-2026-11-10-v1",
        "format": "one_pager",
        "title": "Understanding the Badsecrets Report",
        "report_types": ["scan_badsecrets", "scan6_badsecrets"],
        "source_types": ["Badsecrets", "IPv6 Badsecrets"],
        "priority": "priority",
        "intro": "Web applications use secret keys to help distinguish genuine application data from "
        "altered data. This report identifies a known or weak key in use, based on "
        "information the application already made public.",
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
        "why_heading": "Why We Review This Report",
        "why": "A website can appear normal while relying on a key that outsiders know. This gives "
        "us a specific concern to bring to the business and its application maintainer before "
        "the weakness is used for unauthorized access or tampering.",
        "routes": [
            [
                "No internal IT",
                "Contact the company that built or maintains the application. Explain that the "
                "notice concerns an application security key; changing your own sign-in password "
                "may not address it.",
            ],
            [
                "Outside IT provider",
                "Ask your provider to involve the application developer, assess the affected "
                "feature, and recommend a safe key replacement and review of possible misuse.",
            ],
            [
                "Internal IT team",
                "Confirm the detected module and deployed key, assess what that key protects, "
                "and plan rotation with any session or token changes the application requires.",
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
        "revision": "report-explainers-2026-11-10-v1",
        "format": "one_pager",
        "title": "Understanding the Compromised Website Report",
        "report_types": ["compromised_website", "compromised_website6"],
        "source_types": ["Compromised Website", "IPv6 Compromised Website"],
        "priority": "incident",
        "intro": "This report concerns signs that a website or web-accessible system has "
        "already been altered or used without permission. Shadowserver and its "
        "partners identify indicators such as malicious code, hidden access tools, "
        "or other evidence described in the report.",
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
        "why_heading": "Why We Review This Report",
        "why": "The business may be a victim while its infrastructure also puts customers "
        "or other organizations at risk. Prompt review can help the responsible "
        "technical team understand and contain the reported activity.",
        "routes": [
            [
                "No internal IT",
                "Contact your website host or maintainer and identify this as a "
                "possible security incident. Ask who can investigate the server and "
                "preserve useful records.",
            ],
            [
                "Outside IT provider",
                "Ask the provider to involve its incident-response contact, review the "
                "specific indicator, and assess whether other parts of the hosted "
                "environment could be affected.",
            ],
            [
                "Internal IT team",
                "Triage the source indicator in your incident process. Review "
                "server-side evidence and related access, preserve relevant logs, and "
                "assess containment and recovery.",
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
        "revision": "report-explainers-2026-11-10-v1",
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
                "Signs of an intruder's access",
                "Some checks identify known malicious remote-access keys or responses "
                "associated with a botnet, a collection of devices controlled by "
                "attackers.",
            ],
            [
                "A device involved in attacks",
                "Other entries come from activity against monitored systems and are "
                "matched to an identified device. The source type distinguishes scanning "
                "evidence from observed attack activity.",
            ],
            [
                "Where to begin tracing it",
                "The report includes the address, time and available device details. "
                "Behind a shared internet connection, the responsible device may be "
                "different from the gateway shown by the public address.",
            ],
        ],
        "why_heading": "Why We Review This Report",
        "why": "An affected device can support attacks on others while remaining connected to "
        "the business network. The observation gives the owner or technical provider a "
        "concrete lead for incident review.",
        "routes": [
            [
                "No internal IT",
                "Contact the company responsible for your router, cameras, storage or other "
                "connected equipment. Share the reported address, time and device details "
                "so they can identify the system.",
            ],
            [
                "Outside IT provider",
                "Ask your provider to trace the public address to the equipment in use at "
                "that time and involve the appropriate incident-response or device-support "
                "team.",
            ],
            [
                "Internal IT team",
                "Review source_type and the detection tag before drawing conclusions. "
                "Correlate address assignments and network logs, identify the responsible "
                "device, and assess related exposure.",
            ],
        ],
        "sources": [
            {
                "publisher": "The Shadowserver Foundation",
                "title": "Compromised IoT Report",
                "public_url": "https://www.shadowserver.org/what-we-do/network-reporting/compromised-iot-report/",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "revision_id": "report-explainers-2026-11-10-v1-compromised_iot",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "Non-HTTP compromise observations and correlations, "
                    "with scan or honeypot source types. A shared public "
                    "address can represent a different device behind a "
                    "gateway."
                },
            }
        ],
    },
    "smtp_vulnerable": {
        "id": "smtp_vulnerable",
        "revision": "report-explainers-2026-11-10-v1",
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
        "why_heading": "Why We Review This Report",
        "why": "These observations give us a specific mail service and security concern to "
        "bring to the responsible business. Reviewing that service can help reduce the "
        "risk of disruption or misuse of systems handling business communications.",
        "routes": [
            [
                "No internal IT",
                "Send the technical pages to the company that provides your business email "
                "or website hosting. Ask whether it operates the listed mail service.",
            ],
            [
                "Outside IT provider",
                "Ask your provider to identify the responsible mail-server operator, check "
                "the installed package and patches, and explain the recommended response.",
            ],
            [
                "Internal IT team",
                "Match the address, banner and observation time to the mail system. Compare "
                "the installed vendor package and patch history with the reported "
                "advisory.",
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
        "revision": "report-explainers-2026-11-10-v1",
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
                "An end-of-life tag identifies an older Exchange release. The responsible "
                "administrator can check its current support and upgrade position.",
            ],
            [
                "A concern with qualifications",
                "A tag marked possible can depend on a protective setting that an outside scan "
                "cannot establish. That qualification remains part of the finding.",
            ],
        ],
        "why_heading": "Why We Review This Report",
        "why": "Business email supports daily communications and transactions. The report gives us a "
        "particular server and concern to raise with its operator, helping direct review to "
        "infrastructure whose misuse could affect the business.",
        "routes": [
            [
                "No internal IT",
                "Ask whoever manages your email to identify the listed server and who maintains "
                "it. A familiar email application on your computer may connect to a separately "
                "managed server.",
            ],
            [
                "Outside IT provider",
                "Send the technical pages to your email provider. Ask it to confirm "
                "responsibility, the installed Exchange build, applicable updates and any relevant "
                "protective settings.",
            ],
            [
                "Internal IT team",
                "Match the reported address, server name and time to your environment. Check the "
                "exact build, security updates and advisory-specific controls, including Extended "
                "Protection where relevant.",
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
        "revision": "report-explainers-2026-11-10-v1",
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
        "why_heading": "Why We Review This Report",
        "why": "VPN equipment helps control connections to business networks. A specific "
        "weakness in that equipment, or a service that can be misused for attack "
        "traffic, is a practical reason to notify the responsible operator.",
        "routes": [
            [
                "No internal IT",
                "Contact whoever installed or manages your firewall, router or "
                "remote-work connection. Send the technical pages so they can identify "
                "the equipment.",
            ],
            [
                "Outside IT provider",
                "Ask the network provider to identify the gateway, check the reported "
                "issue against its firmware and configuration, and recommend an "
                "appropriate response.",
            ],
            [
                "Internal IT team",
                "Distinguish CVE findings from amplification findings. Check the actual "
                "device firmware and vendor guidance; assess required VPN reachability "
                "and applicable restrictions.",
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
        "revision": "report-explainers-2026-11-10-v1",
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
                "A hostname and certificate details can help technical staff match the "
                "service to an asset. Names returned by a service still need to be checked "
                "against the organization's records.",
            ],
        ],
        "why_heading": "Why We Review This Report",
        "why": "Poorly secured remote access can give criminals an initial foothold in a "
        "business network. Reviewing who needs this access and how it is protected is a "
        "practical opportunity to reduce that risk.",
        "routes": [
            [
                "No internal IT",
                "Ask whoever supports your computers or remote working whether the listed "
                "connection belongs to your business and who maintains it.",
            ],
            [
                "Outside IT provider",
                "Ask your provider whether this public connection is intended, who can use "
                "it, and whether a more restricted access arrangement is appropriate.",
            ],
            [
                "Internal IT team",
                "Match the endpoint to inventory. Review business need, network access "
                "restrictions, authentication, updates and remote sign-in logs.",
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
                "publisher": "CISA, FBI, NSA and MS-ISAC",
                "title": "#StopRansomware Guide",
                "public_url": "https://www.cisa.gov/sites/default/files/2023-10/StopRansomware-Guide-508C-v3_1.pdf",
                "retrieved_at": "2026-11-10T00:00:00Z",
                "revision_id": "report-explainers-2026-11-10-v1-accessible_rdp-2",
                "partition": "D",
                "referenced_by": ["EX-INFORMATION"],
                "record": {
                    "summary": "Defensive guidance recommends reviewing "
                    "remote-access need, restrictions and protections as "
                    "part of ransomware prevention."
                },
            },
        ],
    },
    "open_mongodb": {
        "id": "open_mongodb",
        "revision": "report-explainers-2026-11-10-v1",
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
                "A vulnerability tag can identify software associated with a published flaw. "
                "Technical staff need to compare the installed build and any vendor fixes "
                "with that specific finding.",
            ],
        ],
        "why_heading": "Why We Review This Report",
        "why": "The useful question is whether only intended systems and users can reach the "
        "database and use its data. MongoDB recommends authentication, appropriate "
        "permissions and restricted network exposure.",
        "routes": [
            [
                "No internal IT",
                "Start with the company that built or hosts the affected application. Ask who "
                "operates its database; that may be a different company from your website "
                "designer.",
            ],
            [
                "Outside IT provider",
                "Ask the application or hosting provider to review the reported tag and "
                "database service, confirm responsibility, and explain the access controls in "
                "place.",
            ],
            [
                "Internal IT team",
                "Match the address to the database deployment. Check the specific tag, "
                "authentication, user permissions, network rules and applicable vendor "
                "updates.",
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
        "revision": "report-explainers-2026-11-10-v1",
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
        "why_heading": "Why We Review This Report",
        "why": "An unnecessarily public system service can expose information or provide an "
        "opportunity for attack. Shadowserver recommends restricting these services "
        "from the public internet.",
        "routes": [
            [
                "No internal IT",
                "Ask the person or company maintaining your network or Windows servers to "
                "identify the listed address and service.",
            ],
            [
                "Outside IT provider",
                "Ask your provider whether this public connection is intended and whether "
                "access can be limited while preserving the functions your business uses.",
            ],
            [
                "Internal IT team",
                "Identify the service behind the reported port. Review the internet-facing "
                "firewall, host firewall and any port-forwarding rules against the "
                "required source systems.",
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

DEFERRED = {
    "scan_http": {
        "name": "Accessible HTTP",
        "reason": "This is an inventory of web services reachable from the internet. It helps "
        "identify and compare exposed assets, but the report itself does not establish a "
        "vulnerability. Keep it for context; do not issue a preventive vulnerability "
        "notification on this signal alone.",
        "source_url": "https://www.shadowserver.org/what-we-do/network-reporting/accessible-http-report/",
    },
    "scan6_http": {
        "name": "IPv6 Accessible HTTP",
        "reason": "This is an inventory of web services reachable from the internet. It helps "
        "identify and compare exposed assets, but the report itself does not establish a "
        "vulnerability. Keep it for context; do not issue a preventive vulnerability "
        "notification on this signal alone.",
        "source_url": "https://www.shadowserver.org/what-we-do/network-reporting/accessible-http-report/",
    },
    "population_isakmp": {
        "name": "Accessible ISAKMP",
        "reason": "Routine VPN reachability alone is not a strong reason for government "
        "outreach; use as inventory context or when a separate concern justifies "
        "contact.",
        "source_url": "https://www.shadowserver.org/what-we-do/network-reporting/accessible-isakmp-report/",
    },
    "population6_isakmp": {
        "name": "IPv6 Accessible ISAKMP",
        "reason": "Routine VPN reachability alone is not a strong reason for government "
        "outreach; use as inventory context or when a separate concern justifies "
        "contact.",
        "source_url": "https://www.shadowserver.org/what-we-do/network-reporting/accessible-isakmp-report/",
    },
    "scan_gtp": {
        "name": "Accessible GPRS Tunneling Protocol (GTP)",
        "reason": "Keep out of the routine small-business queue. This is a specialist mobile-network "
        "exposure that is better evaluated with the network operator or a relevant technical "
        "partner. Revisit for a deliberate telecom-focused campaign or clearly attributable "
        "unexpected exposure.",
        "source_url": "https://www.shadowserver.org/what-we-do/network-reporting/accessible-gprs-tunneling-protocol-gtp-report/",
    },
    "population_ntrip": {
        "name": "Accessible NTRIP",
        "reason": "Not a routine vulnerability-notification candidate. Public availability "
        "often serves the intended function of a positioning-correction service; "
        "without a separate concern, law-enforcement outreach would add little "
        "actionable information.",
        "source_url": "https://www.shadowserver.org/what-we-do/network-reporting/accessible-ntrip-report/",
    },
}
