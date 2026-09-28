// Aira R&D dashboard — talks only to the local server (scripts/rnd/dashboard.py).
// Report text can contain words derived from customer messages: every markdown render goes
// through DOMPurify, and everything else is set with textContent, never innerHTML.
const TOKEN = new URLSearchParams(location.hash.slice(1)).get("t") || "";
const $ = (id) => document.getElementById(id);

function el(tag, props = {}, ...kids) {
  const node = Object.assign(document.createElement(tag), props);
  for (const kid of kids) if (kid != null) node.append(kid);
  return node;
}

function md(text) {
  const box = el("div", { className: "md" });
  box.innerHTML = DOMPurify.sanitize(marked.parse(text || ""));
  return box;
}

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("on");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("on"), 4500);
}

async function api(path, body) {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: { "X-Token": TOKEN, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function act(label, path, body) {
  try {
    const out = await api(path, body);
    toast(`${label}: done${out.output ? "\n" + out.output.slice(-300) : ""}`);
    await load();
  } catch (e) {
    toast(`${label} failed: ${e.message}`);
  }
}

function pill(text, kind) { return el("span", { className: `pill ${kind}`, textContent: text }); }
function btn(text, onclick, cls = "") { return el("button", { className: `btn ${cls}`, textContent: text, onclick }); }
function empty(text) { return el("div", { className: "card empty", textContent: text }); }

function renderStrip(s) {
  const strip = $("strip");
  strip.replaceChildren(
    el("span", { className: `chip ${s.alarm ? "ok" : "bad"}`, textContent: s.alarm ? "Alarm on · 1:30 AM" : "Alarm off" }),
    el("span", { className: `chip ${s.running ? "run" : "ok"}`, textContent: s.running ? "A run is in progress" : "Idle" }),
    el("span", { className: "chip", textContent: `${s.unpushed.length} commit(s) waiting to push` }),
  );
}

async function renderTonight(st) {
  const box = $("tonight");
  if (!st.night) return box.replaceChildren(empty("No night report yet. The first one arrives after 1:30 AM."));
  const approvals = el("div", { className: "card" },
    el("h3", { textContent: "Approve fixes" }),
    el("div", { className: "meta", textContent: "Switch on what you want built. The builder picks it up at the next run, on its own branch." }));
  for (const item of st.night_items) {
    const input = el("input", { type: "checkbox", checked: item.approved, disabled: item.built });
    input.setAttribute("aria-label", `Approve: ${item.title}`);
    input.onchange = () => act(input.checked ? "Approved" : "Unapproved", "/api/approve",
      { report: st.night.name, n: item.n, on: input.checked });
    approvals.append(el("div", { className: "approve" },
      el("span", { className: "t", textContent: `${item.n}. ${item.title}` }),
      item.built ? pill("picked up", "info") : null,
      el("label", { className: "switch" }, input, el("span"))));
  }
  const report = await api(`/api/report?name=${encodeURIComponent(st.night.name)}`);
  box.replaceChildren(approvals, el("div", { className: "card" },
    el("div", { className: "meta", textContent: st.night.name }), md(report.markdown)));
}

function renderBuilds(st) {
  const box = $("builds");
  $("c-builds").textContent = st.builds.filter((b) => !b.merged).length;
  if (!st.builds.length) return box.replaceChildren(empty("No builds yet. Approve an item under Tonight."));
  box.replaceChildren(...st.builds.map((b) => {
    const ok = /^PASS/.test(b.verify);
    const diff = el("details", {}, el("summary", { textContent: "Code changes" }));
    diff.ontoggle = async () => {
      if (!diff.open || diff.dataset.loaded) return;
      const d = await api(`/api/diff?branch=${encodeURIComponent(b.branch)}`);
      diff.append(el("pre", { textContent: d.diff || "(no changes)" }));
      diff.dataset.loaded = "1";
    };
    return el("div", { className: "card" },
      el("h3", { textContent: b.branch.replace(/^rnd\//, "") }),
      el("div", { className: "row" },
        pill(b.status, /BUILT/.test(b.status) ? "ok" : /GAVE_UP/.test(b.status) ? "bad" : "mid"),
        pill(`verify: ${b.verify}`, ok ? "ok" : b.verify === "not run" ? "mid" : "bad"),
        b.merged ? pill("merged", "info") : null,
        el("span", { className: "meta", textContent: `${b.sha} · ${b.when}` })),
      b.diffstat ? el("pre", { textContent: b.diffstat }) : null,
      el("details", {}, el("summary", { textContent: "What the builder says" }), md(b.summary || "_No summary written._")),
      diff,
      el("div", { className: "row" },
        b.merged ? null : btn("Merge into main", () => confirm(`Merge ${b.branch} into your local main?\nNothing is pushed.`) && act("Merge", "/api/merge", { branch: b.branch }), "primary"),
        btn(b.merged ? "Delete branch" : "Drop", () => confirm(`Delete ${b.branch} and its worktree?`) && act("Drop", "/api/drop", { branch: b.branch }), "danger")));
  }));
}

async function renderStrategy(st) {
  const box = $("strategy");
  const latest = st.reports.find((r) => r.kind === "strategy");
  if (!latest) return box.replaceChildren(empty("No strategy report yet. It runs Sunday nights, or press Run strategy under Status."));
  const r = await api(`/api/report?name=${encodeURIComponent(latest.name)}`);
  box.replaceChildren(el("div", { className: "card" }, el("div", { className: "meta", textContent: latest.name }), md(r.markdown)));
}

function renderStatus(st) {
  const s = st.status;
  const ship = el("div", { className: "card" },
    el("h3", { textContent: "Ship to customers" }),
    el("div", { className: "meta", textContent: s.unpushed.length ? "These commits are on your Mac but not on GitHub yet:" : "Nothing waiting to push." }),
    s.unpushed.length ? el("pre", { textContent: s.unpushed.join("\n") }) : null,
    el("div", { className: "row" }, btn("Push to GitHub…", pushFlow, "primary")));
  const runs = el("div", { className: "card" },
    el("h3", { textContent: "Run now" }),
    el("div", { className: "meta", textContent: "Same as the 1:30 AM run, started now. Uses your Claude plan." }),
    el("div", { className: "row" },
      ...["build", "night", "strategy"].map((k) => btn(`Run ${k}`, () => act(`Started ${k}`, "/api/run", { kind: k }))).map((b) => { b.disabled = s.running; return b; })));
  const logs = el("div", { className: "card" }, el("h3", { textContent: "Recent logs" }),
    ...s.logs.map((l) => el("details", {}, el("summary", { textContent: l.name }), el("pre", { textContent: l.tail.join("\n") }))));
  $("status").replaceChildren(ship, runs, logs);
}

async function pushFlow() {
  try {
    const p = await api("/api/push-preview");
    if (p.behind) return toast(`GitHub has ${p.behind} newer commit(s) from a teammate. Pull and re-run the tests first.`);
    if (!p.commits.length) return toast("Nothing to push.");
    const ok = confirm(`Push ${p.commits.length} commit(s) to GitHub?\n\n${p.commits.join("\n")}\n\nThis DEPLOYS the backend to customers.`);
    if (!ok) return;
    const typed = prompt("Type PUSH to confirm");
    if (typed !== "PUSH") return toast("Push cancelled.");
    await act("Push", "/api/push", { confirm: typed });
  } catch (e) {
    toast(`Push failed: ${e.message}`);
  }
}

async function load() {
  try {
    const st = await api("/api/state");
    renderStrip(st.status);
    renderBuilds(st);
    renderStatus(st);
    await renderTonight(st);
    await renderStrategy(st);
  } catch (e) {
    toast(e.message);
  }
}

for (const tab of document.querySelectorAll("#tabs button")) {
  tab.onclick = () => {
    for (const t of document.querySelectorAll("#tabs button")) t.setAttribute("aria-selected", String(t === tab));
    for (const s of document.querySelectorAll("section")) s.classList.toggle("on", s.id === tab.dataset.tab);
  };
}
load();
setInterval(load, 60_000);
