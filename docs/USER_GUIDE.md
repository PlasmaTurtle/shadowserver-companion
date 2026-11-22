# Shadowserver Eclipse User Guide

From reported exposure to documented outreach

Version 0.12.1 release candidate | November 22, 2026

Shadowserver Eclipse helps an analyst turn reported internet exposures into useful, traceable outreach. It brings source reports, organization research, vulnerability references, notification writing, delivery records, and case closure into one local Windows application.

The work starts with a reported hostname or IP address. Your job is to determine who is responsible, which findings belong in a notification, how to reach the organization, and what outcome the record supports. Eclipse organizes that work and preserves the evidence behind it.

This guide follows the decisions you make during a workday. Read sections 1 through 3 for a first start, then follow the workflow through section 11. Use sections 12 through 16 for exploration, reference, maintenance, and help. **Bold text** identifies controls or labels you will see in the app.

### Find your task

1. [Understand the work and find your way](#1-understand-the-work-and-find-your-way)
2. [Set up and open your workday](#2-set-up-and-open-your-workday)
3. [Bring new reports into the workspace](#3-bring-new-reports-into-the-workspace)
4. [Review leads and decide what deserves outreach](#4-review-leads-and-decide-what-deserves-outreach)
5. [Keep organization records accurate](#5-keep-organization-records-accurate)
6. [Build a notification around the evidence](#6-build-a-notification-around-the-evidence)
7. [Resolve vulnerability sources and missing information](#7-resolve-vulnerability-sources-and-missing-information)
8. [Review the report and certify it](#8-review-the-report-and-certify-it)
9. [Find a contact and prepare outreach](#9-find-a-contact-and-prepare-outreach)
10. [Record outreach and manage followups](#10-record-outreach-and-manage-followups)
11. [Close the case and handle later changes](#11-close-the-case-and-handle-later-changes)
12. [Explore the Observatory and entity map](#12-explore-the-observatory-and-entity-map)
13. [Use the Library for research and explanations](#13-use-the-library-for-research-and-explanations)
14. [Protect your work and end the day](#14-protect-your-work-and-end-the-day)
15. [Walk through a typical analyst day](#15-walk-through-a-typical-analyst-day)
16. [Solve common problems](#16-solve-common-problems)

## 1 Understand the work and find your way

**Use Eclipse for:** reviewing reported exposures, qualifying outreach opportunities, identifying organizations, preparing consistent notifications, tracking contact work, and retaining a clear record of decisions. It is not a replacement for the recipient's technical investigation. Importing or certifying a finding does not establish compromise or remediation.

### Know what you are looking at

An **entity** is the organization record. Its name may begin as a hostname until you establish the business identity. An **asset** is an associated hostname, domain, or network address. An **observation** is a retained source-report record. A **finding** is the reported condition supported by observations. Several observations can support the same finding.

A **lead** is an opportunity awaiting analyst action. An **investigation** is the notification case in which you prepare a report, record outreach, and document an outcome. One organization can have several cases over time. A new sighting does not automatically mean a new notification is needed.

### Choose a destination

| I want to | Open |
| --- | --- |
| Decide what to work on next | **Workspace** |
| Find or resume a notification case | **Investigations** |
| Explore organizations, findings, and locations | **Observatory** |
| Maintain an organization and its assets | **Entities** |
| Review qualified opportunities | **Leads** |
| Decide whether identity evidence supports a match | **Attribution** |
| Import reports or review intake and packages | **Data** |
| Research CVEs, products, or explanation text | **Library** |
| Review saved actions and decisions | **Activity** |
| Set preferences, connections, backup, or recovery | **Settings** |

Press **Ctrl+K** for **Search & jump**. Enter at least two characters of an entity, hostname, IP, or CVE. Use the arrow keys and Enter to open a result; Escape closes the search. This searches saved information rather than initiating an external lookup.

### Keep the evidence and the decision distinct

Eclipse preserves original observations while you decide what to include in a recipient report. Excluding a finding from outreach does not erase its source. A shared IP does not establish common ownership. Reported severity and internal outreach priority answer different questions: how serious the condition is assessed to be, and what you should work on next.

## 2 Set up and open your workday

### Start the app

Run the Windows installer, then open **Shadowserver Eclipse** from its shortcut. The installer includes the runtime; operating the app does not require a separate Python installation or Microsoft Word. The browser is the interface, and the console keeps the local application running. Keep that console open while working.

For practice, open **Start → Shadowserver Eclipse → Shadowserver Eclipse Demo** and confirm the banner **Demo workspace · Sample data**. Its separate example records let you learn the workflow before using working records.

### Complete the guided setup

A new workspace opens **Set up your workspace**. Review its three steps:

1. **API connections.** Existing keys appear as completed credential setup, without asking you to enter them again. If both keys are detected, this step is marked complete; choose **Continue**. **Test connection** checks Shadowserver access and loads report choices when needed. For a missing Shadowserver connection, enter your API key and secret, then choose **Save & connect**. An NVD key is optional and allows faster API updates. On Windows, **Save in Windows Credential Manager** makes the selected key available after restarting. To begin without keys or a connection, choose **Use manual imports for now**. You can add connections later.
2. **Identity & jurisdiction.** Choose your agency from the presets or select **Other agency or organization**. Enter your name and office or location, and select your report jurisdictions. A preset fills agency and department; it does not change your jurisdiction or grant subscription access. **Title** and **Contact email** are optional. Leave the title blank for a name-only sender. Choose **Save profile & continue**.
3. **Retrieval schedule.** Leave **Enable retrieval schedule** off to skip this schedule, or enable it and select the services, time, subscription, and report types you need. Review the workspace summary, then choose **Save choices & finish setup**. Library has separate daily NVD catalog and EPSS/KEV update controls; turning this schedule off does not disable them. Review those controls in Library after setup.

**Finish later** retains completed steps. Resume from **Settings → Review setup**. An existing workspace with a complete saved identity keeps that profile; you can review setup when you want to change it.

### Review Settings for daily work

Use the section buttons at the top of **Settings** to reach **Profile**, **Jurisdiction**, **Connections**, **Automation**, **Reports**, **Display**, **Data & recovery**, or **Software**.

Under **Review & import defaults**, review **Outreach scope**. **Critical or known exploited** is the default. **Targeted outreach** requires a reason for the deliberate change in scope. Priority cities and products affect urgency; they do not bypass intake requirements. Use **Appearance, branding & display** for workspace appearance, report branding, and display time zone.

Choose **Save settings** for profile and preference edits, and confirm **Settings saved**. If a field needs correction inside a closed section, that section opens and the field receives focus. API keys, the retrieval schedule, and maintenance actions have their own controls. Automation also shows whether Library daily reference updates are enabled and links to their separate controls. Unsaved changes are protected when you navigate away or open setup. Your office describes where you work; **Jurisdiction** controls the report scope.

An entered NVD key remains unsaved until you choose **Save NVD key**. New input entered while an earlier save is running stays in the form. **Clear entry** discards the entered text while keeping the saved connection; **Remove key** removes the saved credential. The header appearance shortcut saves only the theme and preserves your other preferences.

Sender and entity details are saved with a report. Changing Settings or an entity later does not silently rewrite that report. Review and adopt the update in the affected draft when appropriate.

### Prepare your references and connections

Choose **Download catalog** in Library to load the public NVD feeds. An NVD key is optional for normal downloads and updates; adding one in **Settings → API connections** permits faster API updates. Allow **10 GiB free** for the first download. Check CVE catalog status and **Local intelligence · CVSS, EPSS & KEV** separately. File imports do not require a Shadowserver API key; API acquisition requires your subscription credentials.

Saved records and downloaded references remain available locally. External lookups, new downloads, and feed updates need connectivity. A partially downloaded or stale catalog is not complete current coverage.

### Choose the next useful action

Start each day in **Workspace**. Review leads, active investigations, follow-ups due, and **Priority work**. Expand **How this list is ordered** if needed. The priority list shows a limited selection; use **All investigations** for the full queue. Open a case to see its next step, then check the evidence before acting. A suggested action or due date is a prompt for you, not an action the app has performed.

## 3 Bring new reports into the workspace

### Import a file

1. Open **Data → Files** and choose **Choose reports**, or drop files into the upload area. Supported files include XLSX, XLSM, CSV, and CSV.gz, up to **50 MiB each**.
2. Watch **Accretion**. Open **Details** to inspect progress and any lookup or attribution issue. Use **Pause** or **Pause after current group** when offered; **Resume import** continues paused work.
3. Review **Import history**. Inspect **Report interpretation**, **Source field details**, and **Hostname groups** when a result is unexpected. **Original file** retrieves the preserved source.
4. Open **Ranked leads** or **Leads** for the work that became actionable.

**Check inbox** imports eligible files waiting in the configured inbox. Automatic inbox checks can be enabled in Settings. Importing a file and qualifying its findings are separate results.

### Understand Accretion

Accretion is a funnel: **Filter → Qualify → Evaluate → Associate**. Filter checks supported findings and jurisdiction. Qualify requires authoritative IP/domain attribution and a functioning related website with a retained screenshot; a login page must identify the business. Evaluate ranks the qualified lead. Associate checks prior notification history, outreach holds and external referrals before publishing and queuing contact discovery. In Data, use **External deconfliction list** to maintain a whole-domain or exact-host entry with its reference and reason. Groups awaiting review or retry stay outside active Leads until qualification completes. Retained source records remain available even when they do not pass.

Some observations remain as context without becoming leads. **Settings → How rows qualify** explains required fields, jurisdiction, supported critical or locally verified KEV findings, and report-dependent version requirements. **Dark Matter** keeps complete source rows and their recorded outcomes, including malformed and excluded rows. A retained row is not itself approval for outreach. Approval of one condition does not approve every other condition from that source.

Reimporting the same source does not create extra density. Genuine later sightings extend history. If settings change, use **Re-evaluate import** deliberately to apply current rules to an earlier import; changing Settings alone does not reprocess it.

### Import through the API

Open **Data → API**. Enter the **API key** and **Secret**, choose the desired credential storage option, then **Save & connect**. Select **Subscription**, **Report type**, **From**, and **Through**, and choose **Find reports**. Select available reports and **Import selected**.

Subscription choices follow your saved jurisdiction. Recognized subscriptions for other states are excluded; a uniquely matching subscription is selected for you. National and custom subscriptions may remain available because their names do not establish a narrower scope. Choose them deliberately; intake still checks the source rows against your jurisdiction. If you change jurisdiction, review your subscription and schedule again.

Read partial-listing warnings. Retrieval marked **Completed** does not mean every finding passed intake; follow Accretion afterward. **Already imported** identifies previously acquired reports.

### Schedule recurring acquisition

Use **Settings → Automation → Configure** for guided choices, or **Data → API → Scheduled intake** for the existing schedule controls. Enable the schedule, select report and reference sources, set **First check, local time**, recheck interval, and recent-day window, then save. The first-check time uses the computer's local time, separately from the display time zone. **Run now** starts a check; **Recent scheduled checks** shows results.

Normal schedules require the app's backend to run. In guided setup, **Allow checks while the app is closed**, or **Enable closed-app runs** in Data, uses the signed-in Windows account. Save the Shadowserver and NVD keys for the selected services in Windows Credential Manager first. Session-only keys cannot support a later background process. Checks do not run with the computer off or the user signed out. Scheduled imports still pass through Accretion and can require your review.

A saved subscription that conflicts with a changed jurisdiction pauses automatic acquisition until you correct the selection. Review the visible schedule status after changing scope or replacing credentials.

## 4 Review leads and decide what deserves outreach

### Read priority as a work aid

In **Leads**, choose **All**, **CVE**, or **End of life**, search by hostname, IP, or finding, and sort by priority or observation date. A lead with both kinds of finding appears in both views. A decision on that lead updates both views and advances to the next eligible lead in your selection. The **Outreach priority** badge uses **Cool**, **Warm**, **Hot**, and **Blazing**. **Unscored** means a usable score is unavailable.

Open a lead to compare its reported hostname and root site with the hostname and time on its saved screenshot. Select the image to inspect the original. **Notification history** shows when the organization last received a certified notification and how many distinct cases reached a recorded delivery or acknowledgement.

Open **Why this temperature** to inspect quality, urgency, local CVE evidence, and the saved scoring record. Review catalog warnings before relying on the ranking. Priority does not prove compromise, establish ownership, or mean a contact is ready.

### Resolve identity uncertainty

If a lead says **Match needs review**, review the proposed organization before choosing **Associate**. In **Attribution**, open **Review** and compare the reported hostname/IP, registration details, matched words, source, and time. Use **Lookup history** or **Download evidence** when the summary is insufficient.

Choose the relevant **Use this supporting record**, add a decision note when useful, and **Accept attribution** only when the evidence supports the association. Use **Dismiss match** (**Reject** in the list) for an unsupported match or **Retry lookups** when another attempt is warranted. A partial word match or shared hosting address alone is not enough to establish a business identity.

### Choose what happens next

| Action | When to use it |
| --- | --- |
| **Start notification** | The lead is qualified, its organization is resolved, and a new report is appropriate. |
| **Add to active notification** | Related findings belong in an existing editable case. Review its scope afterward. |
| **Open active notification** | Existing work already covers the next step; continue that case. |
| **Defer** | Move the lead out of the immediate queue. This does not set a dated reminder. |
| **Return to leads** | Bring a deferred lead back for action. |
| **Ignore** | Retire the lead from actionable work while preserving history. |

An existing frozen or certified report will not silently absorb new findings. Reopen or revise through the report's controls when allowed. If a lead says **This lead is no longer current**, follow **Current leads** rather than acting on the old view.

Before starting a report, you should be able to explain the organization match, the specific reported condition, why it belongs in your scope, and how the source supports it. Unresolved checks should lead to review, not stronger wording in the notification.

## 5 Keep organization records accurate

Open **Entities** and select the organization. **Overview**, **Contacts**, **Assets**, **History**, and **Details / edit** bring its current information and retained work together.

### Replace the provisional identity with useful details

In **Details / edit**, review **Name**, **Mailing address**, **City**, **State**, and **Notes**, then **Save details**. Keep known business details separate from what a network report happens to say about an IP address. A reported city can help place an entity on the map without becoming a verified mailing address.

In **Contacts**, save the person's or team's name, role, email, and phone when known. In **Assets**, review **Associated domains and hostnames**. **Associate asset** links an identifier to the entity; it does not create a vulnerability finding.

### Update an active report deliberately

Return to the report after changing the entity. **Review entity update** compares **In this report** with **Current entity**. Check the differences and choose **Use updated details**, or supply a reason and **Reopen affected sections and update** when frozen sections are affected. Review those sections again before freezing them.

This keeps the shared entity record current while preserving what you reviewed for each report. Earlier certified packages retain their original content.

### Choose the right correction

| Situation | Use | Result to expect |
| --- | --- | --- |
| Two records are the same business | **Combine entities** | Select the entity to keep and review the combination. |
| An asset belongs to a different organization | **Transfer ownership** or **Transfer entire domain** | Review affected records and record the correction reason. Prior cases and dated evidence remain with the original owner. |
| A dismissed finding should be reconsidered | **Assets → Dismissed findings → Review restoration** | Record a reason and **Restore finding** to return it to lead review. |

Save open edits before a combination or transfer. A duplicate-record correction and a change in ownership are different decisions. New qualifying observations create separate finding history for the new owner; undated or earlier observations require review. Transferring an identifier does not transfer the truth of an earlier notification to that organization.

Use **History** to understand prior associations and decisions before making another correction. If a record is incomplete, leave the uncertainty visible rather than filling it with an assumption.

## 6 Build a notification around the evidence

Open the case from **Workspace** or **Investigations**, then use **Report**. The other case tabs are **Assets**, **Contact & delivery**, **Closing report**, and **History**. **Scope & history** shows the case context and retained work.

### Work through the five report sections

| Section | What to review |
| --- | --- |
| **Introduction** | Notification date, entity, sender, subject, overview, severity, and presentation. |
| **Vulnerabilities** | Recipient scope, reported conditions, versions, CVEs, source treatment, and technical limitations. |
| **Attribution** | Why the reported assets are associated with this organization and which evidence supports that conclusion. |
| **Information** | Plain-language explanations, guidance, and any optional advisory snippets. |
| **Closing** | Resources, sign-off, signature, and recipient output options. |

Use **Save draft** as you work and check **Saved locally** before leaving. The report's **Closing** section is its recipient-facing ending. It is not the separate **Closing report** that finalizes the case.

### Review what the recipient will be told

In Vulnerabilities, open **Recipient report scope** and **Review source observations** or **Review N flagged observations**. Inspect the date, source, and reported condition. Use **Include** or **Exclude** for the particular observation, record **Reason for this scope decision**, and **Save scope decision**. Reopen affected frozen sections when the dialog requires it.

This changes the current report's scope while retaining originals and earlier certified reports. Invalid or nonpublic network addresses cannot be presented as public exposures. Exclusion does not mean remediation, and evidence can support attribution without being a notified finding.

### Use the right explanation

Choose the appropriate **Narrative template**. **Critical vulnerabilities** and **Other reported findings** serve different source conditions. Some supported reports describe an exposed service or end-of-life product without a CVE; follow their specific checks and interpretation limits.

Use **Finding values · supply missing software or affected versions** only when you have supporting information. Blank overrides retain source values. A screenshot or Secretary of State record is not mandatory for every case.

In Information, **Additional optional snippets** provides reusable advisory text. **Edit wording for this notification** changes this case's wording. **Adopt latest library revisions** deliberately brings in updated shared text. Review it before freezing. Put internal working material in **Closing → Internal notes → Working notes**, which is excluded from recipient reports.

## 7 Resolve vulnerability sources and missing information

Use this section when a CVE is missing, a source has changed, or the report asks you to choose how published information will be used.

### Review the source behind each CVE

1. In Vulnerabilities, open **Published CVE sources**. Review the reported CVEs and the local records available for them.
2. Use **Search catalog** or **Load local CVEs**. If the catalog is missing or incomplete, update **Library**, then return to the report and review the available sources again.
3. Use **Refresh sources → Refresh local records** when a refresh is needed. **Review retrieved sources** lets you consider newly retrieved material before adopting it.
4. Read **Source details and references** and **Preserved response metadata**. Check the description, product/version conditions, source status, and dates against the reported exposure.
5. Under **Use in this notification**, select the appropriate source treatment and review the resulting wording.

The **Show** selector only filters what you see. It does not remove a CVE from the report. Missing records remain visible so that you can make an explicit decision.

### Choose a supported source treatment

| Choice | What you need to do |
| --- | --- |
| **Use selected published source** | Read the selected record and confirm that its use in the report is appropriate. |
| **Document an official-text fallback** | Supply the reason, official publisher or contributor, public source URL, retrieval timestamp with timezone, and exact official published description. |
| **Exclude with a recorded reason** | Explain why the CVE should be excluded from this notification. |

Official-text fallback is not offered for reserved or rejected CVEs. It does not require a screenshot. Do not fill a missing description with invented wording or treat an absent local record as evidence that the CVE is harmless.

### Read the signals separately

**CVE** identifies a publicly documented vulnerability. **CVSS** is a severity assessment. **KEV** identifies a vulnerability listed by CISA as known exploited. **EPSS** is a dated estimate of exploitation probability for the vulnerability; its percentile is a separate comparison measure. **EOL** means end of life or support.

These references help explain and prioritize a finding. They do not establish that this particular organization has been compromised. Product and version matches can still depend on platform or configuration details. The recipient's technical team must assess applicability and response. Frozen content stays tied to its reviewed sources until you explicitly reopen and adopt changes.

## 8 Review the report and certify it

### Choose the recipient presentation first

Under **Appendix & output options**, select **Recipient edition**. **Full notification v1** is the default fuller report. **Compact recipient v1** summarizes CVE evidence and combines next steps and resources, while the internal package retains complete report content and source records.

**Include appendix in the recipient report** controls whether the full supporting appendix travels inside the recipient PDF/DOCX. When unchecked, the appendix is saved separately and the recipient report retains references. Choose the edition and appendix setting before freezing. Older saved layouts may require **Adopt current report format**; reviewed sections must reopen before the edition changes.

### Complete the review checkpoints

1. Save your content and use **Preview** to read the rendered document. Check names, dates, scope, explanation, citations, and page layout. Preview saves current draft edits; it does not certify or deliver the report.
2. In each of the five sections, resolve its checks and choose **Freeze section**. Freezing saves and locks the reviewed content; it does not render a new document by itself.
3. If information changes, inspect **Changes need review** and **Changed fields and dependencies**. Use **Reopen section**, record the reason, make the change, and freeze again.
4. In **Report certification**, confirm **5 / 5 sections frozen**, no remaining checks, and **Ready to certify**. Follow any blocker to the relevant section.
5. Choose **Certify report** and wait for success. A rendering or source error is not a certified result.

**Report certified** means the reviewed revision has been preserved and the case is **Completed & Pending Notification**. It does not mean anyone has received the report. Continue to **Contact & delivery**.

### Download the intended output

| Output | Intended use |
| --- | --- |
| **Download DOCX**, **Open PDF**, **Recipient package** | Recipient-facing notification materials. |
| **Supporting appendix PDF / DOCX** | Separate supporting appendix when available. |
| **Evidence & records** | Internal evidence reader, source records, working notes, priority context, and chronology. |

Review the actual attachment before sending. Do not send the entire internal record merely because it is beside the recipient download. Saved revisions are also available through **Packages** in Data. A **Package files missing. Restore from backup.** warning means the expected files need recovery.

Certification preserves the reviewed report. It is a workflow checkpoint, not a finding that the recipient was exploited, notified, or remediated.

## 9 Find a contact and prepare outreach

### Research a useful route

Open **Contact & delivery** and choose **Find contacts**. Select the **Website** when several eligible roots exist. Read the suggested route and its supporting source. **Sources & other contacts** or **Sources & search details** shows what the search checked and where it was blocked, partial, or unsuccessful.

**Known contact**, **Preferred**, **Pending confirmation**, **Delivery recorded**, and **Previously found · not in the latest search** describe different facts. A high-ranked result is a lead to consider, not proof that this person is responsible for the affected system.

Use **Copy** to copy the route or **Fill fields** to populate the plan. **Search one company page → Search this page** supports a targeted check. **Source history** lets you prefer, hide, or mark routes unavailable without erasing historical evidence.

In **Edit contact plan**, review the contact name or team, role, email, phone, **Next action**, and **Follow-up date**, then **Save contact plan**. Copying or filling a contact does not record an attempt.

### Prepare wording you can use

1. Save the contact plan, then open **Prepare outreach**.
2. Review the selected recipient, **Why this contact was selected**, and **Open certified notification · revision N**. Without a certified report, this remains contact research; there is no certified attachment.
3. Review **Independent verification**. If needed, enter the **Public verification URL or office telephone route** and **Save verification route** so the recipient can independently verify the contacting office.
4. Read and edit **Subject**, **First-contact message**, and **Call outline**. If the context changed, use **Refresh context** and acknowledge that you reviewed the current recipient, report, and outreach context.
5. Choose **Save preparation**, then **Copy saved subject and message** once the preparation is current and its blockers are cleared.

Use your approved email, telephone, mail, or other channel to perform the outreach. Attach the intended report yourself when appropriate. Copying preparation does **not** send a message, attach a document, or record delivery.

If copy is unavailable, check unsaved changes, conflicting edits, outdated context, and the displayed readiness issue. Read generated wording before using it. After the real-world action, return to the case to record what happened.

## 10 Record outreach and manage followups

### Record the action you actually completed

Open **Record activity** or **Record contact activity**. Set **When · local time** and **Channel**. Select the outcome, the applicable **Report revision** or **No report involved**, recipient or team, and destination. Add notes and the recorded operator, then **Add activity**.

Use **Basis of information** to distinguish **Contact / administrative record**, **Reported by the recipient**, and **Independently verified by analyst**. A recipient's statement that a system was patched should remain recipient-reported unless you separately verified the relevant condition.

| Outcome | What it records |
| --- | --- |
| **Contact research**, **No answer**, **Voicemail left**, **Callback requested** | Progress toward contact, without successful delivery. |
| **Email sent** or **Email bounced** | The communication event; neither advances the case as delivered. |
| **Report delivered** or **Receipt acknowledged** | Successful notification tied to the current certified revision, a recipient, and an available package. |
| **Recipient update** or **Other** | Additional context with the appropriate notes and information basis. |

Successful delivery advances the case to **Notification Completed**, records the delivery time, clears the existing follow-up date, and makes preparing the closing report the next action. It does not establish remediation. Ordinary activity may refer to an older revision, but successful delivery must use the current certified report.

### Keep unfinished work visible

For unanswered calls, bounces, promised callbacks, or other remaining work, update **Next action** and **Follow-up date**, then save the contact plan. Workspace helps surface due work. A reminder does not place a call or send a message.

### Record a deliberate hold

Under **Outreach decision & finding history → Outreach decision**, choose **Active**, **Defer outreach**, or **Do not contact**. Record **Reason for decision**. **Reconsider on** is required for a deferral and optional for Do not contact. Choose **Save outreach decision**.

A due review date prompts you to reconsider; it does not automatically reactivate outreach or reopen a closed case. New work can inherit an existing reasoned hold, so inspect that decision before proceeding. This case-level deferral is different from the undated **Defer** action in Leads.

Use **Finding history** to compare new, repeated, changed, and previously covered findings. **Not seen in latest retained observations** describes the local reporting history. It does not establish that the underlying exposure has been fixed.

## 11 Close the case and handle later changes

### Write the final outcome

Open the case's **Closing report** tab when the work is ready to conclude. This is the internal outcome document, separate from the recipient report's **Closing** section.

1. Choose **Disposition**. A delivered case uses **Successfully notified**. Without recorded delivery, available outcomes include **Unable to contact**, **Out of scope**, **Duplicate notification**, and **Other**.
2. Write **Conclusion**. Distinguish source findings, actual contact outcomes, recipient statements, and independently verified work. Explain the reason for an administrative closure.
3. Review **Closed by**, then select **Preview closing report** and read the outcome and chronology. Preview alone leaves the case open.
4. Confirm **I reviewed the closing report and its chronology**, then **Finalize closing report**.
5. Confirm **Investigation closed** and inspect the final disposition and conclusion. **Open closing PDF**, **DOCX**, **JSON**, and **Recorded chronology** provide the retained output.

Finalization clears next action and follow-up. Closed cases do not accept ordinary edits or contact activity. A case closed without delivery continues to show **Delivery not recorded**; it is not counted as successfully notified.

### Understand the stages

| Stage | Meaning |
| --- | --- |
| **Scan Validation** | Source hostname groups awaiting review; this count is not a case count. |
| **Work in Progress** | Build, review, and certify the notification. |
| **Completed & Pending Notification** | Certified, awaiting delivery work. |
| **Notification Completed** | Successful delivery recorded; ready for outcome documentation. |
| **Closing Report Completed** | Final internal outcome retained, including administrative closure where applicable. |

Workspace may shorten active labels to **In progress**, **Ready to notify**, and **Awaiting closure**. Completed or archived work does not always mean successful delivery.

### Correct or extend work without erasing history

Before delivery, use **Revise report** or **Revise certified report** with a reason to create a new working draft. The previous certified package remains. Review, freeze, and certify the replacement before delivery.

After delivery, open the entity and use **Notifications for this business → New notification** for new work. That delivered revision cannot be rewritten through the revision flow. New observations, refreshed CVEs, entity changes, or library edits do not retroactively change historical certified reports.

## 12 Explore the Observatory and entity map

Use **Observatory** to understand the retained evidence across organizations, assets, findings, and time. Its views are **Field**, **Atlas**, **Pulse**, and **Records**.

| View | Use it to |
| --- | --- |
| **Field** | Explore grouped findings and relationships. **Instruments** changes grouping and detail. |
| **Atlas** | Locate known entities geographically and open their supporting evidence. |
| **Pulse** | Compare dated observations over time. |
| **Records** | Inspect underlying findings and source observations. |

Search **Organization, hostname, IP or finding**. **Filters** narrows the evidence; **Reset** clears scope controls. Select an object and use **Focus**, **Details**, or **Explore**. Open Records for underlying evidence and **Download original** for its source.

### Read Atlas by organization

Each entity contributes one marker even when it has many hostnames, findings, or repeat observations. Several entities can occupy the same city point. Counts of evidence describe the supporting data, not additional organizations.

Placement follows these rules:

1. A complete saved entity **city and state** takes priority.
2. Without a complete saved city/state, Atlas uses the **most recent associated IP/hostname report** in the selected evidence scope.
3. If that report lacks a usable location, the entity stays unplaced; the map does not choose an older report simply because it has a location.
4. A complete but unsupported saved city/state also remains unplaced rather than being replaced with an IP location.

The bundled Census city points cover **all 50 states, the District of Columbia, and Puerto Rico**. Ambiguous or unmatched names remain unplaced. Points represent approximate city areas, not verified street addresses. **Reported city fallback** identifies the reported city, hostname/IP, observation date, and source. Use **Inspect location source** to review it.

Atlas initially fits and highlights the states selected in Settings. Those outlines provide geographic context; they do not define legal or investigative jurisdiction. Historical entities outside your current states remain available in the current evidence view.

Use **Explore → Entities in this map** to browse organizations, **Unplaced** for missing markers, and **Edit saved location** for reliable business details. Unassociated assets remain in Records.

### Use time and visual patterns carefully

**Observation history → Observed through** limits the supporting scan-date evidence. It can change reported fallback locations; saved entity addresses and workflow status reflect current saved work. This is not a historical business-address reconstruction.

Field glow and size describe evidence patterns, not outreach priority. Connections represent identifiers reported together, not proven ownership or network traffic. Timeline gaps do not establish remediation; undated observations remain in Records.

Drag to pan and use the zoom controls. **Fit jurisdiction** returns to the states selected in Settings. **Fit entities** shows all mapped entities in the current view, including historical entities outside those states.

## 13 Use the Library for research and explanations

Library brings together reusable **Explainers** and **Products & vulnerabilities**. The catalog tabs are **Products**, **CVEs**, **Fields**, **Changes**, and **Dark Matter**. Library's plural **Fields** explores CVE data; Observatory's singular **Field** visualizes workspace evidence.

### Check reference freshness

Use **Download catalog** for the first download. **Partially downloaded** is not complete coverage. **Pause download** and **Resume download** manage an interrupted initial download. Afterward use **Sync now**, and **Build product index** when offered.

Review **Local intelligence · CVSS, EPSS & KEV** separately. **Sync EPSS & KEV** updates those feeds. Check successful update dates, score dates, counts, and errors. **Update daily** needs a running backend or an enabled closed-app schedule and can catch up when reopened. Saving a key does not itself download the catalog.

### Answer a specific research question

Use the Library search to find CVEs, products and explainer titles together. Results
are grouped by type; an unavailable catalog does not hide available explanation
text. Select a result to continue in its detailed view.

In **CVEs**, use **Search CVEs** with an identifier, product, or description. Open a result to read CVSS assessments, known exploitation, EPSS probability and percentile, dates, references, and **Source record**. **Open NVD record** opens the public source; **See observed connections** connects the reference to locally retained observations.

In **Products**, use **Find a product** and **Search products**. Choose an **Outreach scope**, then **Compare a reported version → Compare**. Read affected ranges and platform or configuration conditions. A version comparison is evidence to assess, not a substitute for confirming the recipient's installation.

**Fields → Field explorer** groups CVEs by a selected data field. Categories can overlap. **Changes → Catalog changes** shows changes captured by local updates; it is not every revision ever published upstream.

From a catalog change, review affected work to compare the current local reference
with the older source selected in an active notification. Include completed work
when needed. Missing comparable source data is shown as unknown. Opening this
review never changes a draft or a certified report; adopt a replacement deliberately
in Investigations. CVE details also bring dates, source identity, severity and
EPSS/KEV context together for review, with links to the underlying source record.

Name a selection under **Saved views** to reopen the same filters later. Rename
or remove views as needed. Views belong to the workspace and travel with its
backup; earlier browser-local views are imported without overwriting later edits.

### Revisit retained observations

**Dark Matter** lets you search complete retained report rows, including malformed and out-of-scope observations. Select a field and operator, and choose **Original** or **Normalized** values. Open a record to inspect all fields, normalization diagnostics and its outcome history; the original report remains the source evidence. Archive retention does not establish qualification or current ownership.

### Maintain reusable text

Choose **New explainer** or **Edit explanation**. Enter the title, explanation, and source URLs, then **Save explainer**. Use **Source citations · publisher, title and dates** for accurate metadata; leave unavailable dates blank.

A report keeps its saved wording until you deliberately adopt a newer revision.
Editing an explainer does not rewrite certified reports. Compare retained revisions,
review current case usage, and restore old wording as a new revision. Archive
obsolete explainers to hide them from new selections; they remain available in
history and existing case snapshots. Labels distinguish bundled starting text,
locally edited bundled text and analyst-created text. If another window saved first,
your draft remains available for comparison and explicit rebasing. History begins
with the wording retained at upgrade; earlier overwritten revisions cannot be recovered.

## 14 Protect your work and end the day

### Save and stop deliberately

Before finishing, save drafts, contact plans, outreach preparations, and Settings changes. Record completed outreach and give unfinished work a next action or follow-up date. In **Activity**, search decisions, reasons, or names; operator and action filters use exact matches. Expand **Recorded context** to inspect saved details.

Let imports and reference updates finish, or use their offered pause/cancel control. Closing the browser tab leaves the backend running. Press **Ctrl+C in the app's console** to stop it. Open the desktop shortcut next time for a fresh browser session. Eclipse has no separate close-workday command; this is your daily routine.

### Export a checked backup

In **Settings → Backup & recovery**, choose **Export data** and retain the ZIP in your protected backup location. Check **Last verified export**. Exports are checked by restoring an isolated copy. A normal export includes records, original reports, evidence, report packages, settings, inbox files, and operation history. Export limits are 2 GiB compressed and 8 GiB expanded. **Saved restore points** normally retains the latest three automatic points.

Provider credentials and the rebuildable reference catalog are excluded. Browser-local saved views also have separate persistence. After recovery or a move, review API connections and reference downloads. Export before upgrades and after significant work. Updates normally retain data; do not open an upgraded workspace with an older application.

### Update the application

Open **Settings → Software → Software updates**. **What’s new** displays the changes bundled with the installed version. Those notes appear once after an upgrade and can be reopened here; first-run setup takes precedence.

Choose **Check for updates** to look for a compatible release. Read the result: a connection failure or an unavailable release is not confirmation that you have the newest software. When an update is available, review its changes and choose **Download update**. Downloading alone does not install it.

Save your work and let background operations finish. Choose **Install and restart**, review the confirmation, and confirm when ready. If the available installer changes after that review, the app asks you to review it again. The installed Windows application verifies the downloaded installer, closes for installation, and reopens afterward. Your workspace is retained. If installation reports an error, follow that message and reopen the application after resolving it.

Running a newer installer directly also preserves working data with its default retention choice. Keep that choice when you intend to continue your workspace. Uninstall removes the application's own runtime and retains working data; it does not require you to delete a separate Python installation. Starting fresh in the installer or deleting data from Settings is a separate, deliberate choice.

### Restore a workspace

1. Choose **Import data**, select the backup ZIP, type **IMPORT**, and choose **Verify and stage import**.
2. A normal restore first retains the current workspace in a verified restore point. The import is a replacement, not a merge.
3. Close both browser and console, then reopen to apply it. Before restart, **Cancel pending change** keeps the current records instead.

Invalid imports leave current data untouched. The advanced **Replace without saving a current restore point** option does not preserve a new restore point of damaged current data. If the app cannot open, follow **Recovery when the app cannot open** and [the offline recovery guide](../modules/workspace/docs/DATA_MANAGEMENT.md#recovery-before-the-app-can-start); that offline workflow preserves the entire previous workspace. Do not delete database files manually. **Delete all data** is a deliberate reset that also removes managed restore points after restart.

### Check health and use targeted maintenance

Open **Workspace health & storage → Check workspace**. Wait for completed results; a canceled check is not a pass. Review warnings, storage, free disk, feed freshness, and the last verified backup. **Export diagnostic summary** omits report contents, contacts, credentials, and logs.

**Review safe cleanup** previews expired lookup pointers. Confirm the offered plan only if wanted; it retains evidence and reports and does not guarantee smaller database files. Use **Rebuild analytical counters** when the health result offers it for inconsistent counts. Checks and cleanup do not themselves refresh feeds or repair every underlying problem.

## 15 Walk through a typical analyst day

This illustrative example follows a fictional organization, Ridgeway Services. It describes decisions rather than supplying test data to import.

### Open and choose work

You open Workspace and see a callback due on an existing case plus new leads. You handle the promised callback first, record **No answer**, and save a new next action and follow-up date. The case remains pending. You then check reference freshness and import the day's source report through Data.

Accretion links several host observations to one possible organization. A repeated sighting extends the existing finding history. One association needs review, so you read the registration and hostname evidence in Attribution. You accept the supported match and leave an unrelated shared-hosting address unresolved.

### Prepare a useful notification

You replace the provisional entity name with Ridgeway Services after establishing the business identity. No complete business city/state is saved. The most recent associated report in the selected scope has a supported city/state, so Atlas uses that approximate location and identifies its source. You do not copy the fallback into the mailing address as a verified fact.

From Leads, you choose **Start notification**. You review each included observation, exclude one unsuitable record with a reason, and check the source treatment for the relevant CVEs. A missing reference sends you to Library; it does not disappear from the report automatically.

You review all five sections, select the recipient edition and appendix option, read the preview, freeze the sections, and certify. The case is now ready to notify. No message has been sent.

### Contact and document the outcome

Contact research identifies a published IT route. You save the contact plan and prepare outreach, checking the independent verification route and the current report revision. You save and copy the message, then use your approved communication channel and attach the intended recipient PDF.

You initially record **Email sent**. The case remains pending. When the facts support **Report delivered** or **Receipt acknowledged**, you record that outcome against the current certified revision. The case advances to Notification Completed.

The recipient later says the system was patched. You record a **Recipient update** with **Reported by the recipient** as its basis. Your conclusion says what the recipient reported; it does not turn that statement into independent verification.

### Close and preserve the work

You preview the Closing report, verify its chronology, and finalize the supported disposition. Before stopping, you save unfinished work, review tomorrow's follow-ups, export a checked backup, and stop the console. Later findings are reviewed as later evidence; they do not overwrite this delivered report.

## 16 Solve common problems

Start with the status shown in the app and the record involved. A failed view, incomplete lookup, or stale browser session does not by itself mean your saved records are lost.

| What I see | What to do next |
| --- | --- |
| Setup is unfinished | Open Settings → Review setup. Completed steps are saved. Choose manual imports or leave the retrieval schedule off if you are not ready to configure APIs. Library daily reference updates remain separately controlled. |
| An expected API subscription is absent | Review Settings → Jurisdiction and your account's subscribed reports. Recognized subscriptions outside your jurisdiction are hidden. An agency preset does not grant access. |
| Scheduled checks need attention | Review the saved subscription, jurisdiction, source selections, and credentials. Closed-app checks require saved Windows keys and a signed-in account. |
| An update check failed or no compatible release is published | Read the status and retry when the service or release is available. Continue using the installed version; do not treat this result as a successful up-to-date check. |
| Install and restart is unavailable | Save open edits and wait for active operations to finish. Automatic installation is available in the installed Windows application. |
| Import completed but no leads | Read Import history and Accretion details. Check jurisdiction, scope, supported finding type, attribution, and whether the observations already belong to existing work. |
| Lookup retry or attribution review needed | Open the stated issue, review saved evidence, and retry or make the supported attribution decision. Do not assume retrieval success means qualification. |
| A lead cannot start a notification | Resolve the exact qualification or entity issue. Check for an active case and use its offered open/add action. A superseded lead points to Current leads. |
| Report text is read-only | Check whether it is sourced, approved, frozen, or certified. Use the relevant structured fields, source treatment, reopen, adoption, or permitted revision flow. |
| Certify remains unavailable | Read Report certification blockers. Confirm all five sections are frozen and resolve scope, source, dependency, or rendering issues. |
| Copy outreach is disabled | Save edits, review the recipient/report/verification route, refresh changed context, and resolve the displayed blocker. |
| Email sent but case still pending | Record the event accurately. Only supported Report delivered or Receipt acknowledged advances delivery; sending alone does not. |
| Entity is missing from Atlas | Open Unplaced and inspect saved city/state and the latest report location. Ambiguous or unmatched cities remain unplaced. Many observations still make one entity marker. |
| Observatory looks empty | Reset filters and search; check Records. Pulse needs dated observations. An empty scope is not evidence of remediation. |
| Library is incomplete or overdue | Read errors and successful-update dates. Resume the catalog, sync the relevant feeds, or build the product index when offered. |
| Entity or sender changed but report did not | Review and adopt the update in the draft; reopen affected frozen sections. Historical certified reports remain unchanged. |
| Changes are paused after restore/reset | Review the staged operation. Restart the console and app to apply it, or Cancel pending change before restart. |
| Several views show a connection error while the console is open | Choose **Check local service** on the connection error screen, or open `/api/health` in a new tab on the same local address (normally `http://127.0.0.1:8881/api/health`). A JSON response with the application version confirms the service can answer at that moment. If it times out or the connection is refused, note the time and console message. Open Eclipse from the desktop shortcut for a fresh session. |
| Browser session no longer works | Reopen the desktop shortcut for a fresh session. If the app cannot start, use the documented recovery path. |
| Package files are missing | Use the documented backup recovery workflow. Import replaces the workspace, so preserve current work first. A database entry alone is not an intact package. |

If the issue remains, note the exact action, visible message, affected record, and whether the work was saved. Use **Export diagnostic summary** when useful. Retain the original evidence and describe the actual failure rather than repeating the action without checking its result.

## Support and troubleshooting

Start with [Solve common problems](#16-solve-common-problems),
[backup and recovery guide](../modules/workspace/docs/DATA_MANAGEMENT.md), and
[Windows acceptance checklist](WINDOWS_ACCEPTANCE.md). Developers should use
[Development](DEVELOPMENT.md) for setup and verification commands.

For a reproducible application defect, open a
[bug report](https://github.com/PlasmaTurtle/shadowserver-companion/issues/new?template=bug_report.yml).
Include the exact application version, Windows version, whether you used the
installer or source checkout, steps using synthetic data, and the expected and
actual behavior. State whether the problem reproduces in a separate synthetic
workspace. Do not delete or modify working evidence to investigate a defect.

For a proposed improvement, open a
[feature request](https://github.com/PlasmaTurtle/shadowserver-companion/issues/new?template=feature_request.yml)
and describe the workflow and desired outcome.

Do not attach real reports, databases, evidence, workspace backups, API credentials,
launcher/session URLs, or identifiable contact information. Redact diagnostic
excerpts and use fictional examples. Follow [SECURITY.md](../SECURITY.md) for suspected
vulnerabilities; ordinary issue reports are not a confidential reporting channel.

Issues track application work. They do not establish an organization's identity,
validate an exposure, or replace an analyst's review of notification evidence.
