
(() => {
  const root = document.documentElement;
  const themeKey = "ro-planning-review-theme";
  const otherSentinel = "__OTHER__";
  const savedTheme = localStorage.getItem(themeKey);
  if (savedTheme === "dark" || savedTheme === "light") root.dataset.theme = savedTheme;
  else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) root.dataset.theme = "dark";

  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
      localStorage.setItem(themeKey, root.dataset.theme);
    });
  });

  const capabilityId = document.body.dataset.capabilityId;
  if (!capabilityId || document.body.dataset.pageType !== "capability") return;

  const cards = Array.from(document.querySelectorAll("[data-decision-id]"));
  const stateKey = `ro-planning-review:${capabilityId}`;
  const reviewer = document.querySelector("[data-reviewer-name]");
  const notes = document.querySelector("[data-review-notes]");
  const approvalIntent = document.querySelector("[data-approval-intent]");
  const selectedCount = document.querySelector("[data-selected-count]");
  const message = document.querySelector("[data-feedback-message]");

  const toggleOther = (card) => {
    const checked = card.querySelector("[data-decision-option]:checked");
    const field = card.querySelector("[data-other-option-field]");
    const input = card.querySelector("[data-decision-other]");
    const visible = Boolean(checked && checked.value === otherSentinel);
    if (field) field.classList.toggle("is-visible", visible);
    if (input) {
      input.required = visible;
      input.setAttribute("aria-hidden", visible ? "false" : "true");
    }
  };

  const readState = () => {
    try { return JSON.parse(localStorage.getItem(stateKey) || "{}"); }
    catch (_) { return {}; }
  };
  const state = readState();
  if (reviewer) reviewer.value = state.reviewer || "";
  if (notes) notes.value = state.notes || "";
  if (approvalIntent) approvalIntent.checked = Boolean(state.approval_intent);

  cards.forEach((card) => {
    const id = card.dataset.decisionId;
    const saved = state.decisions && state.decisions[id];
    if (saved) {
      const choice = Array.from(card.querySelectorAll("[data-decision-option]")).find((input) => input.value === saved.selected_option);
      if (choice) choice.checked = true;
      const other = card.querySelector("[data-decision-other]");
      if (other) other.value = saved.other_option || "";
      const rationale = card.querySelector("[data-decision-rationale]");
      if (rationale) rationale.value = saved.rationale || "";
    }
    toggleOther(card);
  });

  const collect = () => {
    const decisions = {};
    cards.forEach((card) => {
      const id = card.dataset.decisionId;
      const checked = card.querySelector("[data-decision-option]:checked");
      const other = card.querySelector("[data-decision-other]");
      const rationale = card.querySelector("[data-decision-rationale]");
      decisions[id] = {
        selected_option: checked ? checked.value : null,
        other_option: other ? other.value.trim() : "",
        recommendation: card.dataset.recommendation,
        rationale: rationale ? rationale.value.trim() : ""
      };
    });
    return {
      reviewer: reviewer ? reviewer.value.trim() : "",
      notes: notes ? notes.value.trim() : "",
      approval_intent: approvalIntent ? approvalIntent.checked : false,
      decisions
    };
  };

  const save = () => {
    cards.forEach(toggleOther);
    const value = collect();
    localStorage.setItem(stateKey, JSON.stringify(value));
    const count = Object.values(value.decisions).filter((item) => item.selected_option).length;
    if (selectedCount) selectedCount.textContent = String(count);
    return value;
  };

  document.addEventListener("input", (event) => {
    if (event.target.closest("[data-review-toolbar]") || event.target.closest("[data-decision-id]")) save();
  });
  document.addEventListener("change", (event) => {
    if (event.target.closest("[data-review-toolbar]") || event.target.closest("[data-decision-id]")) save();
  });

  const acceptButton = document.querySelector("[data-accept-recommendations]");
  if (acceptButton) acceptButton.addEventListener("click", () => {
    cards.forEach((card) => {
      const recommended = card.dataset.recommendation;
      const option = Array.from(card.querySelectorAll("[data-decision-option]")).find((input) => input.value === recommended);
      if (option) option.checked = true;
      const other = card.querySelector("[data-decision-other]");
      if (other) other.value = "";
      toggleOther(card);
    });
    save();
    if (message) message.textContent = "Recommended defaults restored. Review any intended overrides before capability approval.";
  });

  const clearButton = document.querySelector("[data-clear-decisions]");
  if (clearButton) clearButton.addEventListener("click", () => {
    cards.forEach((card) => {
      card.querySelectorAll("[data-decision-option]").forEach((input) => { input.checked = false; });
      const other = card.querySelector("[data-decision-other]");
      if (other) other.value = "";
      const rationale = card.querySelector("[data-decision-rationale]");
      if (rationale) rationale.value = "";
      toggleOther(card);
    });
    save();
    if (message) message.textContent = "Decision selections and draft overrides cleared.";
  });

  const exportButton = document.querySelector("[data-export-feedback]");
  if (exportButton) exportButton.addEventListener("click", () => {
    const value = save();
    const missing = Object.entries(value.decisions).filter(([, item]) => !item.selected_option).map(([id]) => id);
    const missingOther = Object.entries(value.decisions)
      .filter(([, item]) => item.selected_option === otherSentinel && !item.other_option)
      .map(([id]) => id);
    const alternativeWithoutRationale = Object.entries(value.decisions)
      .filter(([, item]) => item.selected_option && item.selected_option !== item.recommendation && !item.rationale)
      .map(([id]) => id);
    if (missing.length) {
      if (message) message.textContent = `Select an option for: ${missing.join(", ")}`;
      return;
    }
    if (missingOther.length) {
      if (message) message.textContent = `Enter a brief Other description for: ${missingOther.join(", ")}`;
      return;
    }
    if (alternativeWithoutRationale.length) {
      if (message) message.textContent = `Add detailed rationale for non-recommended selections: ${alternativeWithoutRationale.join(", ")}`;
      return;
    }
    const planHash = cards[0] ? cards[0].dataset.planHash : "";
    const payload = {
      schema_version: "1.1",
      document_type: "capability-decision-feedback",
      capability_id: capabilityId,
      capability_plan_sha256: planHash,
      reviewer: value.reviewer || null,
      reviewed_at: new Date().toISOString(),
      requested_action: value.approval_intent ? "approve-capability-and-slices" : "record-feedback",
      capability_notes: value.notes,
      decisions: Object.entries(value.decisions).map(([id, item]) => ({
        id,
        selected_option: item.selected_option,
        other_option: item.selected_option === otherSentinel ? item.other_option : null,
        accepted_recommendation: item.selected_option === item.recommendation,
        rationale: item.rationale || null
      }))
    };
    const blob = new Blob([JSON.stringify(payload, null, 2) + "\n"], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${capabilityId}-decision-feedback.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    if (message) message.textContent = `Downloaded ${anchor.download}. Apply it with planctl from the repository root.`;
  });

  save();
})();
