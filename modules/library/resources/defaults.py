"""Initial Library wording; startup preserves existing analyst revisions."""

PREVIOUS_EXPLAINERS = [
    (
        "financial_crime",
        "Business Email Compromise and Financial Fraud",
        "Compromised email accounts may be used to monitor business correspondence, impersonate trusted contacts, and redirect legitimate payments. Verify requests to change payment instructions through a separately established communication channel. This general fraud context does not establish that the reported system has been compromised.",
        "https://www.ic3.gov/PSA/2020/PSA200406",
    ),
    (
        "responsibility",
        "Review by Responsible IT Personnel",
        "Please provide this notification to the personnel responsible for the identified systems. Your organization or its authorized service provider should determine which reported conditions apply to the environment, identify the responsible party, and select appropriate remediation.",
        "",
    ),
    (
        "eol",
        "EOL Software Vulnerabilities",
        "The reported service appears to use a software version identified as end of life. Please confirm the installed version and its support status with the vendor, including any extended support arrangement. If the software is no longer supported, plan an upgrade or replacement and review available vendor guidance for reducing exposure.",
        "https://www.cisa.gov/resources-tools/resources/secure-your-business",
    ),
    (
        "attribution",
        "Open Source Attribution",
        "We reviewed public registration information and other available sources to associate a reported service with your organization. The supporting material is included below. Please confirm whether the reported assets belong to your organization or an authorized service provider and identify the appropriate party for follow-up.",
        "https://www.arin.net/resources/registry/whois/",
    ),
    (
        "cve",
        "Detected CVE",
        "A Common Vulnerabilities and Exposures identifier provides a reference for a publicly documented vulnerability. The identifier reported here should be reviewed alongside the vendor advisory, installed software version, configuration, and applicable remediation guidance. A reported identifier alone does not establish that exploitation has occurred.",
        "https://www.cve.org/About/Overview",
    ),
]

CITATION_TITLES = {
    "financial_crime": (
        "Federal Bureau of Investigation, Internet Crime Complaint Center",
        "Cyber Criminals Conduct Business Email Compromise through Exploitation of Cloud-Based Email Services, Costing US Businesses More Than $2 Billion",
    ),
    "responsibility": (
        "National Institute of Standards and Technology",
        "Building Your Small Business's Cybersecurity Team: From In-House to Outsourcing",
    ),
    "eol": ("Red Hat", "Security Backporting Practice"),
    "attribution": ("American Registry for Internet Numbers", "Using Whois"),
    "cve": ("CVE Program", "Overview"),
}

EXPLAINERS = [
    (
        "financial_crime",
        "Business Email Compromise and Financial Fraud",
        "The FBI's Internet Crime Complaint Center describes cases in which criminals used "
        "compromised email accounts to impersonate business contacts and divert payments. "
        "This describes a fraud pattern. A reported software or service finding alone supplies "
        "no evidence of account misuse or a fraudulent transaction.",
        "https://www.ic3.gov/PSA/2020/PSA200406",
    ),
    (
        "responsibility",
        "Service operators and technical contacts",
        "A business may manage its technology with internal staff, an outside provider, or "
        "both. The person who runs a particular service may differ from the organization "
        "listed in a public registry. Service agreements and asset records can identify those roles.",
        "https://www.nist.gov/itl/smallbusinesscyber/guidance-topic/building-your-team",
    ),
    (
        "eol",
        "EOL Software Vulnerabilities",
        "An end-of-life finding identifies a software release associated with the end of a "
        "supplier's usual support period. A distributor may maintain an older release by "
        "backporting fixes. The installed package revision and applicable support terms "
        "determine what maintenance is available.",
        "https://access.redhat.com/security/updates/backporting",
    ),
    (
        "attribution",
        "Open Source Attribution",
        "ARIN registry records identify organizations associated with Internet number "
        "resources, such as blocks of IP addresses. A registry association alone does not "
        "establish who operated a particular service at the observation time.",
        "https://www.arin.net/resources/registry/whois/",
    ),
    (
        "cve",
        "Detected CVE",
        "The CVE Program assigns identifiers to publicly disclosed vulnerabilities. A CVE "
        "record describes the issue and includes references. Whether it applies to a particular "
        "installation depends on its product, version and configuration. A reported identifier "
        "alone supplies no evidence of exploitation.",
        "https://www.cve.org/About/Overview",
    ),
]
