// The manual demonstration: pin a revision, confirm typed steps, show the server's result for it.
// All decisions are made on the server. Ink is never sent from here, and sync carries on unchanged.
// Text only reaches the page through textContent, so typed steps cannot become markup.

const el = (id) => document.getElementById(id);

const SUMMARIES = {
  CORRECT: "Correct.",
  INCORRECT: "Something needs another look.",
  INCOMPLETE: "Not finished yet.",
  UNSUPPORTED: "Not marked: this check cannot read part of this. It needs a person to look at it.",
  UNDETERMINED: "Not marked yet: please check what you typed. It needs a person if it stays unclear.",
};
const STEP_LABELS = {
  CORRECT: "Same value as what comes before it",
  INCORRECT: "Needs another look",
  INCOMPLETE: "Not finished",
  UNSUPPORTED: "Not read",
  UNDETERMINED: "Not checked",
};

function newKey() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

class VerifyDemo {
  constructor(app) {
    this.app = app;
    this.exercises = new Map();
    this.pin = null; // The pinned revision that the typed steps belong to.
    this.result = null; // The result on show.
    this.attempt = null; // { fingerprint, key }: a retry of the same work reuses the same key.
    this.busy = false;
  }

  async start() {
    el("verify").addEventListener("click", () => this.verify());
    el("verify-confirm").addEventListener("click", () => this.confirm());
    el("verify-retry").addEventListener("click", () => this.confirm());
    el("verify-explain").addEventListener("click", () => this.explain());
    el("verify-exercise").addEventListener("change", () => this.exerciseChanged());
    this.shownPageId = this.app.activePage.id;
    document.addEventListener("notebook:changed", () => this.pageChanged());
    await this.loadExercises();
    el("verify").disabled = false;
    await this.loadHistory();
  }

  get pageUrl() {
    const page = this.app.activePage.id;
    return `/api/grading/v1/notebooks/${this.app.notebookId}/pages/${page}/verifications/`;
  }

  status(state, text) {
    const status = el("verify-status");
    status.dataset.state = state;
    status.textContent = text;
  }

  async loadExercises() {
    const response = await fetch("/api/grading/v1/exercises/");
    const { exercises } = await response.json();
    const select = el("verify-exercise");
    for (const exercise of exercises) {
      this.exercises.set(exercise.exercise_id, exercise);
      const option = document.createElement("option");
      option.value = exercise.exercise_id;
      option.textContent = exercise.title;
      select.append(option);
    }
    this.showStatement();
  }

  showStatement() {
    el("verify-statement").textContent = this.selected.statement;
  }

  get selected() {
    return this.exercises.get(el("verify-exercise").value);
  }

  exerciseChanged() {
    this.showStatement();
    this.result = null;
    this.attempt = null;
    el("verify-result").hidden = true;
    el("verify-result").dataset.status = "none";
  }

  // Step 4 of the flow: finish saving and fix the revision. Nothing is graded here.
  async verify() {
    if (this.busy) return;
    this.setBusy(true);
    this.status("working", "Saving your page…");
    try {
      const pin = await this.app.pinCurrentPage();
      if (pin.status === "empty") {
        this.status("error", "Write your work on the page first.");
      } else if (pin.status === "not-synced") {
        this.status("error", "Your page is not saved to the server yet, so it cannot be checked. Your writing is kept here.");
      } else if (pin.status === "rejected") {
        this.status("error", `The page could not be pinned (${pin.code}). Your writing is kept here.`);
      } else {
        if (this.pin?.revision !== pin.revision) {
          // New ink, so new work. The same revision again keeps its result and its retry key.
          this.attempt = null;
          this.result = null;
          el("verify-result").hidden = true;
          el("verify-result").dataset.status = "none";
        }
        this.pin = pin;
        el("verify-work").hidden = false;
        el("verify-retry").hidden = true;
        this.status("pinned", `Revision ${pin.revision} is saved. Now type your steps below.`);
        el("verify-steps").focus();
      }
    } catch (error) {
      console.warn("pin failed", error);
      this.status("error", "Could not reach the server. Your writing is kept here.");
    } finally {
      this.setBusy(false);
    }
  }

  setBusy(busy) {
    this.busy = busy;
    el("verify").disabled = busy;
    el("verify-confirm").disabled = busy;
    el("verify-retry").disabled = busy;
  }

  typedSteps() {
    return el("verify-steps")
      .value.split("\n")
      .map((line) => line.trim())
      .filter((line) => line !== "");
  }

  // Steps 5 to 7. The same work keeps the same key, so a retry can never make a second record.
  async confirm() {
    if (this.busy || !this.pin) return;
    const steps = this.typedSteps();
    if (steps.length === 0) {
      this.status("error", "Type at least one step.");
      return;
    }
    const exercise = this.selected;
    const earlier = this.result;
    const corrects =
      earlier && earlier.revision === this.pin.revision && earlier.exercise_id === exercise.exercise_id
        ? earlier.id
        : null;
    const fingerprint = JSON.stringify([this.pin.revision, exercise.exercise_id, steps]);
    if (this.attempt?.fingerprint !== fingerprint) {
      this.attempt = { fingerprint, key: newKey(), corrects };
    }
    this.setBusy(true);
    this.status("working", "Checking…");
    try {
      const response = await fetch(this.pageUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": this.app.csrfToken },
        body: JSON.stringify({
          idempotency_key: this.attempt.key,
          exercise_id: exercise.exercise_id,
          exercise_version: exercise.exercise_version,
          revision: this.pin.revision,
          visible_hash: this.pin.visibleHash,
          steps,
          corrects: this.attempt.corrects,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        this.status("error", `This check was refused (${body.code}). ${body.detail}`);
        return;
      }
      el("verify-retry").hidden = true;
      this.showResult(body);
      this.status("done", `Result for revision ${body.revision}.`);
      await this.loadHistory();
    } catch (error) {
      console.warn("check failed", error);
      el("verify-retry").hidden = false;
      this.status("error", "The answer did not arrive. Press Try again: it will not count twice.");
    } finally {
      this.setBusy(false);
    }
  }

  showResult(result) {
    this.result = result;
    const box = el("verify-result");
    box.hidden = false;
    box.dataset.status = result.mathematical_status;
    box.dataset.compliance = result.task_compliance;
    let summary = SUMMARIES[result.mathematical_status];
    if (result.mathematical_status === "CORRECT" && result.task_compliance === "NON_COMPLIANT") {
      summary = "The value is right, but the question asks for something more.";
    }
    el("verify-summary").textContent = summary;
    el("verify-score").textContent =
      result.score === null ? "No mark given." : `Mark: ${result.score} out of ${result.max_score}.`;
    el("verify-checked").textContent = result.feedback.checked;
    el("verify-problem").textContent = result.feedback.problem ?? "";
    el("verify-hint").textContent = result.feedback.hint ? `Hint: ${result.feedback.hint}` : "";
    el("verify-explain").hidden = result.mathematical_status === "CORRECT" && result.task_compliance === "COMPLIANT";
    const explanation = el("verify-explanation");
    explanation.hidden = true;
    explanation.textContent = "";
    const list = el("verify-step-list");
    list.replaceChildren();
    for (const step of result.steps) {
      const item = document.createElement("li");
      item.dataset.status = step.mathematical_status;
      const rounded = step.feedback.code === "STEP_ROUNDED";
      const label = rounded ? "Rounded from what comes before it" : STEP_LABELS[step.mathematical_status];
      item.textContent = `${step.text}: ${label}`;
      list.append(item);
    }
    this.pageChanged();
  }

  // A result belongs to one revision, and is never shown as a verdict on anything newer.
  pageChanged() {
    const page = this.app.activePage;
    if (page.id !== this.shownPageId) {
      // Typed steps and results belong to the page they were pinned on, so they leave with it.
      this.shownPageId = page.id;
      this.pin = null;
      this.result = null;
      this.attempt = null;
      el("verify-work").hidden = true;
      el("verify-result").hidden = true;
      el("verify-result").dataset.status = "none";
      this.status("idle", "");
      this.loadHistory();
      return;
    }
    const result = this.result;
    if (!result) return;
    const current = page.state.opIndex.size === result.seq;
    const stale = el("verify-stale");
    stale.hidden = current;
    stale.textContent = current
      ? ""
      : `This result is for revision ${result.revision}. The page has changed since.`;
    el("verify-result").dataset.current = String(Boolean(current));
  }

  async explain() {
    if (!this.result) return;
    const box = el("verify-explanation");
    try {
      const response = await fetch(`${this.pageUrl}${this.result.id}/explanation/`);
      const body = await response.json();
      box.textContent = response.ok ? body.explanation : "The explanation is not available.";
    } catch (error) {
      console.warn("explanation failed", error);
      box.textContent = "Could not reach the server.";
    }
    box.hidden = false;
  }

  async loadHistory() {
    const list = el("verify-history");
    try {
      const response = await fetch(this.pageUrl);
      if (!response.ok) {
        list.replaceChildren();
        return;
      }
      const { verifications } = await response.json();
      list.replaceChildren(
        ...verifications.map((row) => {
          const item = document.createElement("li");
          const corrected = row.corrected_by ? ", later corrected" : "";
          const mark = row.score === null ? "no mark" : `${row.score}/${row.max_score}`;
          item.textContent = `Revision ${row.revision}, ${row.exercise_id}: ${row.mathematical_status}, ${mark}${corrected}`;
          return item;
        }),
      );
    } catch (error) {
      console.warn("history failed", error);
    }
  }
}

function startWhenReady() {
  const app = window.tutorInk;
  const canvas = app.canvas;
  const begin = () => new VerifyDemo(app).start().catch((error) => {
    console.error("verification demo failed to start", error);
    const status = el("verify-status");
    status.dataset.state = "error";
    status.textContent = "The checking demonstration could not start. Your notebook still works.";
  });
  if (canvas.dataset.ready === "true") {
    begin();
    return;
  }
  new MutationObserver((_, observer) => {
    if (canvas.dataset.ready === "true") {
      observer.disconnect();
      begin();
    }
  }).observe(canvas, { attributes: true, attributeFilter: ["data-ready"] });
}

startWhenReady();
