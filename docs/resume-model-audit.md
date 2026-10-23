# Resume features: audit (October 2026)

What the resume score, "words to add" and job recommendations do today, and
where they go wrong. Nothing was changed for this audit.

**How the examples were made.** Postings are real: open postings from a local
copy of the database. Resumes are not: six invented personas plus the two
resumes the test suite already uses (`tests/test_resume.py`). No user resume
was read. The scripts are kept out of the repo; every number below can be
reproduced by running today's code on the same inputs.

| Persona | Who |
|---|---|
| frontend_student | 3rd-year CS student, one React internship, Toronto |
| data_new_grad | Statistics BSc 2026, data analyst internship |
| embedded_student | Electrical engineering student, firmware internship, FPGA side project |
| ml_new_grad | NLP master's 2026, LLM internship, ACL paper |
| senior_backend | Staff engineer, 10 years, Go and Kubernetes |
| non_tech | Café shift supervisor and cashier, business diploma |

## 1. How each one works today

### Resume strength (`tracker/resume/quality.py`)

`check_resume` runs about 15 rules, each a yes/no check:
- contact details (email, phone, LinkedIn, GitHub);
- which sections exist;
- the share of bullets with a number;
- weak openers ("responsible for");
- bullets over 35 words;
- word count;
- at least six recognised skills;
- buzzwords and "I/my".

The score starts at 100 and loses 14, 8 or 4 points per failed check, by
severity. That's all it is: **no job, role or posting is involved**, so a 100
means "no rule fired", not "a strong resume for what you want".

### Fit score and "words to add" (`tracker/resume/match.py`, `posting.py`)

`analyze_posting` splits a description by its headings into requirements,
nice-to-haves, duties and boilerplate. It then pulls out:
- skills, with `tracker/skills.py`: about 90 hand-written regular expressions;
  anything not on that list doesn't exist;
- years of experience and degree;
- "currently enrolled" phrasing;
- key terms: the 12 words or two-word phrases the posting repeats most, after
  a stop list, counting the title 3×, requirements and duties 2× and the rest 1×.

`score_job` adds up six parts:

| Part | Points | How it's measured |
|---|---|---|
| Required skills | 35 | skills on the resume, weighted by where they appear |
| Nice-to-haves | 10 | preferred skills on the resume |
| Key terms | 15 | key terms that appear on the resume |
| Experience | 20 | career stage and years |
| Education | 10 | degree, field and enrolment |
| Role and title | 10 | role type and title words |

Caps apply for a career stage mismatch or a missing description.

**"Words to add"** is `terms_missing`, the key terms the resume doesn't use. The
website shows it as "The posting's key terms" (`web/src/components/Match.tsx`)
and "Its key terms you don't use" in the builder.

### Recommendations (`recommend` in `match.py`, `POST /resume/recommendations`)

1. Every open tech posting (12,392 in the copy) gets a quick score from its
   stored skill tags.
2. The top 250 are re-scored with their full descriptions and sorted by score.
3. Ties go to the newer posting.

There's no notion of where the person is, which role they want, duplicate
postings, or variety in the list.

## 2. Ten examples where the strength score goes wrong

| # | Resume | Strength | What's wrong |
|---|---|---|---|
| 1 | frontend_student | 92 → **100** | Adding seven near-identical filler bullets ("Organized N weekend events…") made it perfect: padding clears the "too short" rule. |
| 2 | non_tech (café supervisor) | 76 | Same score as the ML new grad with an ACL paper and an LLM internship (76). |
| 3 | non_tech + GitHub link + "Python, Git, Docker" in skills | **92** | A non-tech resume beats every tech persona except one, by listing tools. |
| 4 | data, embedded, ML, senior, non_tech | 76, 76, 76, 76, 76 | Five very different resumes get the identical score: it moves in fixed 4/8/14-point steps. |
| 5 | test_STRONG vs frontend_student | 92 and 92 | 20 recognised skills and 8 months of experience score the same as 7 skills and 4 months. |
| 6 | senior_backend | 76 | A staff engineer with 10 years is told to "Link your GitHub or portfolio" (–8) and "Describe your work in bullets" although the resume has bullets. |
| 7 | embedded_student | 76 | "Describe your work in bullets" fires because the resume has 3 bullets (the rule wants 4+), even though all 3 are strong and quantified. |
| 8 | non_tech | – | Read as role **data**, level **experienced** (65 months), because of "Excel" and "SQL basics". That profile then drives which jobs are recommended (section 4). |
| 9 | embedded_student | – | The skills list misses STM32, SPI, I2C, UART and oscilloscope work; the frontend student loses Figma, Tailwind and accessibility; the ML grad loses LoRA and RAG. The "few skills" rule counts only the ~90 names the regexes know. |
| 10 | any | 100 | The page shows "Resume strength 100 · Strong · Nothing major to fix" whatever the person is applying for. A Go backend resume and an ML resume can both be "100" for the same ML internship. |

## 3. Ten examples where "words to add" goes wrong

Each row is a real posting and the terms the persona was told it was missing.

| # | Posting | Persona | Terms shown as missing |
|---|---|---|---|
| 1 | Verkada, Frontend Software Engineering Intern (#9923) | frontend_student | **verkada**, culture, cross-functionally, design, web |
| 2 | National Life, Web Production Intern (#11114) | frontend_student | **national life**, **life group**, position, **approved**, **range**, accurate, program |
| 3 | American Family Insurance, Web Developer Intern (#9817) | frontend_student | **benefits**, **employees**, **contingent**, program, technologies, development, standards |
| 4 | DoorDash, Data Analyst In-Store (#16808) | data_new_grad | **sevenrooms** (a company DoorDash bought), ship, executive, translate, plg, signals |
| 5 | Pure Storage, Staff AI & Automation Data Analyst (#16789) | data_new_grad | comfortable, **e.g**, quickly, **something**, **people actually**, change |
| 6 | Pure Storage, Senior MDM Product Data Analyst (#16737) | data_new_grad | **amp** (an HTML `&amp;` left in the text), technical, structures, systems |
| 7 | Anduril, 2027 Firmware Engineer Intern (#13597) | embedded_student | **u.s**, **anduril**, technology |
| 8 | Life Fitness, Embedded Software Intern (#13420) | embedded_student | **fitness hammer**, **hammer strength**, **local laws**, life fitness/hammer |
| 9 | The Aerospace Corporation, Embedded Systems Intern (#13099) | embedded_student | obtain, **clearance**, participates, organizational, full-time, microsoft |
| 10 | OpenTable, Staff ML Engineer (#17190) | ml_new_grad | **restaurant**, **diners**, **opentable**, builds, tradeoffs, design |

The pattern: key terms are frequency counts, not requirements. Company names,
benefits text, legal text, filler words and HTML leftovers all get through, and
none of them is something a person should add to a resume.

The skill extraction behind "missing skills" has its own errors on the same
postings:

- **Alternatives read as "all of these":** Verkada "requires" Angular, React,
  React Native, TypeScript *and* Vue; the posting says "React, Angular or Vue".
- **Words read as skills:** "Networking" in a web production internship (from
  "social networking"), and "Excel" for an embedded internship.
- **Everything counted as required:** OpenTable's staff ML role lists **28**
  required skills because the description has no requirements heading.
- **"Golang" missed:** "Golang" with a capital G isn't recognised. Canonical's
  "Senior Software Engineer – Python/Golang – Kubernetes" (#17093) reads as
  needing Python, Linux and Kubernetes but not Go, so the 10-year Go engineer
  scores **53**.
- **Bachelor's degrees score as no degree:** the resume reader stores
  `"bachelors"` but the scorer looks up `"bachelor"`, so anyone with a
  bachelor's gets **2 of 10** education points whenever a posting asks for
  one. The frontend student lost 8 points on Verkada for this.

## 4. Ten examples where recommendations don't fit

From `recommend()` exactly as the API runs it, over 12,392 open tech postings
with high ghost risk left out.

| # | Persona | Recommended (score) | What's wrong |
|---|---|---|---|
| 1 | non_tech | Voyager, **Systems Engineer III** (senior) – 78 | A café supervisor's top match is a senior aerospace engineering role. |
| 2 | non_tech | Wachter, Fire/Security Alarm Installation Technician – 75; Aevex, Facility Security Officer – 75 | Matches on the "security" role type, not on anything the person did. |
| 3 | non_tech | Barr, Electrical Engineer – Entry Level – 74 (listed twice) | An engineering degree role, and the same posting twice. |
| 4 | frontend_student | Shure, Automated Test Software Engineering Intern – 90; Shure, Automated Test Engineer Intern – Hardware – 81 | Test and hardware roles rank above real frontend internships, because "Testing" and "Git" matched. |
| 5 | frontend_student | Lyft, Software Engineer Intern, Frontend – **Mexico City**; Nimble Robotics, Integration Test **Technician** – 75 | Location is never considered (the student is in Toronto), and a technician role is a "75". |
| 6 | embedded_student | **All 10** results are "FPGA Engineer Intern", every one at **96** | One side project dominates; no firmware internships appear, though firmware is the student's actual work. Ties are broken only by age. |
| 7 | data_new_grad | Johns Hopkins APL, **PhD Graduate** – Statistics and Data Science – 95 | The top match requires a PhD; the person has a BSc. |
| 8 | data_new_grad | Akuna, Software Engineer – Python – 94; Sajix, Python Developer – 94 | Software roles outrank data analyst roles because "Python" matched. |
| 9 | senior_backend | Mastercard, Lead Software Engineer – **Pune, India**; Senior Software Engineer – **Oslo**; GitLab, **Engineering Manager** | Location ignored, and a management role for an IC; meanwhile Go roles score low because "Golang" isn't recognised. |
| 10 | frontend_student, data_new_grad | Meridian Partners, Python Software Engineer Co-op – 85, **twice**; Medpace Python Developer Intern and Python Intern – 85 | Duplicate postings fill the list, and nothing keeps it varied. |

## 5. What the failures have in common

1. **There's no target.** Strength never asks what the person wants, and recommendations never ask where.
2. **Words, not meaning.** About 90 regexes decide what a skill is, frequency decides what a term is, and nothing knows that STM32 is embedded C work or that "SevenRooms" is a company.
3. **One number hides the reasons.** Several real bugs (education, Golang, alternatives) lived unnoticed inside a sum of six parts.
4. **No measurement.** There's no labelled set, so none of this could be caught by a test or a metric. The plan (`docs/resume-model-plan.md`) starts by fixing that.
