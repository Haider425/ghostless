# Resume evaluation set

The labelled set the resume models are measured on (`docs/resume-model-plan.md`, stage 1).

| File | What it is | Committed? |
|---|---|---|
| `personas.yaml` | 40 synthetic resumes in tech, each with the role, level and place it targets | yes |
| `personas_fields.yaml` | 60 more in twelve other fields (accounting to hospitality), including 12 people moving into tech | yes |
| `split.json` | the 30 personas held out from all tuning, chosen by a hash of their id: adding personas never moves one | yes |
| `pairs.jsonl` | the postings chosen for each persona (8 in tech, 6 moving into tech, 3 outside tech), by id and text hash | yes |
| `labels.jsonl` | your labels for the persona pairs | yes |
| `private/` | everything else, **git-ignored, never committed** | no |
| `private/postings.jsonl` | the text of every chosen posting, so labels outlive the posting | no |
| `private/resumes/` | real resumes, shared with permission | no |
| `private/pairs.jsonl`, `private/labels.jsonl` | their pairs and labels | no |

## Labelling

```
ghostless label-resume          # label: one pair at a time, saved after each answer
ghostless label-resume status   # how many are done
```

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

- **strong:** a good fit; apply.
- **okay:** worth applying; a stretch or a partial fit.
- **weak:** not a fit (wrong field, wrong level, a hard requirement they don't meet, or the wrong country for them).

Pairs come round-robin across resumes, so stopping early still covers every
person. There are 536 in all: the 320 for the tech personas matter most (at
least 150 of them). The 216 for people outside tech are quick: most are clearly
weak, and that's still worth labelling, since it teaches the model what *doesn't*
transfer.

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
