"""The page for `ghostless label-resume --web` (tracker/resume/label_web.py).

One self-contained HTML page: no build step, no outside scripts or fonts, so
nothing it shows ever leaves this computer."""

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Resume labels</title>
<style>
  :root {
    --paper: #fbf7f0; --surface: #ffffff; --ink: #17140f; --soft: #5c564c; --line: #e3dccd;
    --accent: #0a62c2; --req: #fff4cc; --pref: #e3f0ff; --skip: #9a9286; --skill: #c8f0d4;
    --strong: #1d7a46; --okay: #9a6a00; --weak: #b42a24;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --paper: #191713; --surface: #23201b; --ink: #f3efe7; --soft: #bdb6a9; --line: #3a352e;
      --accent: #6aaef5; --req: #3a3220; --pref: #1c2b3c; --skip: #8a8276; --skill: #1e4a2e;
      --strong: #5fd394; --okay: #f0c35a; --weak: #ff8a7e;
    }
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body { background: var(--paper); color: var(--ink); font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
         display: flex; flex-direction: column; }
  header { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; padding: 10px 16px;
           border-bottom: 1px solid var(--line); background: var(--surface); }
  header h1 { font-size: 16px; margin: 0 8px 0 0; }
  select, input[type=text] { font: inherit; color: var(--ink); background: var(--paper); border: 1px solid var(--line);
                             border-radius: 8px; padding: 5px 8px; }
  .modes button { font: inherit; border: 1px solid var(--line); background: var(--paper); color: var(--ink);
                  padding: 5px 12px; cursor: pointer; }
  .modes button:first-child { border-radius: 8px 0 0 8px; }
  .modes button:last-child { border-radius: 0 8px 8px 0; border-left: 0; }
  .modes button[aria-pressed=true] { background: var(--accent); color: #fff; border-color: var(--accent); }
  .progress { flex: 1 1 260px; min-width: 220px; }
  .bar { height: 8px; border-radius: 99px; background: var(--line); overflow: hidden; }
  .bar > div { height: 100%; background: var(--accent); width: 0; transition: width .2s; }
  .counts { font-size: 13px; color: var(--soft); margin-top: 3px; }
  .counts b.s { color: var(--strong); } .counts b.o { color: var(--okay); } .counts b.w { color: var(--weak); }
  main { flex: 1; display: grid; grid-template-columns: 1fr 1fr; min-height: 0; }
  section { display: flex; flex-direction: column; min-height: 0; border-right: 1px solid var(--line); }
  section:last-child { border-right: 0; }
  .head { padding: 12px 16px; background: var(--surface); border-bottom: 1px solid var(--line); }
  .head h2 { font-size: 17px; margin: 0 0 4px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; font-size: 13px; }
  .chip { background: var(--paper); border: 1px solid var(--line); border-radius: 99px; padding: 1px 9px; }
  .chip.hold { border-color: var(--weak); color: var(--weak); }
  .scroll { overflow: auto; padding: 12px 16px 24px; flex: 1; }
  .text { font: 14px/1.55 ui-monospace, "Cascadia Code", Consolas, monospace; white-space: pre-wrap; word-break: break-word; }
  .ln { padding: 0 6px; border-radius: 4px; }
  .k-required { background: var(--req); }
  .k-preferred { background: var(--pref); }
  .k-heading { font-weight: 700; margin-top: 6px; }
  .k-skip { color: var(--skip); }
  mark.skill { background: var(--skill); color: inherit; border-radius: 3px; padding: 0 1px; }
  .legend { font-size: 12px; color: var(--soft); margin-top: 6px; display: flex; gap: 10px; flex-wrap: wrap; }
  .legend span { padding: 0 6px; border-radius: 4px; }
  footer { background: var(--surface); border-top: 1px solid var(--line); padding: 10px 16px; display: grid; gap: 8px; }
  .row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .big { font: 600 16px system-ui, sans-serif; padding: 12px 22px; border-radius: 12px; border: 2px solid transparent;
         cursor: pointer; color: #fff; }
  .big kbd { font: 12px ui-monospace, monospace; opacity: .8; margin-left: 6px; }
  .b-strong { background: var(--strong); } .b-okay { background: var(--okay); } .b-weak { background: var(--weak); }
  .b-plain { background: var(--paper); color: var(--ink); border-color: var(--line); }
  .b-accept { background: var(--accent); }
  .big.current { outline: 3px solid var(--ink); outline-offset: 2px; }
  .review { display: none; padding: 8px 12px; border-radius: 10px; background: var(--pref); }
  .review.on { display: flex; }
  .note { flex: 1 1 280px; }
  .terms { font-size: 14px; color: var(--soft); }
  .terms label { margin-right: 12px; white-space: nowrap; color: var(--ink); }
  .msg { font-size: 13px; color: var(--soft); }
  .done { padding: 40px; text-align: center; color: var(--soft); }
  @media (max-width: 900px) { main { grid-template-columns: 1fr; } section { border-right: 0; border-bottom: 1px solid var(--line); } }
</style>
</head>
<body>
<header>
  <h1>Resume labels</h1>
  <div class="modes" role="group" aria-label="Mode">
    <button id="m-label" aria-pressed="true">Label (blind)</button>
    <button id="m-review" aria-pressed="false">Review pre-labels</button>
  </div>
  <label>Pairs <select id="part">
    <option value="all">All</option><option value="holdout">Held out (blind)</option><option value="tuning">Tuning</option>
  </select></label>
  <label>Persona <select id="persona"><option value="">All personas</option></select></label>
  <div class="progress">
    <div class="bar"><div id="bar"></div></div>
    <div class="counts" id="counts"></div>
  </div>
</header>
<main>
  <section aria-label="Resume">
    <div class="head"><h2 id="r-title"></h2><div class="chips" id="r-chips"></div></div>
    <div class="scroll"><div class="text" id="r-text"></div></div>
  </section>
  <section aria-label="Posting">
    <div class="head">
      <h2 id="p-title"></h2><div class="chips" id="p-chips"></div>
      <div class="legend"><span class="k-required">requirement</span><span class="k-preferred">nice to have</span>
        <span><mark class="skill">skill in both</mark></span><span class="k-skip">boilerplate</span></div>
    </div>
    <div class="scroll"><div class="text" id="p-text"></div></div>
  </section>
</main>
<footer>
  <div class="review row" id="review">
    <strong id="pre-fit"></strong><span id="pre-reason"></span>
    <button class="big b-accept" id="accept">Accept<kbd>A / Enter</kbd></button>
  </div>
  <div class="row">
    <button class="big b-strong" data-fit="strong">Strong<kbd>S</kbd></button>
    <button class="big b-okay" data-fit="okay">Okay<kbd>O</kbd></button>
    <button class="big b-weak" data-fit="weak">Weak<kbd>W</kbd></button>
    <button class="big b-plain" id="skip">Skip<kbd>K</kbd></button>
    <button class="big b-plain" id="back">Back<kbd>B</kbd></button>
    <input class="note" type="text" id="note" maxlength="300" placeholder="Optional note (N to type, Esc to leave)">
  </div>
  <div class="terms" id="terms"></div>
  <div class="msg" id="msg"></div>
</footer>
<script>
const $ = (id) => document.getElementById(id);
const store = {
  get(k, d) { try { return localStorage.getItem("labels:" + k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("labels:" + k, v); } catch {} },
};
let mode = store.get("mode", "label"), part = store.get("part", "all"), persona = store.get("persona", "");
let items = [], index = 0, current = null;

function chip(text, cls) { const s = document.createElement("span"); s.className = "chip " + (cls || ""); s.textContent = text; return s; }

async function loadList(keepPlace) {
  const q = new URLSearchParams({ mode, part, persona });
  const res = await fetch("/api/pairs?" + q);
  const data = await res.json();
  items = data.items;
  const sel = $("persona");
  if (sel.options.length === 1) data.personas.forEach((p) => sel.add(new Option(p, p)));
  sel.value = persona;
  $("part").value = data.part; $("part").disabled = mode === "review";
  const labelled = items.filter((i) => i.fit).length;
  $("bar").style.width = (items.length ? (100 * labelled / items.length) : 0) + "%";
  const c = data.counts;
  $("counts").innerHTML = "";
  $("counts").append(`${labelled} of ${items.length} labelled · `);
  for (const [k, cls] of [["strong", "s"], ["okay", "o"], ["weak", "w"]]) {
    const b = document.createElement("b"); b.className = cls; b.textContent = `${k} ${c[k]}`;
    $("counts").append(b, " ");
  }
  if (!keepPlace) { const first = items.findIndex((i) => !i.fit); index = first === -1 ? 0 : first; }
  await show();
}

async function show() {
  const item = items[index];
  if (!item) { $("r-text").innerHTML = '<div class="done">Nothing to label here.</div>'; $("p-text").innerHTML = ""; return; }
  const res = await fetch(`/api/pair?resume=${encodeURIComponent(item.resume)}&job=${item.job}&mode=${mode}`);
  current = await res.json();
  const r = current.resume, p = current.posting, t = r.target || {};
  $("r-title").textContent = r.id + " — " + r.summary;
  $("r-chips").replaceChildren(
    ...[t.role, t.level, (t.location || "") + (t.remote_ok ? " or remote" : "")].filter(Boolean).map((x) => chip("wants " + x)),
    ...(r.field ? [chip("field: " + r.field)] : []),
    ...(r.holdout ? [chip("held out", "hold")] : []),
    ...(r.real ? [chip("real resume", "hold")] : []),
  );
  $("r-text").innerHTML = r.html;
  $("p-title").textContent = `${p.company} — ${p.title}`;
  $("p-chips").replaceChildren(chip(p.level || "?"), chip(p.role || "?"), chip(p.location || "?"),
    chip(`pair ${index + 1} of ${items.length} · chosen as ${current.source}`));
  $("p-text").innerHTML = p.html;
  document.querySelectorAll(".scroll").forEach((s) => (s.scrollTop = 0));
  const lab = current.label;
  $("note").value = lab ? lab.note || "" : "";
  document.querySelectorAll("[data-fit]").forEach((b) => b.classList.toggle("current", !!lab && lab.fit === b.dataset.fit));
  const pre = current.prelabel;
  $("review").classList.toggle("on", !!pre);
  if (pre) { $("pre-fit").textContent = "Pre-label: " + pre.fit.toUpperCase(); $("pre-reason").textContent = pre.reason; }
  const terms = $("terms"); terms.replaceChildren();
  if (current.candidates.length) {
    terms.append("Fair to suggest adding (a real requirement they plausibly have): ");
    current.candidates.forEach((term) => {
      const l = document.createElement("label"), box = document.createElement("input");
      box.type = "checkbox"; box.value = term; box.checked = !!(lab && lab.terms && lab.terms[term]);
      l.append(box, " " + term); terms.append(l);
    });
  }
  $("msg").textContent = lab ? `You said ${lab.fit}${lab.via ? " (" + lab.via + ")" : ""}.` : (mode === "label" ? "Blind: no pre-labels are shown." : "");
}

async function label(fit) {
  if (!current) return;
  const terms = {};
  document.querySelectorAll("#terms input").forEach((b) => (terms[b.value] = b.checked));
  const res = await fetch("/api/label", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume: current.resume.id, job: current.posting.id, fit, terms, note: $("note").value, mode }),
  });
  if (!res.ok) { $("msg").textContent = "Not saved: " + (await res.text()); return; }
  items[index].fit = fit;
  const next = items.findIndex((i, n) => n > index && !i.fit);
  index = next === -1 ? Math.min(index + 1, items.length - 1) : next;
  await loadList(true);
}

function setMode(m) {
  mode = m; store.set("mode", m);
  $("m-label").setAttribute("aria-pressed", m === "label"); $("m-review").setAttribute("aria-pressed", m === "review");
  loadList(false);
}
$("m-label").onclick = () => setMode("label");
$("m-review").onclick = () => setMode("review");
$("part").onchange = (e) => { part = e.target.value; store.set("part", part); loadList(false); };
$("persona").onchange = (e) => { persona = e.target.value; store.set("persona", persona); loadList(false); };
document.querySelectorAll("[data-fit]").forEach((b) => (b.onclick = () => label(b.dataset.fit)));
$("accept").onclick = () => current && current.prelabel && label(current.prelabel.fit);
$("skip").onclick = () => { index = Math.min(index + 1, items.length - 1); show(); };
$("back").onclick = () => { index = Math.max(index - 1, 0); show(); };
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" && e.target.type === "text") { if (e.key === "Escape") e.target.blur(); return; }
  if (e.target.tagName === "SELECT" || e.ctrlKey || e.metaKey || e.altKey) return;
  const k = e.key.toLowerCase();
  if (k === "s") label("strong"); else if (k === "o") label("okay"); else if (k === "w") label("weak");
  else if (k === "k") $("skip").click(); else if (k === "b") $("back").click();
  else if (k === "n") { e.preventDefault(); $("note").focus(); }
  else if ((k === "a" || k === "enter") && current && current.prelabel) { e.preventDefault(); label(current.prelabel.fit); }
  else return;
});
setMode(mode);
</script>
</body>
</html>
"""
