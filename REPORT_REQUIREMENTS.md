TLP:AMBER

# Shadowserver Companion v0.7.0 — Release Requirements

**Release theme:** Branded, source-backed notification exhibits and a complete Companion Appendix.  
**Requirements revision:** 1.0 · November 7, 2026 · America/New_York.  
**Status:** Historical release implementation contract. See VALIDATION.md and HOME_VALIDATION.md for current verification evidence and release acceptance.  
**Baseline:** Application 0.6.0; workbench database schema 6; report snapshot schema 6; package manifest schema 3; standalone Attribution Module 0.2.1.  
**Handling:** TLP:AMBER. Share on a need-to-know basis within the receiving organization and its clients. Source-specific additional restrictions remain applicable. [S8]

## 1. Release objective and governing decisions

Turn the accepted exhibit prototype into production features within the existing Windows application. An analyst should import a scan, qualify a business association, reuse published vulnerability information, review five report sections, certify the exact output, deliver it, and close the notification without retyping collected evidence.

The recipient receives a concise notification followed by a readable, complete Companion Appendix after the closing and signature. The internal package retains the source files, machine-readable records, review chronology, and integrity hashes. The report must remain useful without the application or internet access.

### 1.1 Decisions fixed for this release

| Decision | Required outcome |
| --- | --- |
| Version | Target **0.7.0**, a coordinated pre-1.0 feature release; use this version consistently in app, installer, manifests, and release notes. |
| Product and case names | **Shadowserver Companion**; each unit of notification work is a **Shadowserver Notification**. |
| Visible workflow | **Scan Validation → Documentation → Pending Notification → Closing Report**, with Completed as an archive. |
| Default outreach | Critical findings. Lower-severity data remains retained; deliberate targeted work must be identifiable and must not silently use an inaccurate critical-only narrative. |
| Qualification | One accepted supporting attribution can qualify a domain group containing many reported assets. Do not imply that all its assets were separately attributed. |
| Branding | Separate agency branding profile from application appearance. Provide Companion and USSS profiles; retain the Dark Matter design direction. |
| Color meaning | Blue indicates confirmation/validation. Red indicates adverse findings or explicit failure. Pending, unknown, and unreviewed states are neutral. |
| Report text | All generated report text is pure black on white paper, **except the standards-based TLP marking**. Original source images remain unchanged. |
| Handling marking | **TLP:AMBER**, not TLP:YELLOW. Apply across the application and generated outputs, with document placement and colors defined in section 4. |
| Main report | Five existing builder sections: Introduction, Vulnerabilities, Attribution, Information, Closing. Integrate the three exhibits into those sections. |
| Appendix | A **Companion Appendix starts after the closing/signature**, with every case-relevant observation and captured information item represented field by field. |
| Wording | Preserve the established paragraphs and fixed narrative sentences. Only defined insertables change. New boilerplate remains a separately versioned proposal until explicitly selected for use. |
| Exploitation intelligence | Separate KEV, known ransomware use, SSVC exploitation assessment, potential impact, and EPSS. They may coexist; none establishes compromise of the recipient. |
| Certification | Extend the existing persistent section-validation and final-certification system. Do not introduce the prototype's session-only review system into production. |

This specification supersedes the older report requirements where they conflict with these decisions. It carries forward their evidence retention, citations, local operation, case isolation, and certification protections. The appendix placement supersedes the earlier requirement to put all full CVE descriptions before attribution; the full descriptions remain unchanged and cited in the appendix. Existing certified files remain historical artifacts and are never silently reformatted.

### 1.2 Verified baseline and release delta

The following is based on inspection of the saved 0.6.0 source package and exhibit prototype, not a claim that this release's acceptance tests have passed. [B1–B3]

| Area | Existing implementation | v0.7.0 change |
| --- | --- | --- |
| Opening view | ECLIPSE; local map/density/shared-ASN views; retained excluded rows and unplaced observations | Apply shared branding, semantic colors, TLP, and enrichment filters without removing coverage. |
| Theme | Browser-local light/dark preference; ECLIPSE has separately scoped styling | Persist versioned branding and appearance; make all application surfaces coherent. |
| Sources | NVD-first published descriptions; CVE Program fallback; source-specific CVSS; shared raw-response cache/hashes | Add independent SSVC, ransomware, and reviewed impact records; retain reference tags and source revisions. |
| KEV/EPSS | Existing `enrich()` retrieves EPSS and the full matching KEV entry | Normalize ransomware data already potentially present in `kev_details`; strengthen completeness/provenance checks and expose indicators. |
| Review | Five persistent section validations, author/time, reopen reason, stale dependency checks | Include exhibits, appendix content, selected intelligence revisions, branding, and handling policy in dependency hashes. |
| Report | Shared composition; ReportLab PDF; python-docx DOCX; established copy; optional images | Add production exhibit renderer, black-text print rules, TLP header/footer, and complete appendix. |
| Prototype | Two synthetic cases; shared SVG; 3-page exhibit samples; transient demo history | Adapt real case data; persist through existing backend; integrate into complete notifications. |
| Packaging | Immutable PDF/DOCX, snapshot, captured evidence, work log, chronology, manifest | Include exhibit masters/fallbacks, appendix index, exact rendering versions, and complete source-to-display mappings. |

No separate major-version increase of the Attribution Module is required if its public interface does not change. Use the next numbered database migration only for actual persistence changes; do not rename stored workflow states merely to match visible labels.

## 2. Scope, workflow, and data preservation

### 2.1 Workflow requirements

| ID | Requirement |
| --- | --- |
| WF-01 | Preserve the four visible stages. Scan Validation is the intake/qualification view; Documentation maps to an in-progress notification; Pending Notification contains certified reports awaiting contact or delivery; successful delivery leads to Closing Report; finalized closing moves to Completed. |
| WF-02 | Preserve separation of entity, hostname, root-domain group, scan observation, notification case, report revision, delivery event, and closing revision. A hostname may initially provide the entity's display name without asserting a researched legal identity. |
| WF-03 | Keep recipient contact/name/title/email in the entity record and outreach activity. Report To remains exactly **Principle Executive / IT Director**. Sender name/title come from Settings and are read-only in the builder. |
| WF-04 | Import, qualification, documentation, certification, delivery, and closing metrics must be derived from saved records. A generated report, attempted email, or phone call is not a successful delivery. Confirmed delivery names the recipient and exact certified revision. |
| WF-05 | Preserve contact plans, callbacks, due follow-ups, delivery attempts, outcomes, and internal closing reports. Closing without successful delivery remains separately labeled and counted. |
| WF-06 | Preserve case-scoped membership. Later scans, source refreshes, entity renaming/combination, or new findings must not silently expand a certified or closed notification. New work is a new case or an explicit revision. |
| WF-07 | A report containing supported attribution and adequate structured evidence can be certified without mandatory hostname/CVE screenshots. Record website-active/contact review; Secretary of State evidence remains optional additional research. |
| WF-08 | A data refresh, profile change, or explicit inclusion/exclusion must never delete the original observation. Record the decision, actor, reason where applicable, timestamp, and affected case revision. |

### 2.2 Input and report-specific schema requirements

| ID | Requirement |
| --- | --- |
| IN-01 | Preserve the original workbook byte-for-byte with its fingerprint, filename, import time, and source context. Read actual headers; retain the whole row before applying eligibility rules. Entirely blank rows are counted separately from rejected observations. |
| IN-02 | Preserve every supplied field, including unknown columns, zero, false, empty strings, and null values where distinguishable. Store workbook/sheet/row identity. Normalized values supplement rather than overwrite the source values. |
| IN-03 | Separate **ingestion validity** from **notification eligibility**. Data excluded from the lead queue remains available to the scan summary, map inventory, and source inspector. Do not run attribution lookups for rows already excluded by configured workload/jurisdiction rules. |
| IN-04 | Use a common observation envelope plus report-specific profiles. Profiles declare endpoint roles, field mappings, finding extraction, relevant versions/products, and eligibility rules. Do not treat the upstream field inventory as a universal required-field/type schema. |
| IN-05 | Bundle a pinned Shadowserver report-profile inventory with source commit/hash and adapter version. The audited inventory contains 177 definitions and 745 distinct field names at the recorded commit; these are snapshot counts, not permanent constants. Record the version actually used for each import. [B4] |
| IN-06 | Preserve unknown report types as unclassified records; show the actual capability status: retained, interpreted, or eligible for notification. Full field retention must not be described as full semantic support for every report. Add profile adapters without changing the case/report object architecture. |
| IN-07 | Preserve the established CVE-only exception: a reported CVE may remain eligible without a generic version value. EOL/other eligibility uses its report profile. Root-domain digit and suffix preferences remain configurable workload filters; service labels containing digits are not inherently invalid. |
| IN-08 | Represent multiple reported products and versions as a collection linked to the originating observation/service. Preserve the original composite version string and unresolved fragments; never attach one service's version or CVE to another service through grouping. |
| IN-09 | Retain non-public addresses with an explicit flag and no public RDAP lookup. They may remain attached to a group with qualifying public-address evidence. Do not fabricate geolocation or public routing information for them. |
| IN-10 | Preserve current jurisdiction configuration and recorded reasons for exclusion. Reported IP location and researched entity location are separate facts. Unknown coordinates belong in the unplaced inventory, not at invented map points. |
| IN-11 | Add the default critical-only lead-eligibility gate; 0.6.0 does not currently enforce this gate. Use the reported severity or an explicitly documented report-profile severity rule, preserving which supplied the value. Unknown severity remains unknown and outside the default outreach queue. EOL, KEV membership, ransomware use, or a missing severity cannot independently imply Critical. Retain all rows; deliberate targeted inclusion records an explicit override and appropriate report template. Other observations may accompany a critical-led case as clearly labeled context without being reclassified as Critical. |

### 2.3 Attribution requirements carried forward

| ID | Requirement |
| --- | --- |
| AT-01 | Reuse the independent Attribution Module and existing IANA/RIR routing, bounded requests, caches, raw evidence, retries, and saved result IDs. Do not replace RDAP with an unrelated WHOIS scraper. |
| AT-02 | Preserve the lookup sequence: exact root-domain association in registration data; reported-hostname forward A/AAAA match; forward-confirmed PTR evidence where appropriate; network/entity keyword candidates for human review. Distinguish unsuccessful association from request failure. |
| AT-03 | Match normalized registrable domains at domain boundaries. Subdomains remain eligible; unrelated strings merely containing the root text do not constitute an exact domain match. Preserve the original field and its value as evidence. |
| AT-04 | Partial organization-name matches remain review candidates and do not stop later exact-match attempts. A human acceptance records reviewer, time, reason/basis, and evidence result. A failed reverse lookup is not proof that an address moved. |
| AT-05 | Show **Reported IP → evidence/validated IP or covering network → source**, plus matched root/field, method, decision actor/time, and source retrieval time. Use range membership wording for a network match; do not invent a second resolved IP. |
| AT-06 | Show reported-asset count separately from qualifying-evidence count. Preserve the legacy supporting-entry-at-index-zero contract where consumed, but add/use explicit supporting entry/result IDs internally so sorting cannot change the meaning. |
| AT-07 | When several domain groups form one business notification, retain each group's qualification or documented review basis. One supporting IP qualifies its accepted group; a shared ASN or unrelated domain must not silently extend that qualification. |

## 3. Branding and semantic color system

### 3.1 Settings and palette

Branding profile and appearance are separate settings. Initial branding profiles are `companion` and `usss`. Appearance supports light, dark (the Dark Matter design direction), and system preference. Preserve an existing selected appearance on upgrade; introduce no forced color-mode switch. The ECLIPSE visualization mode is separate from application appearance.

| USSS digital token | Hex used by this release | Role |
| --- | --- | --- |
| Beast Black | `#010101` | Dark surfaces and structural identity |
| Lincoln Blue | `#002d61` | Primary identity and confirmation graphics on suitable backgrounds |
| Detail Blue | `#5f88b0` | Supporting blue graphics and dark-surface treatments where contrast permits |
| Centurion Gold | `#b4a471` | Sparing identity accents |
| Legacy Gold | `#d5cca8` | Subtle supporting accents |

The supplied hex values are the provisional digital source of truth. Centurion Gold's supplied RGB value `193,168,113` differs from hex `#b4a471` (`180,164,113`); Beast Black's supplied RGB `0,0,0` differs from `#010101`. Retain these notes in profile metadata. Do not convert the provided Pantone/CMYK values by guesswork. The supplied approval restriction accompanies the profile provenance; selecting it does not claim new HQ OPA approval. No official seal or emblem is automatically added.

Functional risk red is an application semantic token, not one of the supplied USSS brand colors. Initial visual defaults may use `#B42318` on light surfaces and `#FF6B6B` on dark surfaces, subject to contrast checks. The TLP amber value is independent of both brand golds and severity colors.

### 3.2 Required behavior

| ID | Requirement |
| --- | --- |
| BR-01 | Persist profile ID/version and appearance in Settings. On upgrade, carry the existing browser preference forward when available. Future agency profiles must fit the same interface without changing case data structures. |
| BR-02 | Use semantic tokens for confirmation, adverse finding, explicit failure, pending/unknown, selection, identity, paper, and report ink. Replace hardcoded green success treatments throughout the application with blue confirmation treatments. |
| BR-03 | Keep status dimensions independent. An asset can have a blue confirmed association and red critical/known-exploitation indicator simultaneously. No confirmation, completed outreach, or missing risk data implies remediation or safety. |
| BR-04 | Use a separate selection outline/halo or shape so selecting a map node does not erase its status meaning. Unreviewed observations can remain faint, but must have an accessible inventory and readable selected state. |
| BR-05 | Apply the same role mappings to ECLIPSE, leads, entity/case pages, source details, builder, progress cards, and completion views. Gold is decorative identity, never a substitute for warning or success. |
| BR-06 | All generated document text uses `#000000`: headings, narrative, tables, citations, links, graphic labels, badges, dates, page numbers, and work-log text. The sole standards-based color exception is TLP marking. Report paper is white in every appearance. |
| BR-07 | Permit restrained blue/red/gold graphics. Put black labels on white or sufficiently light areas; do not retain white text on dark charts in the report. Do not grayscale/recolor original evidence images; captions follow the black-text rule. |
| BR-08 | Document preview uses the actual print rendering, including TLP. Theme-aware application exhibit views may be offered separately, but are not labeled as the exact document preview. SVG, PDF, DOCX, and PNG fallback use the same print token resolution. |
| BR-09 | Use explicit labels/shapes in addition to color. Target WCAG 2.2 AA text contrast (4.5:1 normal; 3:1 large) and meaningful graphic/control contrast (3:1), with keyboard focus, 200% zoom, and reduced-motion behavior. No claim of complete accessibility certification follows from these checks alone. [S9–S10] |
| BR-10 | Branding changes cannot rewrite the issuer identity or established paragraphs. Appearance-only changes do not invalidate review. Explicit adoption of a different document branding/palette version requires renewed validation for affected sections. Historical report bytes remain unchanged. |

## 4. TLP handling and marking

The requested yellow sharing designation maps to **TLP:AMBER** under FIRST TLP 2.0. TLP is a sharing-boundary label, not a formal security classification. The standard requires document labels in every page's header and footer; right alignment and 12-point-or-larger type are recommended. This product adopts both recommendations as requirements. Use `#FFC000` text on `#000000` for the marking. [S8]

| ID | Requirement |
| --- | --- |
| TLP-01 | Set the active workspace handling policy to `TLP:AMBER`, standard version `2.0`. Display the label in persistent application chrome and on standalone case/source/report views, including loading, empty, and error states where case information is visible. |
| TLP-02 | Place the marking at the **top right and bottom right of every generated document page**, at a minimum 12 points at final printed size. Apply to main notification, appendix, internal work log, closing report, and standalone exhibit pages. Reserve layout space so marks cannot overlap content or page numbers. |
| TLP-03 | The amber-on-black TLP label is an explicit exception to BR-06. Agency profile, dark/light mode, grayscale styles, ordinary hyperlink styles, or SVG scaling must not unintentionally replace its text, colors, or final size. |
| TLP-04 | The marking applies to the entire notification, including its appendix. Include a concise sharing explanation and source guidance reference without modifying established paragraph bodies. Do not substitute `TLP:AMBER+STRICT` or invent `TLP:YELLOW`. |
| TLP-05 | Store handling label, standard version, policy version, and additional source restrictions in case/report metadata and machine-readable export envelopes/manifests. Do not inject metadata into captured source bytes or alter original workbook hashes. |
| TLP-06 | Preserve stricter or additional source-origin restrictions. The workspace default does not authorize a downgrade or broader sharing of imported material. Surface an incompatible source restriction before building a recipient package and require an explicit documented disposition; do not silently relabel it. |
| TLP-07 | Pin the handling policy with each certified revision. Existing certified packages remain byte-identical; if they need a new marking, create a new report revision. The application can show current workspace handling alongside an older artifact's recorded marking without claiming the old bytes changed. |
| TLP-08 | Place TLP on both exported document pages and machine-readable package metadata. ZIP archives include a readable handling notice. A future email-draft feature must place the label before content and in the proposed subject; this release does not add automated sending. |

Application placement and machine-readable envelopes are product decisions implementing the user's system-wide policy; FIRST does not prescribe a particular web application layout. The release must not imply that TLP is an encryption mechanism or replace existing local access controls.

## 5. Report composition and Companion Appendix

### 5.1 Required reading order

| Builder section | Main-report content | Full detail placement |
| --- | --- | --- |
| Introduction | Letterhead, fixed addressee, configured sender/date/subject, established introduction, Summary Exhibit | Appendix A for complete observations and asset inventory |
| Vulnerabilities | Fixed generated finding narrative; Vulnerability Exhibit with distinct findings, source-labeled metrics, exploitation/impact indicators, concise source references | Appendix C for full published descriptions, conditions, metrics, intelligence assessments, and captured case-specific CVE data |
| Attribution | Established attribution paragraph; Attribution Exhibit; concise source references | Appendix B for all accepted/candidate evidence, method, matched fields, source contents, and actual timestamps |
| Information | Selected established explainers, protective measures, financial-crime context, limitations, responsibility language, and general resources | Appendix D for source register and supporting materials |
| Closing | Established closing and configured signature; no contact email/name re-entry in builder | **Explicit page break after the signature**, then Companion Appendix |

Attribution, Information, and Closing retain their existing new-page boundaries. The appendix begins on its own page after Closing. The three exhibits are components, not a mandate that the full notification has only three pages. Full detail must not be squeezed into the main pages to achieve a cosmetic page count.

### 5.2 Exhibit requirements

| ID | Requirement |
| --- | --- |
| EX-01 | Generate all exhibits from one saved, case-scoped report content model. Screen selection, table pagination, map viewport, and search filters must not change the notification's included data. |
| EX-02 | Define counts explicitly: unique IP; endpoint as IP+transport+port when supplied; observation as a source row; CVE as a distinct identifier; EOL finding as its recorded lifecycle condition; supporting attribution as an accepted evidence association. Retain report-specific endpoint roles for nonstandard reports. |
| EX-03 | Summary shows reporting period, report type/source, scope counts, product/version groups, and observation history where useful. Repeated observations are not additional assets or proof of continuous exposure. Overlapping group totals are labeled nonadditive. |
| EX-04 | Small cases may show individual assets; large cases aggregate by product, version, finding, or service. Every aggregate links to an exact set of observations and appendix entries. No unlabeled top-N omission, guessed remainder, or identity loss. |
| EX-05 | Attribution shows the exact saved supporting relationship and its source, matched field, decision actor/time, and retrieval time. Show, for example, **70 reported assets / 1 supporting attribution**, with candidate evidence separately counted. |
| EX-06 | Vulnerability shows distinct CVEs and EOL conditions separately, reported product/version, published metric source/version, exposure count, relevant conditions, and independent exploitation/impact indicators. No numeric CVSS is invented for EOL. |
| EX-07 | Use a one-page target for each exhibit where readable. Aggregate before adding pages, but never crop necessary identifiers, truncate material qualifiers, or reduce essential text below the configured print minimum (initial target 10 points; TLP always at least 12). Use continuation pages if needed. |
| EX-08 | Every exhibit has a stable exhibit ID, report revision, appendix references, source citation links, and accessible textual alternative. An excerpt never implies that it is the full source description. The appendix holds full text and fields. |
| EX-09 | Expose a document preview and expandable/keyboard-accessible supporting detail. Source and validation timestamps are separate; missing historical values remain explicitly unavailable. The UI does not create new lookup dates when displaying saved evidence. |
| EX-10 | Emit self-contained SVG masters plus compatible raster fallbacks from a deterministic layout model. Use XML-safe text, safe links, fixed dimensions, and no executable code or remote resources in exported graphics. Preserve exact exported masters at certification. |

### 5.3 Companion Appendix requirements

| ID | Requirement |
| --- | --- |
| AP-01 | Include the Companion Appendix by default in both recipient PDF and DOCX **after the closing and signature**, not as a separate download required to understand the report. Continue page numbering and TLP on every appendix page. |
| AP-02 | Start with an appendix index: A—Reported assets and observations; B—Attribution records; C—Vulnerability and exploitation records; D—References and supporting material. Use stable entry IDs and reciprocal exhibit/appendix links. |
| AP-03 | Appendix A lists every included asset and every underlying observation, including repeated scan rows. Render a readable field/value breakdown with original field names and values, source workbook/sheet/row, source scan timestamp, report/profile identity, and import provenance. Do not replace the full list with counts or require the reader to parse JSON. |
| AP-04 | Preserve values line by line: zero, false, arrays, nested structures, long strings, and multilingual text. Nested data uses stable paths and indexes. Distinguish supplied empty/null values from fields absent in the source. Long values wrap or continue; no ellipses as a substitute for retained content. |
| AP-05 | Appendix B includes case-relevant RDAP/network/entity/DNS records and analyst attribution decisions, with source, retrieval time, decision time/actor, exact matching fields, and all retained candidates/failed attempts in that case's evidence history. Label accepted, candidate, failed, and superseded records so inclusion does not imply qualification. |
| AP-06 | Appendix C includes full selected published CVE descriptions verbatim apart from display whitespace, applicable source-stated conditions/ranges, all retained source-specific scores and selected intelligence assessments, their dates, raw values, and provenance. Include each complete case-relevant source record or its readable structured equivalent. |
| AP-07 | Include all case-relevant information obtained for the notification, not unrelated records in a shared cache or the entire global KEV catalog. For shared feeds include the complete matching entry, catalog metadata, and retained response reference/hash; the complete captured feed remains in internal evidence storage/package where applicable. An unlisted result includes the checked catalog's identity and outcome. |
| AP-08 | Deduplicate identical source snapshots by ID/hash, but retain every observation and every relationship to the reused source. A source is printed once with all referencing entry IDs. Differing source revisions/assessments remain distinguishable. |
| AP-09 | Include source publisher, title, public/request URL as appropriate, source dates, actual retrieval timestamp, original record ID/path, and integrity reference. Provide a complete numbered source register. Keep general recommended resources distinct from evidentiary citations. |
| AP-10 | Original screenshots are optional, captioned, and included after their structured evidence. Preserve original images separately; fitting an image on a page must not overwrite it. A source record with embedded HTML/scripts is rendered as inert readable data, not executed. |
| AP-11 | Partition the appendix by the existing five section owners for review. Observation/summary content belongs to Introduction; CVE/impact content to Vulnerabilities; attribution material to Attribution; advisory source material to Information; delivery closing copy to Closing. The appendix is not a sixth workflow stage or independent competing certification system. |
| AP-12 | Frozen review covers full appendix content as well as compact exhibits. A change to a supporting field, source selection, restriction, or appendix inclusion cannot pass unnoticed because the front-page totals stayed the same. |
| AP-13 | Keep the recipient appendix separate from the internal work log. Certification chronology, operational contact attempts, credentials, application internals, and unrelated cases are not accidentally appended by a blanket database dump. The appendix is complete for the notification's source/evidence scope; internal workflow records remain in the internal package. |
| AP-14 | Provide native searchable/selectable PDF text and native editable DOCX text for full descriptions and field tables. Repeat headers, keep headings with content, wrap long fields, and permit natural multi-page flow. A recipient need not have Companion, JSON tools, or live URLs to inspect the details. |

## 6. Exploitation and impact enrichment

### 6.1 Signal definitions and display

| Signal | Stored meaning | Default display |
| --- | --- | --- |
| KEV membership | Exact CVE match in an identified complete catalog | Known exploited · CISA KEV; inclusion date |
| KEV nonmembership | Successful full-catalog lookup with no exact match | Not listed in retrieved catalog; catalog date |
| Ransomware Known | CISA explicitly supplies `Known` | Known ransomware use |
| Ransomware Unknown | CISA explicitly supplies `Unknown` | Ransomware use unconfirmed by CISA |
| Ransomware missing | Field absent or no matching KEV entry | Not supplied / No CISA assessment in this catalog |
| SSVC active | Source's dated active-exploitation assessment | Active exploitation reported; publisher and assessment date |
| SSVC poc | Source reports public proof of concept or a well-known exploitation method | Public PoC / known exploitation method |
| SSVC none | Source assessment reports no exploitation evidence | No exploitation evidence reported in this assessment |
| Potential impact | Source-supported consequence with qualifiers | For example, arbitrary code execution, information disclosure, authentication bypass |
| EPSS | Dated probability and corresponding percentile; score date and retrieval time retained separately | EPSS percentage and score date; percentile separately labeled |

KEV membership records known exploitation; it does not independently establish current activity today. A missing assessment is not SSVC `none`. Unknown ransomware use is not a negative finding. An EPSS percentage is not the likelihood that this recipient will be compromised. [S1–S6]

| ID | Requirement |
| --- | --- |
| CV-01 | Extend `cve_sources.py` and existing captured-source storage. Reuse enrichment per unique CVE/provider across cases, retaining immutable revisions. Do not fetch the entire KEV feed for every CVE. |
| CV-02 | Preserve NVD-first descriptions and CVE Program fallback, while retrieving supplementary CVE/ADP information when needed even if NVD succeeded. Existing fallback-only control flow must not prevent SSVC enrichment. |
| CV-03 | Validate exact CVE identity, source structure, response bounds, source state, and catalog completeness before normalization. A failed/partial/malformed response or absent NVD CISA field cannot establish KEV nonmembership. Preserve catalog version/release time and matching entry. |
| CV-04 | Normalize `knownRansomwareCampaignUse` independently. Retain original values and availability reasons. Unknown future values remain visible for adapter review; do not coerce them to known/false. |
| CV-05 | Parse SSVC from CVE additional-provider metrics and NVD SSVC metrics where supplied. Preserve publisher, role, scheme version, assessment timestamp, raw options, and source revision. Normalize only supported spelling/case variations. |
| CV-06 | Retain multiple/conflicting assessments. Prefer an explicitly selected assessment; otherwise use a documented deterministic preference, initially CISA-origin assessments ordered by actual assessment timestamp. The selection belongs to the case/draft/report revision, not mutable shared CVE-bank state. Show differing assessments in details/appendix. Retrieval time must not masquerade as assessment time. |
| CV-07 | Keep KEV, ransomware, SSVC, impact, and EPSS independent. Never collapse them into one mutually exclusive compromise-type field. Do not infer ransomware/BEC/RCE from a high CVSS, a CWE alone, or SSVC technical impact `total`. |
| CV-08 | Potential-impact labels require source text and an extraction basis: explicit structured data, reviewed normalization, or identified analyst interpretation. Preserve deployment/authentication/OS/feature conditions. Ambiguous text remains reviewable without an invented label. An AI service is not required. |
| CV-09 | Retain CVE reference tags and optional published exploitation information. A reference tagged as an exploit is supporting metadata, not proof of active exploitation. Do not retrieve/run exploit code to qualify a notification. |
| CV-10 | Preserve all source-specific CVSS assessments with score, version, severity, vector, and contributor. Selected summaries and full appendix values agree; differing assessments remain labeled rather than overwritten. |
| CV-11 | Preserve EPSS probability, percentile, score date, and retrieval time separately. A real zero displays as zero; missing values are null with reasons. A low EPSS score cannot suppress KEV/ransomware indicators. |
| CV-12 | Distinguish acquisition outcomes from substantive values: not requested, success, not found, unavailable, rate limited, invalid response. Failed refreshes retain the last intact response and its original dates, with the failed attempt and its actual attempt time separately visible. No-response attempts have no response hash/retrieval timestamp; never fabricate these from the attempt time. |
| CV-13 | Make refresh asynchronous, cancellable between requests, bounded, cached, and respectful of provider rate limits and Retry-After. One provider's outage must not discard other sources or block offline document rendering. Do not change a draft's selected evidence silently. |
| CV-14 | Show Exploitation & impact in CVE details and compact exhibit indicators. Add KEV/ransomware filters to relevant queues and ECLIPSE views without changing the critical-only outreach default. Indicator labels describe the CVE, not the recipient's compromise status. |
| CV-15 | Freeze selected intelligence revisions, descriptions, display labels, source dates, retrieval times, citations, and raw-response hashes with certification. New source data enters the shared bank; explicit adoption identifies changed fields and makes dependent sections stale. |
| CV-16 | Missing optional scores/intelligence alone do not prevent certification when displayed accurately. An unavailable/unresolved lookup may use a documented official-source fallback or an explicit exclusion with a reason. Reserved/rejected identifiers remain retained and visibly dispositioned; fallback must not present them as published vulnerabilities. Only a subsequently captured authoritative record establishing published status can change that treatment. Preserve original observations and status history. |

## 7. Established wording and citations

| ID | Requirement |
| --- | --- |
| TX-01 | Preserve the controlled text in `workbench/approved_template.py`, revision `approved-2026-11-06-v1`, including introduction, fixed narrative sentences, attribution, advisory/fraud paragraphs, responsibility, resources, and closing. Do not silently correct spelling, grammar, statistics, or wording while changing the layout. |
| TX-02 | Populate only defined narrative insertables from saved case/entity/settings data. Preserve IP↔hostname↔service↔product/version↔finding relationships. Entity city/state comes from the entity profile, not inferred IP geolocation. Missing values remain explicit. |
| TX-03 | Source descriptions are published source text; analyst notes and compact impact labels are separate. Keep full descriptions in the appendix without substantive rewriting. Compact exhibits reference those entries. |
| TX-04 | Store newly proposed scope statements as versioned optional blocks with provenance/status. Selecting a new block does not overwrite an established paragraph. Changes to recurring statistics require an explicit new text/source revision rather than a live substitution. |
| TX-05 | Use numbered citations in first-use order across main report and appendix. Reuse a number for the same source snapshot; distinguish different source revisions. Resolve all figure labels and appendix cross-references after pagination. |
| TX-06 | Attribute actual publishers/contributors: a CNA description delivered through NVD is not automatically NIST-authored. Keep public record/advisory URLs for recipient references, and request URLs/field paths/hashes in the detailed provenance. |
| TX-07 | Preserve per-case insertable corrections and source selections across regeneration. No builder field may override controlled prose, report addressee, or configured sender. Validate those rules on the backend, not only by hiding controls. |
| TX-08 | Keep EOL-only and mixed notifications valid. Do not invent CVEs for unsupported software. For deliberate noncritical outreach, an appropriate separately versioned narrative must be selected; do not substitute a noncritical value into an unchanged sentence asserting a critical finding. |

## 8. Persistent review, certification, and history

| ID | Requirement |
| --- | --- |
| RV-01 | Extend `SectionReviews` and existing tables/events. Each of the five sections displays draft/validated/stale state, revision, configured author, and validation timestamp. Full content remains readable while editing is frozen. |
| RV-02 | A validation freezes section content and dependency IDs/hashes, including its appendix partitions, selected source revisions, exhibit SVG/fallback or their immutable artifact references, render version, print palette, and TLP policy. |
| RV-03 | Reopening requires a nonblank reason and appends an actor/time event. Keep earlier validated contents and graphic bytes; do not rerender an old revision against new data or new theme settings. |
| RV-04 | Dependency changes mark affected validations stale without silently replacing or unlocking frozen data. Display a field/source-level change explanation. Unrelated appearance, map selection, contact planning, or another case must not invalidate a section. |
| RV-05 | Existing stale-write/concurrency guards remain enforced. Reject an attempt to validate/certify a stale case revision. No final package can combine section content from inconsistent case snapshots. |
| RV-06 | Final certification requires all five current sections, their appendix partitions, required attribution/dispositions, and applicable handling checks. The final action generates/stages and verifies the package before committing workflow state. |
| RV-07 | Include final certification actor/time, section chronology, attribution decision chronology, and reopened reasons in the internal work log/JSON. Use configured identity rather than the prototype's Demo analyst. Hashes support integrity, not an assertion of cryptographic identity/signature. |
| RV-08 | Validation and history survive refresh, browser restart, process restart, backup, and restore. Source refresh never alters already certified or delivered files. Changes after certification create a new report revision and renewed review. |
| RV-09 | Store UTC event times with offsets/zone context; display the configured local zone explicitly and use unambiguous export dates. Scan time, retrieval time, assessment date, and validation/certification time remain distinct. |

### 8.1 Dependency ownership

| Changed input | Required renewed validation |
| --- | --- |
| Included observation/asset membership | Introduction and all other sections whose narrative, finding list, attribution coverage, or appendix content changes |
| Selected CVE description/KEV/ransomware/SSVC/EPSS/impact revision | Vulnerabilities; Introduction if its derived display changes; affected citation/appendix partitions |
| Supporting attribution/result or reviewer decision | Attribution; Introduction/narrative if identity or scope changes |
| Selected advisory block or its source | Information and its appendix sources |
| Issuer/signature identity | Introduction/Closing and any dependent rendered content |
| Document brand, print palette, TLP policy, or renderer version adopted into draft | Every section whose exported bytes/content change |
| Application appearance only | None |
| Contact attempt after certification | No recipient report section unless report content is explicitly revised; append to case work log |

## 9. Logical records and component contracts

Extend existing SQLite records and versioned JSON snapshots where practical. These are logical contracts, not a requirement to create a table for every nested object or replace SQLite with another database.

| Record | Required fields/relationships |
| --- | --- |
| BrandProfile | Stable ID/version, display name, supplied palette/provenance, semantic token mappings, print policy version, documented palette discrepancies |
| WorkspacePresentation | BrandProfile reference, appearance preference, accessibility/motion preferences; independent of notification content |
| HandlingPolicy | Label `TLP:AMBER`, standard version 2.0, policy version, source restrictions, header/footer presentation |
| ReportProfile | Report type, source schema commit/hash, adapter version, field map, endpoint roles, eligibility/extraction capability |
| Observation | Original file/sheet/row, raw fields, scan time, normalized endpoint/product/finding references, profile version, retention/eligibility flags |
| SourceSnapshot | Captured response identity; provider, public/request URLs, actual response retrieval time, source dates, catalog metadata if applicable, raw bytes/path/hash, adapter version, inherited restrictions, and validation outcome |
| RetrievalAttempt | Provider/request identity, attempted/completed timestamps, acquisition outcome/error, nullable captured-response snapshot ID, and last usable snapshot reference. No-response attempts have no fabricated response bytes/hash. |
| CveIntelligenceRevision | CVE ID; source snapshots; KEV membership/date; ransomware raw/normalized value and availability; SSVC assessments with dates/providers; reviewed impacts/conditions; CVSS collection; EPSS probability/percentile/date; immutable available assessment IDs |
| AttributionAssociation | Original reported IP/root/group; supporting result/entry IDs; evidence IP/range/source; method; exact matching fields; accepted/candidate/failed state; decision actor/time; retrieval time |
| ExhibitModel | Type/ID, included observation/finding/evidence IDs, aggregates, composition choice, appendix entry references, selected source versions, display labels, render/print versions |
| AppendixEntry | Stable entry ID/type, parent section, source/observation IDs, ordered field paths/values, source metadata, incoming exhibit/citation references, inclusion/disposition status |
| SectionValidation | Existing section revision plus immutable model/artifact/dependency references, author/time, content hash, state and event linkage |
| ReportSnapshot | Existing case-scoped content plus ordered exhibits/appendix, citation register, intelligence revision references, case-selected assessment IDs, controlled text revision, branding/handling/render versions, inclusion decisions |
| ReportPackage | PDF, DOCX, snapshot JSON, exhibits/fallbacks, appendix index, source evidence, work log, chronology, handling notice, integrity manifest |

Every nullable intelligence value carries availability context. Do not represent all source failures and unknown assessments with a single false Boolean. Preserve unknown source fields and raw provider values for future adapters.

### 9.1 Implementation boundaries

1. **Intake/profile adapters** preserve and normalize supplied rows; they do not fetch CVE intelligence or render reports.
2. **Attribution Module** establishes candidate/supported associations and records evidence; it does not claim vulnerability applicability.
3. **Source adapters/CVE bank** retrieve and version public records once per provider/CVE; they do not edit a case's pinned selections.
4. **Report assembler** creates an immutable, case-scoped content model, counts, citations, and appendix mappings from saved records.
5. **Exhibit renderer** consumes that model and a print policy; no live requests or mutable global case state.
6. **PDF/DOCX renderers** assemble letter sections, graphic masters, native appendix text, TLP, and navigation from the same snapshot.
7. **Section validation and package finalization** own review, dependency checks, immutable history, and workflow transitions.

New backend/API contracts shall expose source retrieval state, available/selected revisions, appendix inclusion and ownership, presentation settings, and immutable artifact retrieval through the existing application. Reuse current case IDs and optimistic-concurrency guards. Rendering endpoints never implicitly refresh sources. UI preview and final output use the server-assembled snapshot; a browser-supplied score, sender, TLP value, or certification result is not authoritative.

## 10. Export, performance, security, and Windows operation

| ID | Requirement |
| --- | --- |
| OP-01 | Operate locally on the supported Windows x64 workstation. Preserve `%LOCALAPPDATA%\\OutreachWorkbench\\data`, existing workspace selection, IDs, backups, and upgrade identity. New release naming must not strand the old data directory. |
| OP-02 | Read, preview, validate, and render from saved records offline. Network access is confined to explicit source/intake services; document rendering and theme assets use bundled resources. No cloud AI, Word, or LibreOffice dependency is required to generate reports. |
| OP-03 | Retain ReportLab/python-docx as integration points unless a renderer change has a demonstrated packaging need. Any additional vector/font/browser dependency must be bundled and tested offline; do not turn the prototype's development browser into an undocumented workstation prerequisite. |
| OP-04 | PDF retains vector graphics where supported and searchable/selectable generated text. DOCX embeds SVG with compatible PNG fallback, while body/appendix text stays native text. PDF and DOCX have equivalent content/citations/markings; identical pagination across viewers is not required. |
| OP-05 | Place TLP outside scalable exhibit content or compensate explicitly so final size remains at least 12 points. Avoid duplicate document/exhibit marking when embedded, but mark standalone exported exhibits at both header/footer positions. |
| OP-06 | Generate asset/observation and source indexes once per snapshot. Handle large input in bounded batches; progress shows truthful phase and counts. Interruptible background enrichment and rendering must not freeze navigation. |
| OP-07 | Performance acceptance fixture: 10,000 retained scan rows and 1,000 unique CVEs on a documented Windows reference workstation. Measure local parse/group/render phases separately from network latency. Target usable cached dashboard/queue within 5 seconds and 70-asset main preview within 3 seconds after assembly; publish measurements and any unresolved misses. Do not hide omitted rows to meet targets. |
| OP-08 | Escape spreadsheet/source text in HTML, SVG, PDF, and DOCX. No execution of formulas/macros, arbitrary fetched scripts, or embedded remote resources. Sanitize export filenames and links; enforce size/time limits and the existing local server protections. |
| OP-09 | If a tabular companion export is supplied, preserve values safely without triggering spreadsheet formulas. The readable appendix remains required and cannot be replaced by that export. |
| OP-10 | Preserve private case data outside the program directory. Distributed demos/tests use synthetic or explicitly sanitized fixtures; never ship the user's real workbook, source cache, entity details, or work history in the installer. |
| OP-11 | Use transactional numbered migrations with a pre-upgrade backup. Preserve existing drafts, screenshots, source responses, certifications, delivery/closing history, and old downloadable output. Interrupted migration/package builds must recover without falsely advancing the case. |
| OP-12 | Produce a Windows installer and source/development distribution for the actual release. Test clean install, upgrade from 0.6.0, offline startup/export, relaunch, backup/restore, and uninstall retaining case data. Record signing status honestly; requirements completion alone is not installer completion. |

## 11. Implementation map and delivery sequence

| Work package | Existing integration points | Required output |
| --- | --- | --- |
| 1. Data/presentation contracts | `store.py`, `api.py`, `migrations.py`, `theme.js` | Versioned profiles, appearance persistence, handling policy, source/appendix contracts; migration only as needed |
| 2. Report profiles/intelligence | `intake_service.py`, `cve_sources.py`, Attribution Module bridge | Full-row/profile preservation, supplementary ADP/SSVC, ransomware/impact normalization, dated cache revisions |
| 3. Shared composition | `report_composition.py`, `approved_template.py`, new exhibit/appendix components | One snapshot with three exhibits, five section owners, full appendix, citations, fixed wording |
| 4. Rendering | `reporting.py`, shared renderer, DOCX/PDF styles | Black text, TLP every page, vector/fallback exhibits, native appendix text, complete offline outputs |
| 5. Review integration | `section_validation.py`, `work_log.py`, `cases.py`, `closing.py` | Dependency-aware freezes, persistent chronology, safe package finalization and unchanged historical bytes |
| 6. Application presentation | `style.css`, `theme.js`, `app.js`, `cases.js`, `eclipse.css` and ECLIPSE views | Coherent brand/appearance, blue confirmation/red adverse semantics, TLP, source details, appendix preview |
| 7. Release assurance | Existing Python/UI/report/migration tests, installer scripts | Acceptance evidence, visual review, Windows install/upgrade proof, versioned artifacts/release notes |

Implement vertical slices rather than a separate replacement application: first one real saved case through composition/appendix/print, then intelligence and profile coverage, then all themes and upgrade cases. Keep the prototype as a fixture/reference, not a second production database or review subsystem.

## 12. Acceptance test matrix

All criteria are required for release unless explicitly described as a recorded performance target. These are future verification requirements, not claims of completed implementation.

| ID | Scenario and required evidence | Requirements |
| --- | --- | --- |
| AC-01 | Upgrade a 0.6.0 workspace: IDs, files, source hashes, entity/case boundaries, and historical packages remain unchanged. | WF-02,06; OP-01,11 |
| AC-02 | Four visible stages and Completed archive remain correct; send attempt is not delivery; exact-revision delivery and close-without-delivery stay distinct. | WF-01,04–05 |
| AC-03 | Fixed addressee, configured sender, all controlled paragraphs, and narrative sentences remain identical; only supported token values vary. | WF-03; TX-01–02,07 |
| AC-04 | A workbook with unknown columns, reordered headers, zero/false/null values, composite versions, and blank rows retains full source fidelity. | IN-01–04,08 |
| AC-05 | CVE-only versionless entry, EOL entry, numeric subdomain, non-public IP, unknown report type, and out-of-scope row follow their distinct profile/eligibility rules without data loss. | IN-03,06–10 |
| AC-06 | One accepted attribution supports a 70-asset group; output shows one supporting match and all 70 reported assets, never 70 verified ownership claims. | AT-05–07; EX-05 |
| AC-07 | Forward DNS fallback, failed PTR, partial network-name candidate, exact domain boundary, and manual acceptance preserve their actual evidence/basis/time. | AT-01–04 |
| AC-08 | Changing profile/appearance leaves observations, workflow, and attribution decisions unchanged. Existing appearance survives upgrade. | BR-01,10 |
| AC-09 | Same asset shows blue attribution confirmation and red vulnerability/KEV state; neutral unknown remains neutral; selection does not hide status. | BR-02–05 |
| AC-10 | Inspect SVG/PDF text colors, DOCX runs/styles/hyperlinks, and PNG fallbacks: all generated text black except explicit TLP. Original evidence bytes remain unchanged. | BR-06–08; TLP-03 |
| AC-11 | Light/dark/USSS/Companion, keyboard navigation, 200% zoom, reduced motion, and contrast checks pass for primary workflows; document preview remains white-paper print output. | BR-08–09 |
| AC-12 | Every page of main report, appendix, work log, and closing PDF/DOCX has TLP:AMBER top right and bottom right, amber-on-black, at least 12 points. Include first, continuation, and last pages. | TLP-01–04; OP-05 |
| AC-13 | Theme/SVG scaling cannot alter TLP. Standalone exhibits are marked; embedded exhibits do not create duplicate or conflicting page labels. | TLP-03; OP-05 |
| AC-14 | Export manifest/envelope carries TLP and restrictions; original raw-source hashes remain intact. Stricter source restrictions are surfaced rather than silently downgraded. | TLP-05–08 |
| AC-15 | Small 3-IP case and 70-IP/84-endpoint/336-observation case produce accurate counts and complete mappings. Group counts are explicitly nonadditive where appropriate. | EX-01–04 |
| AC-16 | Large assets/CVEs/long identifiers aggregate or continue without clipping, tiny text, lost qualifiers, or hidden findings. Screen filters do not alter exported scope. | EX-04,07–09 |
| AC-17 | Companion Appendix begins after the signature on a new page, in both formats; section and page references resolve. | AP-01–02; TX-05 |
| AC-18 | Appendix contains all 336 fixture observations, not only 70 unique IPs. Every supplied row field and provenance is readable and traceable. | AP-03–04 |
| AC-19 | Nested/long/multiline/Unicode values and true zero/false/null/empty states are preserved with stable paths; no display truncation loses content. | AP-04,14 |
| AC-20 | Attribution appendix distinguishes accepted, candidate, failed, and superseded evidence with matching fields and separate decision/retrieval times. | AP-05; AT-04–05 |
| AC-21 | Full selected source descriptions and case-specific CVE/provider records appear with actual contributors, conditions, dates, and source references. | AP-06–09; TX-03,06 |
| AC-22 | One reused source prints once with all links intact; unrelated KEV entries, other entities, and internal contact logs do not leak into the recipient appendix. | AP-07–08,13 |
| AC-23 | Body/exhibit source markers resolve to appendix/register entries; references work offline as readable text and as links when online. | AP-02,09,14; TX-05–06 |
| AC-24 | A known-KEV/known-ransomware fixture displays both independently with exact raw values, inclusion date, source snapshot, and red graphics. | CV-01,03–04,07,14 |
| AC-25 | Ransomware Unknown, absent field, no KEV entry, unrequested lookup, malformed response, and request failure remain distinguishable; none becomes No ransomware use. | CV-03–04,12 |
| AC-26 | Only a successful complete-catalog check permits Not listed; empty/malformed/partial catalog and missing NVD fields cannot. | CV-03 |
| AC-27 | NVD-success case still obtains available supplemental CISA ADP/SSVC; multiple assessments retain provider, assessment date, raw options, and deterministic selection. Choosing another assessment in case A leaves case B's selected evidence unchanged. | CV-02,05–06 |
| AC-28 | SSVC poc is not automatically Public exploit code available; old active is shown with its assessment date; missing is not none. | CV-05–07 |
| AC-29 | Conditional impact preserves Windows/CGI/authentication or similar qualifiers. CWE/high CVSS/total alone cannot invent RCE, BEC, or ransomware. | CV-07–09 |
| AC-30 | Differing CVSS sources, EPSS probability versus percentile, genuine zero, and missing values remain accurate and consistent throughout output. Low EPSS never hides KEV. | CV-10–11 |
| AC-31 | Two cases sharing a CVE reuse evidence. Rate limit/offline/failed refresh preserves last usable data and original retrieval dates. The failed attempt has a separate timestamp and no invented response hash or evidence retrieval time. | CV-01,12–13; OP-02 |
| AC-32 | Refresh changes the bank but not selected draft/certified evidence. Explicit adoption shows differences and invalidates only dependent reviews. | CV-15; RV-04 |
| AC-33 | EOL-only/mixed cases do not invent CVEs. Unavailable lookups can use a documented official fallback; reserved/rejected identifiers cannot be overridden into published status by fallback. Optional missing metrics do not independently block certification. | CV-16; TX-08 |
| AC-34 | Five section freezes persist across app/browser restart; author/time are real configured identity; reopening requires a reason and retains prior exact content/graphics. | RV-01–03,07–09 |
| AC-35 | An appendix-only source-field change makes its owner stale even when summary counts remain unchanged. Another case/contact attempt/appearance-only change does not. | AP-11–12; RV-02,04 |
| AC-36 | Concurrent stale save/certification is rejected. Interrupted output staging does not advance workflow or lose previous valid packages. | RV-05–06; OP-11 |
| AC-37 | PDF/DOCX use the same snapshot, exhibit data, citations, appendix entries, and handling policy. Required new-page boundaries and readable full details pass visual review. | EX-10; AP-14; OP-04 |
| AC-38 | Historical certified PDF/DOCX/SVG/source hashes are unchanged after bank refresh, theme change, upgrade, reopen, and later delivery/closing events. | TLP-07; RV-03,08 |
| AC-39 | A case with no screenshots certifies when structured evidence and existing readiness requirements are met; optional images remain usable. | WF-07; AP-10 |
| AC-40 | Escaped malicious-looking source strings render inertly; no external asset requests occur during offline preview/export. Source files and internal data stay intact. | EX-10; AP-10; OP-02,08 |
| AC-41 | ECLIPSE retains all eligible/excluded/unplaced inventory and accurate geographic/ASN labels; new filters do not turn provider association into business ownership or compromise. | IN-03,10; BR-04–05; CV-14 |
| AC-42 | Benchmark documented Windows reference system with 10,000 rows/1,000 CVEs; report timings, memory, responsiveness, and any target misses separately from network latency. | OP-06–07 |
| AC-43 | Clean Windows install, 0.6.0 upgrade, offline startup/export, relaunch, backup/restore, and uninstall retaining user data succeed. | OP-01–03,10–12 |
| AC-44 | Extract distribution contents and verify real workbooks, private source caches, credentials, contact records, and unrelated user artifacts are absent. | OP-10 |
| AC-45 | Package integrity verification covers all recipient/internal artifacts and snapshot relationships; recipient appendix is complete without accidentally including internal chronology. | AP-13; RV-06–08; section 9 |
| AC-46 | Import Critical, High, and unspecified-severity rows: retain all three; only the profile-supported Critical row enters the default outreach queue. KEV/EOL alone does not promote the other rows. Targeted inclusion records an override and uses an appropriate narrative. | IN-11; TX-08 |

## 13. Definition of done and release boundaries

v0.7.0 is complete when a real locally saved, qualified case can flow through the existing five-section builder into a branded, correctly marked PDF/DOCX notification with three adaptive exhibits and a complete post-signature appendix; all values are tied to saved sources, all required reviews survive restart, delivery/closing remain correct, and historical outputs remain unchanged.

Release evidence must include the acceptance matrix results, representative visual PDFs/Word renderings, black-text/TLP checks, source and package integrity checks, migration/backup results, and actual Windows installation/export results. A Linux-rendered DOCX or a prototype screenshot alone is not native Windows acceptance. Document any remaining limitations instead of calling untested behavior complete.

### Explicit boundaries

- This increment does not add vulnerability exploitation/testing, unsolicited outbound messages, a cloud deployment, a multi-user identity service, or automatic remediation.
- It does not make CVE applicability or recipient compromise determination a prerequisite for the analyst's notification. Published conditions are shown for recipient validation.
- Additional agency profiles, automated Secretary of State collection, and fully interpreted outreach workflows for every non-vulnerability Shadowserver family remain future adapters/features. Full raw retention and extensible profiles are required now.
- TLP, controlled wording, and source provenance must not be marketed as legal approval, an official classification determination, or a cryptographic signature.
- Default red shades and digital palette discrepancy notes are implementation defaults open to visual refinement; they do not block the architecture. The supplied hex values govern until explicitly corrected.

## 14. Baseline provenance and primary references

### Baseline artifacts

- **[B1]** [Shadowserver Companion 0.6.0 source distribution](https://chatgpt.com/library?file_id=libfile_533e5e20f94c8191b338665ceb5c632c&account_id=personal), saved version 9. Inspected `VERSION`, `CHANGELOG.md`, `REPORT_REQUIREMENTS.md`, current source/cache/render/review/settings code, and release documentation. This document's baseline claims are static inspection, not a rerun of the entire application test suite.
- **[B2]** [Three-exhibit prototype](https://chatgpt.com/library?file_id=libfile_907a333b0cac8191b81e12514925a0dd&account_id=personal), saved version 1; model/renderer/UI/export contracts and README. Its transient demonstration review state is not the application's persistent review implementation.
- **[B3]** Previous Notification Workbench report requirements, read in full and superseded by this consolidated specification. The shipped 0.6.0 `REPORT_REQUIREMENTS.md` additionally includes the governing 0.4.1 wording and 0.5.0 workflow/review amendments.
- **[B4]** [Shadowserver schema support audit](https://chatgpt.com/library?file_id=libfile_6f211d5ed64c8191ac1900ed0d3a715c&account_id=personal), header/summary reviewed; pinned upstream commit `bf5e6791b3bad836154aab411aa6333502babb70`, report inventory SHA-256 `3a5594da9aa2b17d4c7e88f91ff3b28bd4d6118a1cf3b43311bf449cf98023ae`. Snapshot counts and profile interpretation are from that audit, not a claim of a fresh exhaustive audit.

### Source contracts and guidance

- **[S1]** CISA, [KEV JSON schema](https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities_schema.json) and [catalog feed](https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json): membership, catalog metadata, and `knownRansomwareCampaignUse`. Schema inspected November 7, 2026; live per-CVE values remain runtime data.
- **[S2]** NIST, [NVD API schema](https://csrc.nist.gov/schema/nvd/api/2.0/cve_api_json_2.0.schema) and [SSVC schema](https://csrc.nist.gov/schema/nvd/api/2.0/ssvc-v2.0.3.json): description, metrics, provenance, CISA-related properties, and optional SSVC assessments. Inspected November 7, 2026.
- **[S3]** CVE Program, [CVE-2024-4577 JSON record](https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/2024/4xxx/CVE-2024-4577.json): inspected example of CISA ADP SSVC and KEV entries. Example values are not hardcoded product policy.
- **[S4]** CERT/CC, [SSVC exploitation definitions](https://certcc.github.io/SSVC/howto/gathering_info/exploitation/): None, Public PoC, Active, and evidence meaning. Inspected November 7, 2026.
- **[S5]** FIRST, [EPSS API](https://api.first.org/epss/): CVE queries, probability, percentile, and score dates. Inspected November 7, 2026.
- **[S6]** FIRST, [EPSS FAQ](https://www.first.org/epss/faq): probability interpretation, distinction from percentile, and distinction from known exploitation. Inspected November 7, 2026.
- **[S7]** Shadowserver, [report schema repository](https://github.com/The-Shadowserver-Foundation/report_schema): use the audited pinned schema provenance in B4 for this release; schema inventory alone does not define universal requiredness or semantic eligibility.
- **[S8]** FIRST, [Traffic Light Protocol 2.0](https://www.first.org/tlp/) and [TLP usage poster](https://www.first.org/tlp/docs/v2/FirstTLP-PosterA4-CMYK-30m.pdf): official labels, sharing boundaries, document header/footer placement, recommended size/alignment, and colors. Verified November 7, 2026. The standard is maintained by FIRST; the attempted CISA web guidance page was unavailable during this verification, so the primary normative source governs this specification.
- **[S9]** W3C, [WCAG 2.2 text contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html), inspected November 7, 2026.
- **[S10]** W3C, [WCAG 2.2 non-text contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html), inspected November 7, 2026.

**Branding provenance:** User-supplied USSS palette and approval restriction in the current discussion. This specification does not claim independent HQ approval.  
**Controlled-copy provenance:** `approved_template.py`, revision `approved-2026-11-06-v1`; source-file SHA-256 `3b139d987f9e83e97f289b45b69f8b755a06bda1b495452697c59bc8d494d1d3`.

TLP:AMBER
