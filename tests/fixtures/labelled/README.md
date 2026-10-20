# Labelled postings

200 real postings with the values Ghostless should extract from them, for
`ghostless evaluate` (crawler plan, stage C3). Sampled from the database on
20 October 2026 across platforms (Workday 55, Greenhouse 55, Ashby 30, Lever
25, Amazon 8, RSS 8, Google 5, Eightfold 5, Apple 5, job lists 4), levels,
countries and pay formats.

- `labels.jsonl`: one posting per line: its id, platform, title, location,
  `excerpt` (only the description sentences the labels depend on), `expected`
  values, a `note` on judgement calls, and `reviewed`.
- `private/` (git-ignored): each posting's full text. Rebuild it with
  `python scripts/build_labelled_set.py rebuild`.

**Every label is a draft (`"reviewed": false`)**, written by reading the
title, location and excerpt. A person should check them; set `reviewed` to
true for each one checked.

## Conventions

`null` means the posting doesn't say. An extractor that guesses where the
posting is silent counts as wrong.

| Field | Values and rule |
|---|---|
| `seniority` | intern, new_grad, junior, mid, senior, staff. An explicit title word wins: Intern / Co-op / Student / Stagiaire → intern; New grad / Early career / Graduate / programme → new_grad; Junior / Jr / Entry level / "I" → junior; Intermediate / "II" → mid; Senior / Sr / Lead / Manager / Architect / "III" or a level number 3+ → senior; Staff / Principal / Distinguished → staff. Otherwise the years asked for: 0–2 junior, 3–4 mid, 5+ senior, none stated mid. When years differ by degree, seniority follows the bachelor's track. |
| `level` | the site's four levels, from seniority: junior → new_grad, staff → senior. |
| `employment_type` | full_time, part_time, contract, temporary, internship. Interns, co-ops and student roles are internship (a student role on a vendor contract is contract). full_time only when the posting says so (including "permanent"). |
| `workplace` | remote, hybrid, onsite, when stated (including `#LI-Hybrid` style tags and "N days a week in the office"). A company-wide "remote-friendly" line doesn't count. |
| `countries` | ISO codes of the posting's locations, sorted. Empty for "worldwide". |
| `sponsorship` | available ("will consider sponsoring", "we sponsor visas"); not_available ("unable to sponsor", "will only employ those authorized", citizenship or clearance required); unknown otherwise, including generic "must be eligible to work" lines. |
| `min_years_experience` | the smallest number of years the main requirement asks for ("2 to 5 years" → 2, "BS + 5 or MS + 4" → 4). Company history, ages and maximums ("no more than 18 months") don't count. |
| `salary_*` | the base pay for the role: min, max, ISO currency, period (year, month, hour). When pay is given per country, the range for the posting's own country (or its first location); otherwise the first range stated. A "starts at" amount has no max. `$` without a currency is USD in the US and CAD in Canada. Benefits, stipends and placeholder ranges ("$0 - $0") aren't pay. |
| `role_type` | sde, data_eng, data, ml, hardware, security, other, as defined in `tracker/classify.py`. Customer-facing technical roles (sales, field and solution engineers) and IT administration are other. |
