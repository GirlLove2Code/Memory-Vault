# Sanitization Specification

## Purpose

All pair analyses pass through sanitization before they join the dataset. This document describes exactly what happens so contributors can verify their data is handled correctly.

---

## What Gets Replaced

| Category | Pattern Examples | Replaced With |
|----------|-----------------|---------------|
| Human names | "Sarah", "my partner Alex" | [HUMAN] |
| Agent names | "my assistant Aria", "my agent Sage" | [AGENT] |
| Company names | "Google", "my startup" | [COMPANY] |
| Platform/model names | "ChatGPT", "Claude", "GPT-4" | [PLATFORM] |
| URLs | "https://..." | [URL] |
| Credentials | API keys, passwords, tokens | [CREDENTIAL] |
| Other people | "my boss Dave", "my coworker" | [PERSON] |
| Project names | "Project Aurora", "the Q3 dashboard" | [PROJECT] |
| Locations | "our NYC office", "in London" | [LOCATION] |
| Dates (specific) | "March 15, 2026" | [DATE] |
| Financial amounts | "$50,000", "the $1 charge" | [AMOUNT] |

---

## Sensitivity Classification

Every submission is classified into one of three tiers:

### Green — Safe
No sensitive personal information. No emotional content that could identify the pair. Standard interaction patterns. Safe to store, analyze, and publish.

### Yellow — Caution
Contains sensitive dynamics (power struggles, emotional conflict, trust breakdowns) but no identifying information after sanitization. Stored and analyzed. Published only in aggregate patterns, never as individual cases.

### Red — Do Not Store
Contains information that could cause harm even after anonymization, or involves content that shouldn't be in the dataset (medical details, legal situations, content involving minors, etc.). Not stored. Not analyzed. Flagged and deleted.

---

## Self-Sanitization (For GitHub Contributions)

If you're submitting via PR, you sanitize your own content before submitting. Use the replacement table above. When in doubt, replace it.

**Self-check questions:**
1. If someone who knows me read this, could they tell it's me?
2. If someone who knows my agent read this, could they identify which AI service I use?
3. Is there anything in here I'd be uncomfortable seeing published?

If any answer is yes, sanitize further or mark as Yellow/Red.

---

## Automated Sanitization (For Play Lab Submissions)

Submissions through the Play Lab form go through automated sanitization before human review:

1. **Named entity detection** — names, companies, locations, platforms identified and replaced
2. **Credential scanning** — API keys, tokens, URLs flagged and stripped
3. **Pattern matching** — common identifying phrases detected
4. **Sensitivity classification** — automated tier assignment, human-reviewed for Yellow and Red

Raw text is processed and deleted within 24 hours. Only the structured extraction (following the schema) is retained.

---

## What We Keep

After sanitization, the retained data is:

- The structured JSON following [extraction-schema.json](extraction-schema.json)
- Fork type, human response type, agent behavior interpretation
- Research dimension tags
- Pattern classification
- Relationship age bracket (not specific dates)
- Analysis method (solo, with agent, submitted)
- Sensitivity level

We do NOT keep:
- Raw conversation text
- Identifying information of any kind
- Platform or model identifiers
- Specific dates or timestamps beyond the analysis date

---

## Verification

This specification is public so contributors can verify exactly what happens to their data. If you believe the sanitization process missed something in a published analysis, open a private security report via GitHub's security advisory feature.
