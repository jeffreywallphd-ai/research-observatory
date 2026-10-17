"use strict";
(() => {
  const content = document.getElementById("content");
  const navigation = document.getElementById("navigation");
  const notice = document.getElementById("notice");
  const filter = document.getElementById("filter");
  let model;
  let busy = false;
  let revision;
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = String(text);
    if (className) element.className = className;
    return element;
  };
  const value = (item) => typeof item === "string" ? item : JSON.stringify(item, null, 2);
  const link = (item) => {
    const anchor = node("a", `${item.alias || item.id} · ${item.title || item.name || item.goal || item.id}`);
    // Routes originate from canonical identity projection, never imported Markdown.
    if (!/^\/(?:waves\/W\d+|gates\/G\d+|enablers\/ECR-\d{4}|amendments\/W\d+\.A\d+|recoveries\/GRR-\d{4}|corrections\/W\d+\.C\d+\.T\d+|CAP-\d+\/(?:index|CAP-\d+\.S\d+(?:\.T\d+)?))\.html$/.test(item.route)) {
      throw new Error("Invalid projected route");
    }
    anchor.href = item.route;
    return anchor;
  };
  const badges = (item, parent) => {
    for (const [name, status] of [["State", item.status], ["Approval", item.approval?.status], ["Campaign", item.campaign?.status], ["Completion", item.completion?.status], ["Lifecycle", item.lifecycle?.status]]) {
      if (status) parent.append(node("span", `${name}: ${status}`, "badge"));
    }
  };
  const cards = (items, parent) => {
    const grid = node("div", undefined, "cards");
    for (const item of items) {
      const card = node("article", undefined, "card");
      const heading = node("h3"); heading.append(link(item)); card.append(heading);
      badges(item, card);
      if (item.goal || item.objective) card.append(node("p", item.goal || item.objective));
      grid.append(card);
    }
    parent.append(grid);
  };
  function renderNavigation() {
    navigation.replaceChildren();
    const query = filter.value.trim().toLocaleLowerCase();
    for (const kind of ["wave", "capability", "slice", "task", "gate", "amendment", "recovery", "correction"]) {
      const items = model.entities.filter(item => item.kind === kind && (!query || `${item.id} ${item.alias || ""} ${item.title || ""}`.toLocaleLowerCase().includes(query)));
      if (!items.length || (!query && ["slice", "task"].includes(kind))) continue;
      navigation.append(node("h2", `${kind[0].toUpperCase()}${kind.slice(1)}`));
      const list = node("ul");
      for (const item of items) { const row = node("li"); row.append(link(item)); list.append(row); }
      navigation.append(list);
    }
  }
  function renderPlan(plan, parent) {
    if (!plan) return;
    for (const decision of plan.decisions || []) {
      const box = node("details");
      box.dataset.key = decision.id;
      box.append(node("summary", `${decision.id} · ${decision.title} · ${decision.status || "pending"}`));
      const fields = node("dl");
      for (const name of ["binding_waves", "candidates", "recommendation", "recommendation_basis", "selected_option", "rationale", "required_adr"]) {
        if (decision[name] !== undefined) fields.append(node("dt", name.replaceAll("_", " ")), node("dd", value(decision[name])));
      }
      box.append(fields); parent.append(box);
    }
    const full = node("details");
    full.dataset.key = plan.path;
    full.append(node("summary", `Canonical plan · ${plan.path}`));
    full.append(node("p", `SHA-256 ${plan.sha256}`, "muted"));
    full.append(node("pre", plan.markdown)); parent.append(full);
  }
  function render() {
    const active = document.activeElement;
    const focusedLink = active?.tagName === "A" ? active.getAttribute("href") : undefined;
    const focusedDisclosure = active?.tagName === "SUMMARY" ? active.parentElement.dataset.key : undefined;
    const wasInReview = content.contains(active) || navigation.contains(active);
    const openDisclosures = new Set([...content.querySelectorAll("details[data-key][open]")].map(item => item.dataset.key));
    renderNavigation();
    const route = window.location.pathname;
    const selected = model.entities.find(item => item.route === route);
    content.replaceChildren();
    if (!selected) {
      const kind = route === "/enablers/index.html" ? "amendment" : route === "/recoveries/index.html" ? "recovery" : "wave";
      content.append(node("h1", kind === "amendment" ? "Workflow amendments" : kind === "recovery" ? "Recovery records" : "Planning review center"));
      cards(model.entities.filter(item => item.kind === kind), content);
    } else {
      document.title = `${selected.id} · Research Observatory planning`;
      content.append(node("p", `${selected.kind} · ${selected.id}`, "muted"), node("h1", selected.title || selected.name || selected.goal || selected.id));
      badges(selected, content);
      const fields = node("dl");
      for (const name of ["goal", "objective", "outcome", "wave", "after_wave", "unlocks_waves", "criteria", "capability_id", "slice_id", "depends_on", "dependencies", "acceptance_criteria", "verification_profiles", "verification_commands", "approval"]) {
        if (selected[name] !== undefined) fields.append(node("dt", name.replaceAll("_", " ")), node("dd", value(selected[name])));
      }
      content.append(fields);
      const related = model.entities.filter(item => {
        if (selected.kind === "wave") return item.wave === selected.id && ["slice", "gate", "correction"].includes(item.kind);
        if (selected.kind === "capability") return item.capability_id === selected.id && item.kind === "slice";
        if (selected.kind === "slice") return item.slice_id === selected.id;
        return false;
      });
      if (related.length) { content.append(node("h2", "Related work and gates")); cards(related, content); }
      renderPlan(model.plan, content);
      for (const plan of model.plans || []) renderPlan(plan, content);
    }
    const sources = node("details"); sources.append(node("summary", "Current source fingerprints"));
    sources.dataset.key = "source-fingerprints";
    sources.append(node("pre", value(model.sources))); content.append(sources);
    const disclosures = [...content.querySelectorAll("details[data-key]")];
    for (const disclosure of disclosures) disclosure.open = openDisclosures.has(disclosure.dataset.key);
    if (wasInReview) {
      const restored = focusedLink
        ? [...document.querySelectorAll("a[href]")].find(item => item.getAttribute("href") === focusedLink)
        : disclosures.find(item => item.dataset.key === focusedDisclosure)?.querySelector("summary");
      (restored || content).focus({preventScroll: true});
    }
  }
  async function refresh() {
    if (busy) return;
    busy = true;
    try {
      let selected = model?.entities.find(item => item.route === window.location.pathname);
      if (!model) {
        const response = await fetch("/api/review", {cache: "no-store", credentials: "omit"});
        if (!response.ok) throw new Error("Planning sources unavailable");
        model = await response.json();
        selected = model.entities.find(item => item.route === window.location.pathname);
      }
      const response = await fetch(selected ? `/api/review/${encodeURIComponent(selected.id)}` : "/api/review", {cache: "no-store", credentials: "omit"});
      if (!response.ok) {
        const problem = await response.json();
        throw new Error(problem.error === "server.code-changed-restart-required"
          ? "Review implementation changed. Restart the review server."
          : "Planning sources changed or are unavailable; correct the canonical sources and refresh.");
      }
      const current = await response.json();
      model = current;
      if (revision !== current.fingerprint) {
        render(); revision = current.fingerprint;
        notice.textContent = `Live sources checked ${new Date().toLocaleTimeString()}. ${current.authority}`;
      }
    } catch (error) {
      revision = undefined;
      model = undefined;
      content.replaceChildren(node("h1", "Current planning could not be displayed"));
      navigation.replaceChildren();
      notice.textContent = error instanceof Error ? error.message : "Refresh failed";
    } finally { busy = false; }
  }
  filter.addEventListener("input", () => { if (model) renderNavigation(); });
  document.getElementById("refresh").addEventListener("click", refresh);
  window.setInterval(() => { if (!document.hidden) refresh(); }, 15000);
  refresh();
})();
