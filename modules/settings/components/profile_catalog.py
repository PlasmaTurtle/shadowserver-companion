"""Reviewed choices shared by Settings and guided setup.

These are identity and display choices, not grants of API access or jurisdiction.
"""

from copy import deepcopy

REGIONS = tuple(
    "Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|District of Columbia|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming|American Samoa|Guam|Northern Mariana Islands|Puerto Rico|U.S. Virgin Islands".split(
        "|"
    )
)
_REGION_CODES = "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY AS GU MP PR VI".split()
REGION_NAMES = {
    **{name.casefold(): name for name in REGIONS},
    **{code.casefold(): name for code, name in zip(_REGION_CODES, REGIONS, strict=True)},
}
TIMEZONES = (
    "UTC",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Anchorage",
    "Pacific/Honolulu",
)


# Reviewed against official statutory text through November 10, 2026 and
# agency regulations/policy on November 22, 2026. This is the application's
# supported profile catalog, not an exhaustive list of authorized agencies.
AUTHORITY_REVISION = "2026-11-22-v1"
AUTHORITIES = {
    "cisa": {
        "id": "cisa-targeted-outreach",
        "revision": AUTHORITY_REVISION,
        "title": "Cybersecurity risk reduction and vulnerability disclosure coordination",
        "purpose_statement": "Coordinate vulnerability notification and mitigation within CISA's cybersecurity assistance and disclosure mission.",
        "authorities": [
            {
                "citation": "6 U.S.C. § 659(c)(6), (7), (9), (n)",
                "description": "Provides technical assistance upon request, shares security recommendations and mitigation information, and coordinates vulnerability disclosure with industry and other stakeholders.",
                "url": "https://uscode.house.gov/us/usc/t6/s659/",
            },
        ],
    },
    "fbi": {
        "id": "fbi-targeted-outreach",
        "revision": AUTHORITY_REVISION,
        "title": "Federal cybercrime investigation and threat response",
        "purpose_statement": "Support authorized federal cybercrime investigation and related victim notification with a documented connection to the reported material.",
        "authorities": [
            {
                "citation": "28 U.S.C. § 533",
                "description": "Authorizes the Attorney General to appoint officials to detect and prosecute federal crimes and conduct specified investigations.",
                "url": "https://uscode.house.gov/us/usc/t28/s533/",
            },
            {
                "citation": "28 C.F.R. § 0.85(a)",
                "description": "Delegates federal-law investigation and evidence collection functions to the FBI, except responsibilities assigned exclusively to another agency.",
                "url": "https://www.ecfr.gov/current/title-28/chapter-I/part-0/subpart-P/section-0.85",
            },
            {
                "citation": "18 U.S.C. § 1030(d)(2)",
                "description": "Gives the FBI primary authority for specified subsection (a)(1) national-security computer offenses, subject to the Secret Service protective-duty exception.",
                "url": "https://uscode.house.gov/us/usc/t18/s1030/",
            },
            {
                "citation": "PPD-41, sections V–VII (coordination policy)",
                "description": "Assigns DOJ, acting through the FBI and NCIJTF, the federal threat-response lead for significant cyber incidents; it does not expand existing authorities.",
                "url": "https://obamawhitehouse.archives.gov/the-press-office/2016/07/26/presidential-policy-directive-united-states-cyber-incident",
            },
        ],
    },
    "usss": {
        "id": "usss-targeted-outreach",
        "revision": AUTHORITY_REVISION,
        "title": "Financial and computer crime investigation",
        "purpose_statement": "Support authorized financial or computer crime investigation and related preventative outreach with a documented connection to the reported material.",
        "authorities": [
            {
                "citation": "18 U.S.C. § 3056(b)(3)",
                "description": "Covers specified electronic-transfer and access-device offenses, and offenses in or against federally insured financial institutions, subject to interdepartmental agreement and other agencies' retained authority.",
                "url": "https://uscode.house.gov/us/usc/t18/s3056/",
            },
            {
                "citation": "18 U.S.C. § 1030(d)(1)",
                "description": "Authorizes Secret Service investigation of offenses under section 1030 alongside other authorized agencies.",
                "url": "https://uscode.house.gov/us/usc/t18/s1030/",
            },
            {
                "citation": "USA PATRIOT Act § 105, as amended (18 U.S.C. § 3056 note)",
                "description": "Directs development of a national electronic-crime task-force network; it is not a general grant of vulnerability-disclosure authority.",
                "url": "https://uscode.house.gov/us/usc/t18/s3056/",
            },
        ],
    },
}


AGENCIES = (
    {
        "id": "usss",
        "name": "United States Secret Service",
        "department": "U.S. Department of Homeland Security",
        "short_name": "USSS",
        "authority": AUTHORITIES["usss"],
    },
    {
        "id": "fbi",
        "name": "Federal Bureau of Investigation",
        "department": "U.S. Department of Justice",
        "short_name": "FBI",
        "authority": AUTHORITIES["fbi"],
    },
    {
        "id": "cisa",
        "name": "Cybersecurity and Infrastructure Security Agency",
        "department": "U.S. Department of Homeland Security",
        "short_name": "CISA",
        "authority": AUTHORITIES["cisa"],
    },
)


def agency_for_name(value):
    return next(
        (
            agency
            for agency in AGENCIES
            if agency["name"].casefold() == str(value).strip().casefold()
        ),
        None,
    )


def authority_snapshot(agency):
    """Capture reviewed metadata; callers cannot mutate the shared catalog."""
    return {
        **deepcopy(agency["authority"]),
        "agency_id": agency["id"],
        "agency": agency["name"],
        "department": agency["department"],
    }
