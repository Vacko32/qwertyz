const state = {
  annotatorId: null,
  rows: [],
  responses: {},
  currentIndex: 0,
  outputFile: "",
  saveTimer: null,
};

const els = {
  annotatorBadge: document.getElementById("annotatorBadge"),
  saveState: document.getElementById("saveState"),
  progressText: document.getElementById("progressText"),
  progressPercent: document.getElementById("progressPercent"),
  progressBar: document.getElementById("progressBar"),
  previousButton: document.getElementById("previousButton"),
  nextButton: document.getElementById("nextButton"),
  nextUnansweredButton: document.getElementById("nextUnansweredButton"),
  rowSelect: document.getElementById("rowSelect"),
  donePanel: document.getElementById("donePanel"),
  outputPath: document.getElementById("outputPath"),
  sampleMeta: document.getElementById("sampleMeta"),
  sampleTitle: document.getElementById("sampleTitle"),
  answeredBadge: document.getElementById("answeredBadge"),
  sourceText: document.getElementById("sourceText"),
  responseA: document.getElementById("responseA"),
  responseB: document.getElementById("responseB"),
  ratingGrid: document.getElementById("ratingGrid"),
  notesInput: document.getElementById("notesInput"),
};

const ratingLabels = {
  1: ["Strong A", "Response A is much better"],
  2: ["Slight A", "Response A is a little better"],
  3: ["Tie", "No meaningful preference"],
  4: ["Slight B", "Response B is a little better"],
  5: ["Strong B", "Response B is much better"],
};

function storageKey() {
  return `preference-annotation-current-${state.annotatorId}`;
}

function currentRow() {
  return state.rows[state.currentIndex];
}

function answeredCount() {
  return Object.values(state.responses).filter((response) => response.preference_score_1_to_5).length;
}

function setSaveState(message, kind = "muted") {
  els.saveState.textContent = message;
  els.saveState.dataset.kind = kind;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderMarkdown(target, text) {
  const value = text || "";
  if (!window.marked || !window.DOMPurify) {
    target.textContent = value;
    return;
  }

  const renderer = new marked.Renderer();
  renderer.html = (token) => escapeHtml(token.raw || token.text || "");

  marked.setOptions({
    breaks: true,
    gfm: true,
    mangle: false,
    headerIds: false,
    renderer,
  });
  target.innerHTML = DOMPurify.sanitize(marked.parse(value));

  if (window.hljs) {
    target.querySelectorAll("pre code").forEach((block) => hljs.highlightElement(block));
  }
  if (window.renderMathInElement) {
    renderMathInElement(target, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "\\(", right: "\\)", display: false },
        { left: "$", right: "$", display: false },
      ],
      throwOnError: false,
    });
  }
}

function buildRatingButtons() {
  els.ratingGrid.innerHTML = "";
  Object.entries(ratingLabels).forEach(([score, [title, subtitle]]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "rating-option";
    button.dataset.score = score;
    button.innerHTML = `<strong>${score}</strong><span>${title}</span><span>${subtitle}</span>`;
    button.addEventListener("click", () => setRating(Number(score)));
    els.ratingGrid.appendChild(button);
  });
}

function buildRowSelect() {
  els.rowSelect.innerHTML = "";
  state.rows.forEach((row, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = `${row.assignment_index}. ${row.sample_id}`;
    els.rowSelect.appendChild(option);
  });
}

function renderProgress() {
  const done = answeredCount();
  const total = state.rows.length;
  const percent = total ? Math.round((done / total) * 100) : 0;
  els.progressText.textContent = `${done} / ${total}`;
  els.progressPercent.textContent = `${percent}%`;
  els.progressBar.style.width = `${percent}%`;
  els.donePanel.hidden = done !== total || total === 0;
  els.outputPath.textContent = state.outputFile;
}

function renderRow() {
  const row = currentRow();
  if (!row) {
    return;
  }

  localStorage.setItem(storageKey(), String(state.currentIndex));
  els.rowSelect.value = String(state.currentIndex);
  els.previousButton.disabled = state.currentIndex === 0;
  els.nextButton.disabled = state.currentIndex === state.rows.length - 1;
  els.sampleMeta.textContent = `Assigned row ${row.assignment_index} of ${state.rows.length} · dataset row ${row.row_number} · ${row.source_type}`;
  els.sampleTitle.textContent = row.sample_id;

  renderMarkdown(els.sourceText, row.source_text);
  renderMarkdown(els.responseA, row.response_a);
  renderMarkdown(els.responseB, row.response_b);

  const response = state.responses[row.sample_id] || {};
  els.notesInput.value = response.notes || "";
  updateRatingSelection(response.preference_score_1_to_5);
  renderProgress();
}

function updateRatingSelection(score) {
  els.ratingGrid.querySelectorAll(".rating-option").forEach((button) => {
    button.classList.toggle("is-selected", Number(button.dataset.score) === Number(score));
  });
  const answered = Boolean(score);
  els.answeredBadge.textContent = answered ? `Saved: ${score}` : "Unanswered";
  els.answeredBadge.classList.toggle("is-answered", answered);
}

async function saveCurrentResponse() {
  const row = currentRow();
  const existing = state.responses[row.sample_id];
  if (!existing || !existing.preference_score_1_to_5) {
    setSaveState("Choose 1-5 to save");
    return;
  }

  const payload = {
    sample_id: row.sample_id,
    preference_score_1_to_5: existing.preference_score_1_to_5,
    notes: els.notesInput.value,
  };
  state.responses[row.sample_id] = { ...existing, notes: payload.notes };

  setSaveState("Saving...");
  const response = await fetch("/api/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.error || "Save failed");
  }
  setSaveState(`Saved ${body.saved}/${body.assigned}`, "ok");
  renderProgress();
}

function setRating(score) {
  const row = currentRow();
  const previous = state.responses[row.sample_id] || {};
  state.responses[row.sample_id] = {
    ...previous,
    sample_id: row.sample_id,
    preference_score_1_to_5: score,
    notes: els.notesInput.value,
  };
  updateRatingSelection(score);
  saveCurrentResponse().catch((error) => setSaveState(error.message, "error"));
}

function debouncedNotesSave() {
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(() => {
    const row = currentRow();
    const response = state.responses[row.sample_id];
    if (!response || !response.preference_score_1_to_5) {
      return;
    }
    saveCurrentResponse().catch((error) => setSaveState(error.message, "error"));
  }, 500);
}

function goTo(index) {
  state.currentIndex = Math.max(0, Math.min(index, state.rows.length - 1));
  renderRow();
}

function goToNextUnanswered() {
  const start = state.currentIndex + 1;
  const ordered = [...state.rows.slice(start), ...state.rows.slice(0, start)];
  const next = ordered.find((row) => !state.responses[row.sample_id]?.preference_score_1_to_5);
  if (!next) {
    return;
  }
  goTo(state.rows.findIndex((row) => row.sample_id === next.sample_id));
}

async function loadState() {
  const response = await fetch("/api/state", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Could not load annotation state");
  }
  const data = await response.json();
  state.annotatorId = data.annotator_id;
  state.rows = data.rows;
  state.responses = data.responses || {};
  state.outputFile = data.output_file;

  const savedIndex = Number(localStorage.getItem(storageKey()));
  state.currentIndex = Number.isInteger(savedIndex) ? savedIndex : 0;
  state.currentIndex = Math.max(0, Math.min(state.currentIndex, state.rows.length - 1));

  els.annotatorBadge.textContent = `Annotator ${state.annotatorId}`;
  buildRatingButtons();
  buildRowSelect();
  renderRow();
  setSaveState("Ready");
}

els.previousButton.addEventListener("click", () => goTo(state.currentIndex - 1));
els.nextButton.addEventListener("click", () => goTo(state.currentIndex + 1));
els.nextUnansweredButton.addEventListener("click", goToNextUnanswered);
els.rowSelect.addEventListener("change", (event) => goTo(Number(event.target.value)));
els.notesInput.addEventListener("input", debouncedNotesSave);

document.addEventListener("keydown", (event) => {
  if (event.target === els.notesInput) {
    return;
  }
  if (/^[1-5]$/.test(event.key)) {
    setRating(Number(event.key));
  } else if (event.key === "ArrowLeft") {
    goTo(state.currentIndex - 1);
  } else if (event.key === "ArrowRight") {
    goTo(state.currentIndex + 1);
  }
});

loadState().catch((error) => {
  setSaveState(error.message, "error");
  els.sampleTitle.textContent = "Could not load app";
});
