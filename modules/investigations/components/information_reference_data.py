"""Immutable public references shared by versioned Information layouts."""

from copy import deepcopy

IC3_SOURCE = {
    "id": "ic3-2025-advisory-extract-2026-11-08",
    "revision_id": "ic3-2025-advisory-extract-2026-11-08",
    "publisher": "Federal Bureau of Investigation, Internet Crime Complaint Center",
    "title": "2025 IC3 Annual Report, pp. 7-8, 14 and 62",
    "public_url": "https://www.ic3.gov/AnnualReport/Reports/2025_IC3Report.pdf",
    "retrieved_at": "2026-11-08T00:06:12Z",
    "partition": "D",
    "referenced_by": ["EX-INFORMATION"],
    "capture_method": "Reviewed reference extract from the published report; not the full PDF.",
    "record": {
        "reporting_year": 2025,
        "business_email_compromise": {
            "complaints": 24768,
            "reported_losses_usd": 3046598558,
            "source_pages": [7, 8],
            "average_note": "The approved approximate $123,000 average is calculated as reported losses divided by complaints, rounded to the nearest $1,000.",
        },
        "ransomware": {
            "complaints": 3611,
            "reported_losses_usd": 32320105,
            "source_pages": [7, 8, 14, 62],
            "loss_scope": "Reported losses generally omit lost business, time, wages, files, equipment and third-party remediation. The figures reflect complaints to IC3, not every ransomware event or loss.",
        },
    },
}


BEC_SOURCE = {
    "id": "fbi-bec-advisory-extract-2026-11-08",
    "revision_id": "fbi-bec-advisory-extract-2026-11-08",
    "publisher": "Federal Bureau of Investigation",
    "title": "Business Email Compromise, How BEC scams work",
    "public_url": "https://www.fbi.gov/how-we-can-help-you/common-frauds-and-scams/business-email-compromise",
    "retrieved_at": "2026-11-08T00:20:58Z",
    "partition": "D",
    "referenced_by": ["EX-INFORMATION"],
    "capture_method": "Reviewed reference extract from the FBI webpage; not the full page.",
    "record": {
        "source_sections": ["Business Email Compromise", "How BEC scams work"],
        "summary": "BEC criminals can impersonate a trusted sender, use phishing, or obtain access to legitimate email conversations to induce fraudulent payments.",
        "application": "Supports the general explanation of payment fraud. It does not link a specific reported software finding to a BEC incident.",
    },
}
RANSOMWARE_SOURCE = {
    "id": "stopransomware-2023-advisory-extract-2026-11-08",
    "revision_id": "stopransomware-2023-advisory-extract-2026-11-08",
    "publisher": "CISA, FBI, NSA and MS-ISAC",
    "title": "#StopRansomware Guide, October 2023, pp. 3 and 7",
    "public_url": "https://www.cdfifund.gov/system/files/2023-11/StopRansomware_Guide_508C_v3.pdf",
    "retrieved_at": "2026-11-08T00:20:58Z",
    "partition": "D",
    "referenced_by": ["EX-INFORMATION"],
    "capture_method": "Reviewed reference extract from the joint guide hosted by the U.S. Treasury CDFI Fund; not the full PDF.",
    "record": {
        "publication_date": "2023-10",
        "source_pages": [3, 7],
        "canonical_resource": "https://www.cisa.gov/stopransomware/ransomware-guide",
        "access_note": "The CISA webpage returned HTTP 403 during review; the published guide was read from the U.S. Treasury CDFI Fund copy linked above.",
        "summary": "Internet-facing vulnerabilities and misconfigurations can enable initial access. Ransomware can interrupt access to data and services. Data theft can accompany encryption or support extortion without encryption.",
        "application": "Supports general risk context, not a conclusion that the recipient has experienced ransomware, extortion or unauthorized access.",
    },
}
REVISED_IC3_SOURCE = {
    **deepcopy(IC3_SOURCE),
    "id": "ic3-2025-information-r2-extract-2026-11-08",
    "revision_id": "ic3-2025-information-r2-extract-2026-11-08",
    "retrieved_at": "2026-11-08T00:20:58Z",
}
REVISED_IC3_SOURCE["record"]["business_email_compromise"].pop("average_note")
REVISED_IC3_SOURCE["record"]["application"] = (
    "Aggregate reported complaints and losses provide context; they are not an estimate "
    "of the recipient's probability of compromise or expected loss. No average loss is presented."
)
