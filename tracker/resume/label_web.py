"""`ghostless label-resume --web`: the labelling tool as a local web page.

Served only on 127.0.0.1, never on the network and never as part of the public
website, because it shows private resumes. Requests whose Host or Origin isn't
this machine are refused (so another site in the browser can't read or write
through it). Labels go to the same files the terminal tool uses
(tracker/resume/evalset.py), so the two can be used in turn.

Pre-labels are only ever sent in review mode, and never for held-out pairs:
that's decided here on the server, not in the page.
"""

from __future__ import annotations

import html
import re
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from tracker.resume import evalset
from tracker.resume.evalset import Label, Resume
from tracker.resume.posting import line_kinds
from tracker.skills import SKILL_PATTERNS, extract_skills

HOST = "127.0.0.1"
MODES = ("label", "review")


# ---------- text with highlights ----------


def _skill_spans(text: str, skills: set[str]) -> list[tuple[int, int]]:
    spans = sorted(
        m.span() for name in skills for m in SKILL_PATTERNS[name].finditer(text) if m.end() > m.start()
    )
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _marked(line: str, skills: set[str]) -> str:
    out, at = [], 0
    for start, end in _skill_spans(line, skills):
        out.append(html.escape(line[at:start]))
        out.append(f'<mark class="skill">{html.escape(line[start:end])}</mark>')
        at = end
    out.append(html.escape(line[at:]))
    return "".join(out)


def resume_html(text: str, shared: set[str]) -> str:
    return "\n".join(
        f'<div class="ln">{_marked(line, shared) or "&nbsp;"}</div>' for line in text.splitlines()
    )


def posting_html(description: str, shared: set[str]) -> str:
    """The whole posting, each line tagged with the part it's in (requirements,
    nice-to-haves, duties, boilerplate), skills shared with the resume marked."""
    rows = []
    for line, kind in line_kinds(description or ""):
        rows.append(f'<div class="ln k-{kind}">{_marked(line, shared) or "&nbsp;"}</div>')
    return "\n".join(rows)


# ---------- the app ----------


def create_app(port: int):
    from tracker.resume.label import _all_resumes, pairs_to_label
    from tracker.resume.label_web_page import PAGE

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    allowed_hosts = {f"{HOST}:{port}", f"localhost:{port}"}
    allowed_origins = {f"http://{h}" for h in allowed_hosts}

    state: dict = {}

    def load() -> dict:
        if not state:
            state["resumes"] = {r.id: r for r in _all_resumes()}
            state["postings"] = evalset.load_postings()
            state["holdout"] = evalset.load_split() if evalset.SPLIT.exists() else set()
            state["prelabels"] = evalset.load_prelabels()
        return state

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        client = request.client.host if request.client else ""
        origin = request.headers.get("origin")
        if (
            client not in ("127.0.0.1", "::1", "testclient")
            or request.headers.get("host") not in allowed_hosts
            or (origin is not None and origin not in allowed_origins)
        ):
            return JSONResponse({"detail": "local use only"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    def is_holdout(resume: Resume) -> bool:
        return evalset.is_holdout(resume, load()["holdout"])

    @app.get("/", response_class=HTMLResponse)
    def page():
        return PAGE

    @app.get("/api/pairs")
    def pairs(mode: str = "label", part: str = "all", persona: str = ""):
        s = load()
        if mode not in MODES or part not in ("all", "holdout", "tuning"):
            raise HTTPException(400, "unknown mode or part")
        if mode == "review":
            part = "tuning"  # never held-out pairs
        order = pairs_to_label(s["resumes"], s["postings"], part, persona or None)
        labels = evalset.load_labels()
        counts = {f: 0 for f in evalset.FITS}
        items = []
        for p in order:
            lab = labels.get(p.key())
            if lab and lab.fit in counts:
                counts[lab.fit] += 1
            job = s["postings"][p.job]
            items.append(
                {"resume": p.resume, "job": p.job, "title": job["title"], "company": job["company"],
                 "fit": lab.fit if lab else None}
            )  # fmt: skip
        personas = sorted({p.resume for p in evalset.load_pairs() if p.resume in s["resumes"]})
        return {"items": items, "counts": counts, "personas": personas, "part": part}

    @app.get("/api/pair")
    def pair(resume: str, job: int, mode: str = "label"):
        s = load()
        r = s["resumes"].get(resume)
        posting = s["postings"].get(job)
        found = next((p for p in evalset.load_pairs() if p.resume == resume and p.job == job), None)
        if r is None or posting is None or found is None:
            raise HTTPException(404, "no such pair")
        shared = set(extract_skills(r.text)) & set(extract_skills(posting.get("description") or ""))
        lab = evalset.load_labels().get((resume, job))
        pre = None
        if mode == "review" and not is_holdout(r):
            pre = s["prelabels"].get((resume, job))
        t = r.target
        return {
            "resume": {
                "id": r.id,
                "summary": r.summary,
                "real": r.real,
                "holdout": is_holdout(r),
                "field": r.field,
                "target": asdict(t) if t else None,
                "html": resume_html(r.text, shared),
            },
            "posting": {
                "id": job,
                "company": posting["company"],
                "title": posting["title"],
                "location": posting.get("location"),
                "level": posting.get("level"),
                "role": posting.get("role_type"),
                "url": posting.get("url"),
                "html": posting_html(posting.get("description") or "", shared),
            },
            "shared": sorted(shared),
            "source": found.source,
            "candidates": found.candidates,
            "label": asdict(lab) if lab else None,
            "prelabel": {"fit": pre.fit, "reason": pre.reason} if pre else None,
        }

    @app.post("/api/label")
    async def save(request: Request):
        if not request.headers.get("content-type", "").startswith("application/json"):
            raise HTTPException(415, "JSON only")
        body = await request.json()
        s = load()
        resume = s["resumes"].get(body.get("resume"))
        job = body.get("job")
        fit = body.get("fit")
        if resume is None or not isinstance(job, int) or fit not in evalset.FITS:
            raise HTTPException(400, "resume, job and fit (strong, okay or weak) are needed")
        if not any(p.resume == resume.id and p.job == job for p in evalset.load_pairs()):
            raise HTTPException(404, "no such pair")
        terms = {str(k): bool(v) for k, v in (body.get("terms") or {}).items()}
        note = re.sub(r"\s+", " ", str(body.get("note") or "")).strip()[:300]
        via = ""
        if body.get("mode") == "review" and not is_holdout(resume):
            pre = s["prelabels"].get((resume.id, job))
            if pre:
                via = "review-accepted" if pre.fit == fit else "review-corrected"
        evalset.save_label(Label(resume.id, job, fit, terms, note=note, via=via), real=resume.real)
        return {"saved": True, "via": via}

    return app


def serve(port: int = 8765) -> None:
    import uvicorn

    print(f"Labelling at http://{HOST}:{port}  (only on this computer; Ctrl+C to stop)", flush=True)
    uvicorn.run(create_app(port), host=HOST, port=port, log_level="warning")
