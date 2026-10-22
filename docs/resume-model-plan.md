# Resume models: plan

**Status: proposal, waiting for approval. No code until it's approved.**

Based on `docs/resume-model-audit.md` (what's wrong today) and
`docs/resume-model-research.md` (models, taxonomies, data, storage).

## Goals

1. **Two scores that mean something.**
   - *Resume quality* needs no job.
   - *Fit* is always against a specific job, or against a clearly named set of real postings.
2. **"Words to add"** lists only real skills and requirements from the posting, split into must-have and nice-to-have, and never anything the person shows no sign of having.
3. **Recommendations** fit the person's role, level, location and experience, each with a reason.
4. **Measured improvement.** Every change is scored on a held-out labelled set against today's system, and a stage is kept only if it wins.

**Not in scope yet:** the daily "new matches" feed and email digest. The data
model below is designed for them, but neither is built.

## Ground rules

- Models run on CPU inside our API. No paid AI services or external APIs.
- I'll ask before adding any dependency over 50 MB. Model code stays out of the nightly ingest itself; embeddings get their own step.
- No writes to Neon without asking. All work is tested against a local database.
- Resume text is never logged, never sent anywhere, and real user resumes are never committed. **The repository is public**, so the evaluation set in the repo holds only synthetic resumes.
- Tests run in CI. Lint, build and the Playwright tests keep passing.
- Commits have no AI attribution and nothing is pushed.

## 1. The three outputs, redefined

### 1a. Resume quality (no job)

**What it measures:** how well the resume is written, independent of any job.

| Area | Signals |
|---|---|
| Structure | the expected sections for the person's stage; contact details; dates on every role |
| Impact bullets | action verb, what was done, and the result; not a duty ("responsible for…") |
| Numbers | the share of bullets with a measurable result (scale, %, time, money) |
| Clarity | bullet length, one page for students, consistent tense and date format, no duplicate or filler bullets |

How it changes from today:
- **Diminishing returns.** Adding bullets helps only up to a point, and near-duplicate bullets count once. The padding trick from the audit (92 → 100) stops working; there's a test for exactly that.
- **Rules depend on career stage.** A staff engineer isn't told to add a portfolio.
- **One label on the page:** "Resume quality". It never says "fit", and the page explains it isn't about any job.
- **Calibrated against you.** The weights are checked against your own quality ratings of the synthetic personas.

### 1b. Fit to a specific job

Fit is shown **only** next to a job. The API returns no fit score without a job
id or a named comparison set, and the UI has no place to show one.

| Part | What counts |
|---|---|
| Must-have requirements | skills and named requirements in the posting's required section, normalised through the taxonomy. "React, Angular or Vue" is one requirement met by any of the three. |
| Nice-to-haves | the same, from the preferred section |
| Years | years asked for vs dated experience; internships count partly |
| Level | intern / new grad / mid / senior vs the person's stage |
| Education | degree and field, counting degrees in progress (fixes the "bachelors" bug) |
| Location and eligibility | where the job is vs where the person is or will move to; remote; hard requirements such as citizenship, security clearance, "currently enrolled" or a PhD |
| Title and role similarity | embedding similarity of the resume's recent titles and the posting's title (stage 4) |

**Hard requirements cap the score and say why.** For example: "Requires US
security clearance: capped at 30." Ghost risk isn't part of fit; it's shown
beside it and used in ranking.

**Output:** a score, a label (strong, okay, weak), and every part with a one-line reason.

### 1c. The no-job default

When no job is picked, the Resume page compares the resume with **real open
postings for the person's target role**:

1. **Target role.** The page asks for it: role, level, and location or remote. Until the person answers, it's inferred from the resume (recent titles, then skills) and the page says "We guessed *Frontend · Intern · Toronto*. Change it."
2. **Comparison set.** Up to 50 open postings matching the target, low ghost risk, newest first.
3. **What it shows,** under a clear heading, "Compared with 50 open Frontend internship postings in Toronto":
   - the median fit and its range;
   - the must-haves most of those postings ask for and the resume doesn't show ("31 of 50 ask for TypeScript: you list it but don't show it in a bullet");
   - three of the closest postings.

It never shows a bare "fit" number without the comparison set named next to it.

## 2. Skills and "words to add"

### Skill taxonomy (stage 2)

A data file in the repo, `tracker/data/skills.yaml`. Each skill has:
- a canonical name;
- aliases ("Golang", "Postgres", "k8s"), with case rules for ambiguous names (Go, R, C);
- a kind: language, framework, tool, platform, concept or certification;
- a group (frontend, embedded, data…);
- **related** links (Next.js → React, PostgreSQL → SQL, STM32 → embedded C).

Where it comes from:
- today's ~90 curated skills;
- **O\*NET Technology Skills** (CC BY 4.0) and **ESCO** (EU attribution licence) for breadth and relations;
- what our postings actually ask for: a report lists frequent unknown terms so the file can grow.

A build script regenerates the file from the downloads, and the licence credit
goes on the site.

### Requirement extraction

- **Section split, extended.** Today's heading split also looks at sentence cues ("must", "required", "minimum" vs "preferred", "bonus", "a plus", "nice to have").
- **Boilerplate removed.** Company names (from the companies table), benefits, equal-opportunity text, pay text and HTML leftovers are dropped before anything is extracted.
- **Alternatives grouped.** "X, Y or Z" and "X/Y" become one any-of requirement.
- **Named non-skill requirements kept:** degree, years, clearance, enrolment and work authorisation.
- **Frequency key terms removed entirely.**

### "Words to add"

For a resume and a posting:

1. Take the posting's requirements that the resume doesn't show, split into **must-have** and **nice-to-have**.
2. Keep one only if the resume shows **evidence the person plausibly has it**:
   - a related skill on the resume (taxonomy link: "You use PostgreSQL. The posting says SQL. Name it."), **or**
   - in stage 4, a resume bullet whose meaning is close to the requirement ("You 'moved 40 services to EKS'. The posting asks for Kubernetes.").
3. Each suggestion shows its evidence, quoted from the resume.
4. Requirements with no evidence never appear as "add". They go to a separate **"Gaps to learn"** list, framed as things to learn, not words to type.
5. The current reminder stays: "Only add what's true."

## 3. Recommendations (stage 4)

1. **Recall.** Find the 300 open postings nearest the resume's embedding (pgvector, cosine), within the person's filters: location or remote, a level band (one level either side) and ghost risk. Add postings that match the target role's title or share must-have skills, so a strong match isn't missed because of wording.
2. **Rerank** with an explainable model over these features:
   - must-have coverage and nice-to-have coverage;
   - years fit and level fit;
   - education and eligibility gates;
   - location match;
   - title similarity and embedding similarity;
   - ghost risk and freshness.

   It starts as hand-set weights. Once there are labels, it becomes a logistic regression fitted on the tuning split: about 12 weights in a versioned JSON file, run with numpy, with no model library in the API.
3. **Variety.** Duplicate postings (same fingerprint, or same company and title) collapse into one, and at most 2 per company appear in the top 10.
4. **Reasons.** Every result names its top two reasons and its main gap, in words: "Matches 5 of 6 must-haves · Internship, Toronto · Missing: Kubernetes".

## 4. Embeddings

**Model.** Start with bge-small-en-v1.5 (MIT, 33M, 384 dimensions), compared
on our evaluation set with gte-small, e5-small-v2, arctic-embed-s and
MiniLM-L6. It runs through ONNX Runtime; whether to use int8 or fp32 is
measured on our CPU.

**What gets embedded:**
- *Postings:* title, plus the requirements section, plus skills, trimmed to 512 tokens.
- *Resumes:* recent titles, summary, skills, and the top bullets of the latest roles.

**Postings, computed once:**
- A new command, `ghostless embed`, runs as its own workflow job after `finish`. It embeds only new or changed postings, detected by a hash of the embedded text, so the nightly ingest itself doesn't load a model.
- The first backfill (about 59,000 postings) runs once.
- Embeddings are stored in a new `job_embeddings` table: job id, model version, `halfvec(384)`, text hash and time, with an HNSW cosine index.
- They're kept for open postings and deleted 30 days after a posting closes.
- That's about **2 KB per posting, ~120 MB today**, against a 603 MB database (5 GB allowed). Writes don't count toward transfer, and a recommendation query moves about 4 KB.

**Resumes, embedded when uploaded:**
- *Accounts:* the embedding is stored with the resume (a new column on `resumes`).
- *Guests:* only the analysis is kept, in the browser, as today. The API returns the embedding quantised to about 400 bytes inside the analysis, and the browser sends it back with recommendation requests. No resume text is stored for guests.

**In the API:**
- The model loads once per process, on first use (about 35–130 MB of memory, depending on precision).
- A switch, `GHOSTLESS_RESUME_MODEL`, lets it be turned off; scoring then falls back to the non-embedding features.

## 5. Training data and labels

**Synthetic personas, in the repo.** About 40 invented resumes covering:
- roles: software, data, ML, embedded, security;
- levels: intern to senior;
- locations: Canada, US, remote;
- hard cases: career changer, non-tech, bootcamp graduate, international student, PhD.

I write them; you review them. They live in `eval/resume/personas/`, are
synthetic, and are clearly marked as such.

**Postings for labelling.** Real open postings, referenced **by id and text
hash** in the repo. The full posting text is snapshotted to a private local
folder (`data/private/`, git-ignored), so labels stay usable after a posting
closes. Employer text doesn't get republished in the public repo.

**Your labels.** At least **150 resume–job pairs**, aiming for 300. Each pair
gets:
- **strong**, **okay** or **weak**;
- a tick or cross on each suggested "word to add".

Pairs come from pooling, so the judged set isn't biased toward one system:
- today's top results;
- each candidate system's top results;
- random postings of the same role;
- deliberate hard negatives: the right role at the wrong level, or a different country.

Labelling runs through a small local tool, `ghostless label-resume`. It shows
the persona's summary next to the posting's requirements, takes one key per
label, and saves after each answer. Estimate: about 30–45 seconds a pair, so
**2–3 hours for 300**.

**Weak labels from our own data.** Used for training and sanity checks only,
**never for evaluation**:
- a posting's title against its own requirements;
- duplicate postings;
- job-list categories (role, level);
- each persona's stated target role.

**User data.**
- Never trained on without explicit, separate consent: a setting, off by default, with its wording versioned and the time it was given recorded.
- Even with consent, the first use is feedback labels (saved, applied, not interested) joined to embeddings computed on our server. Resume text never leaves the database for training.
- Using resume text itself would be a new request, asked for separately.

## 6. Evaluation

**Built first, before any model work.**

- **Split.** About 30% of the **personas**, with all their pairs, form the held-out set. Splitting by persona, not by pair, means no tuning ever sees those resumes. The split is frozen with a hash file, and a test fails if it changes.
- **Command.** `ghostless evaluate-resume [--holdout] [--system NAME]` runs any system on the set and writes a report.

**Metrics:**

| What | Metric | Notes |
|---|---|---|
| Recommendations | **NDCG@10** (strong = 2, okay = 1, weak = 0) and **precision@10** (strong or okay) | Per persona, then averaged. "Judged@10" is reported too; unjudged results count as weak and are flagged for labelling. |
| Fit score | Spearman correlation with your labels; accuracy and weighted kappa after mapping scores to strong/okay/weak | The mapping thresholds are set on the tuning split only |
| Words to add | **precision** (share you ticked as valid) and a **harmful count** (skills suggested that the persona doesn't have) | The harmful count must be 0 for a stage to ship |
| Resume quality | Spearman with your quality ratings, plus a padding test | Filler must never raise the score |
| Speed | p95 time for analyse and for recommendations on the API's CPU | Budget: analyse under 1 s, recommendations under 1.5 s |

**The baseline comes first.** Today's system is measured on the set before
anything changes, and the numbers are recorded in `docs/resume-model-results.md`.

## 7. Stages

Each stage ends with an evaluation on the **held-out** set, compared with the
previous stage. It's kept only if it's better on that stage's target metric
and no worse elsewhere beyond noise. If not, it's reverted and noted in
`docs/resume-model-results.md`.

| Stage | Builds | Needs from you | Target metric |
|---|---|---|---|
| **1. Evaluation set** | Personas; posting snapshots; `ghostless label-resume`; `ghostless evaluate-resume`; **baseline report** | Review the personas; label 150–300 pairs | (baseline) |
| **2. Skills and "words to add"** | `skills.yaml` and its build script; new requirement extraction (alternatives, sections, boilerplate, company names); evidence-based suggestions; fixes for the Golang, bachelor's and alternatives bugs | Nothing new (data files only, with licence credits) | Words-to-add precision up, harmful = 0; fit agreement not worse |
| **3. Quality and fit split** | The new quality score; fit only with a job; the target-role default with a named comparison set; API and UI changes on the Resume and Matches pages | Look over the new screens | Quality–label correlation; padding test; fit agreement |
| **4. Embeddings and recommendations** | ONNX model; `ghostless embed` workflow step; `job_embeddings` table (migration); resume embeddings; recall + feature reranker + variety | **Approve dependencies**: onnxruntime (~24 MB wheel), tokenizers (~3 MB) and the model file (~35–130 MB, downloaded at build time, not committed). **Approve the Neon write**: the migration and the ~59,000-row backfill | NDCG@10 and P@10 up; speed within budget |
| **5. Fine-tuning** (only if needed) | Fine-tune the embedding model on weak pairs and/or the reranker on labels, in a separate training environment (PyTorch, not deployed) | **Approve the training environment** (PyTorch ~555 MB, dev only); enough labels (about 1,000+ pairs or consented feedback) | Must beat stage 4 on the held-out set |

## 8. Designed now, built later: "new matches for you"

Not built now, but the stage 4 tables are shaped for it:

- **`user_job_fit`:** user, resume, job, score, reasons (JSON), model version, time. After each ingest, a step scores **only the postings new since the last run** for **opted-in** users. That's one vector query plus reranking per user, a few milliseconds each, so it stays cheap as users grow.
- **Feedback as labels:**
  - saved and applied already exist (`saved_jobs`, `application_events`);
  - a new "not interested" action, with an optional reason (level, location, role, company), goes in `match_feedback`.
  - Feedback becomes training labels only for users who gave consent.
- **Email digest:** opt-in only, sent from the stored `user_job_fit` rows. No scoring at send time.

## 9. Risks and open questions

- **Label time is the main cost.** 300 pairs is about 2–3 hours of your time, and the quality of everything after stage 1 depends on it.
- **Taxonomy coverage.** ESCO's coverage of frameworks and tools is unknown until measured. O\*NET and our own list should cover tech well.
- **Your API host's memory and CPU** decide int8 vs fp32 and whether the model stays loaded. This gets measured in stage 4.
- **Neon plan:** Neon's docs don't show a "Build" plan; the estimates use your figures (5 GB, 25 GB a month). Even with generous rounding, embeddings stay under 200 MB.
- **Non-English postings** are out of scope for now (bge-small is English-only).

## 10. What I need from you to start

1. **Approval of this plan**, or changes to it.
2. **Stage 1:** a look at the personas once written, then 2–3 hours of labelling.
3. **Stage 4,** when we get there: approval of the dependencies and model download, and of the Neon migration and backfill.
