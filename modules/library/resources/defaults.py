"""Initial Library wording; startup preserves existing analyst revisions."""

EXPLAINERS = [
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
