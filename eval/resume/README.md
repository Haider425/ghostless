# Resume evaluation set

The labelled set the resume models are measured on (`docs/resume-model-plan.md`, stage 1).

| File | What it is | Committed? |
|---|---|---|
| `personas.yaml` | 40 synthetic resumes in tech, each with the role, level and place it targets | yes |
| `personas_fields.yaml` | 60 more in twelve other fields (accounting to hospitality), including 12 people moving into tech | yes |
| `split.json` | the 30 personas held out from all tuning, chosen by a hash of their id: adding personas never moves one | yes |
| `pairs.jsonl` | the postings chosen for each persona, by id and text hash (see "Balancing the pools") | yes |
| `labels.jsonl` | your labels for the persona pairs | yes |
| `prelabels.jsonl` | Claude's label and one-line reason for each persona pair, kept apart from yours | yes |
| `second_labels.jsonl` | a second, blind Claude pass over the held-out pairs (it never saw the pre-labels) | yes |
| `results/` | the latest `ghostless evaluate-resume` numbers for each system (ids and numbers only) | yes |
| `private/` | everything else, **git-ignored, never committed** | no |
| `private/postings.jsonl` | the text of every chosen posting, so labels outlive the posting | no |
| `private/resumes/` | real resumes, shared with permission | no |
| `private/pairs.jsonl`, `private/labels.jsonl` | their pairs and labels | no |

## Labelling

```
ghostless label-resume --web            # label in a local web page (recommended)
ghostless label-resume                  # label in the terminal: one pair at a time
ghostless label-resume --holdout        # only the held-out pairs (or --tuning)
ghostless label-resume review           # tuning pairs: see the pre-label, accept or correct it
ghostless label-resume agreement        # how often your labels and the pre-labels agree
ghostless label-resume status           # how many are done
```

Both tools save after every label to the same files, so you can switch between
them at any point.

**The web page** runs on `http://127.0.0.1:8765` (`--port` to change it). It is
served only on this computer, never on the network, and it isn't part of the
website: it refuses any request whose host or origin isn't this machine. The
resume is on the left and the full posting on the right, each scrolling on its
own. Requirement lines are tinted, nice-to-haves too, and skills found in both
are highlighted. Keys: **s**, **o**, **w** to label, **k** to skip, **b** to go
back, **n** to type a note (Esc to leave it). In review mode, **a** or Enter
accepts the pre-label. Filter by persona, and by held-out or tuning.

**Blind and review.** Held-out pairs are always labelled blind: neither tool
shows a pre-label for them, in any mode (the server never sends one). Review
mode only offers tuning pairs. A label given in review is marked `via:
review-accepted` or `review-corrected`; accepted ones are left out of the
agreement numbers, since they agree by construction.

For each pair you see the resume (and what the person wants), then what the
posting asks for. Press **s** (strong), **o** (okay) or **w** (weak). Other keys:
- **f** shows the full posting;
- **r** shows the resume again;
- **k** skips the pair;
- **b** goes back to the previous pair;
- **q** quits. Nothing is lost: run the command again to carry on where you stopped.

Then you get the words a system might tell this person to add. Type the
numbers of the ones that are **fair to suggest**: a real requirement of the
posting **and** something this person plausibly has. Press Enter if none are.

**What the labels mean.** Judge whether you'd tell this person to apply:

- **strong:** you'd tell them to apply today.
- **okay:** worth applying, with one real mismatch (wrong city, a different specialty, some key skills missing).
- **weak:** wrong field or level, not eligible, or most requirements missing.

**Another country.** A posting in another country is one mismatch (okay at
best) when the person is a student or new grad and the posting is an internship
or new grad role at their level, since many Canadian students apply to US
internships. Otherwise it's weak, unless the posting is remote in the person's
own country. A different city in the same country is one mismatch. Career
changers aiming at entry-level roles don't count as students or new grads here,
and a posting that only takes students of its own country's schools is "not
eligible", so weak.

## Balancing the pools

```
ghostless label-resume rebalance --db <local database URL>
```

The first pools came out mostly weak (wrong level, other country, random), which
leaves too few strong pairs to measure ranking on. `rebalance` evens them out,
aiming at roughly a third each:

- **likely strong** (up to 4 per person after a tech role): the right role and
  level, in their city or remote in their country, and today's matcher rates it
  a good fit (50 and up);
- **likely okay** (up to 4): exactly one mismatch, taken in turn from each kind:
  another city in their country, some key skills missing (35 to 49), a
  different specialty, or a student's internship or new grad role abroad;
- **weak**, kept as a check: 2 per person after a tech role (where today's
  matcher was wrong first, then a deliberate near miss: wrong level, other
  country or random), and 1 per person staying in a field Ghostless doesn't
  list, since every posting is weak for them.

Without `--db` it only trims the weak pairs. One posting per company per person. It never drops a labelled pair, it drops
the pre-labels of pairs it drops, and running it again changes nothing. The
held-out split is by person, as before, so new pairs go to the same side as
their person's others. New pairs need pre-labels: `status` says how many lack one.

Pairs come round-robin across resumes, so stopping early still covers every
person. The pairs for people after a tech role matter most. The ones for people
staying outside tech are quick: they're clearly weak, and that's still worth
labelling, since it teaches the model what *doesn't* transfer.

## How it's scored

```
ghostless evaluate-resume              # today's matcher on the held-out set
ghostless evaluate-resume --tuning     # on the tuning set (against the pre-labels)
```

Ranking is measured with graded relevance: strong = 2, okay = 1, weak = 0, so
an okay posting counts as a partial match. NDCG@10 per person, then averaged;
see `docs/resume-model-plan.md` for the full list of measures, and
`docs/resume-model-results.md` for the results so far.

**The answer key** (`evalset.answer_key`), most trusted first:

1. a person's label, from `labels.jsonl`;
2. otherwise, where the pre-label and the blind second pass agree, that label.
   Reports call these **"Claude-labelled, provisional"**;
3. pairs the two Claude passes disagree on are left out of the scores.

`ghostless label-resume agreement` shows how the two passes agree, with
examples. Users' feedback (applied = strong, saved = okay, not interested =
weak, only with their consent: `tracker/resume/feedback.py`) is in the same
form, so it can take the place of these labels later.

## Adding real resumes (evaluation only)

1. Put the files (PDF, Word or text) in `eval/resume/private/resumes/`. Only add resumes whose owners have said yes.
2. Run `ghostless label-resume pool --db <database URL>`. For each new resume it writes `<name>.yaml` next to it with a guess at what the person targets, and stops there.
3. **Edit that file**: role, level, location, country, remote_ok and title words. Then run `pool` again: it now chooses that resume's postings.
4. Label as usual.

**Scanned resumes** (PDFs that are pictures, with no text in them) are read by
text recognition, on your machine only (`tracker/resume/ocr.py`). It takes a
one-time setup:

```
pip install -e ".[ocr]"
mkdir -p ~/.cache/ghostless/ocr
curl -L -o ~/.cache/ghostless/ocr/en_PP-OCRv3_rec_infer.onnx \
  https://huggingface.co/SWHL/RapidOCR/resolve/main/PP-OCRv3/en_PP-OCRv3_rec_infer.onnx
```

That's RapidOCR's English model (9 MB, Apache-2.0). Without it, scanned files
are skipped and named by id. Expect a few seconds per page.

Real resumes are always held out, never used for tuning, and their text is never logged. To remove one, delete its file, its `.yaml` and its lines in `private/pairs.jsonl` and `private/labels.jsonl`.

**Which database for `pool`.** Use a local copy. Passing Neon's URL works, but
reading the job pool and descriptions counts toward its transfer, about 10–20
MB per run.
