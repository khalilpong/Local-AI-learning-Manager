const noteForm = document.querySelector("#noteForm");
const searchForm = document.querySelector("#searchForm");
const askForm = document.querySelector("#askForm");
const refreshNotes = document.querySelector("#refreshNotes");
const reviewButton = document.querySelector("#reviewButton");
const notesList = document.querySelector("#notesList");
const noteCount = document.querySelector("#noteCount");
const noteStatus = document.querySelector("#noteStatus");
const searchResults = document.querySelector("#searchResults");
const answerBox = document.querySelector("#answerBox");
const reviewBox = document.querySelector("#reviewBox");
const tagFilters = document.querySelector("#tagFilters");
const modelSelect = document.querySelector("#modelSelect");
const modelStatus = document.querySelector("#modelStatus");
const studyCard = document.querySelector("#studyCard");
const studyCount = document.querySelector("#studyCount");
const statsBox = document.querySelector("#statsBox");
const noteModal = document.querySelector("#noteModal");
const modalTitle = document.querySelector("#modalTitle");
const modalBody = document.querySelector("#modalBody");
const modalClose = document.querySelector("#modalClose");
const courseForm = document.querySelector("#courseForm");
const libraryImportForm = document.querySelector("#libraryImportForm");
const courseSelect = document.querySelector("#courseSelect");
const noteCourseSelect = document.querySelector("#noteCourseSelect");
const searchCourseSelect = document.querySelector("#searchCourseSelect");
const askCourseSelect = document.querySelector("#askCourseSelect");
const documentList = document.querySelector("#documentList");
const libraryStatus = document.querySelector("#libraryStatus");

let activeTag = null;
let lastQuery = "";

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderMarkdown(text) {
  const lines = escapeHtml(String(text || "")).split("\n");
  const html = [];
  let inCode = false;
  let code = [];
  let listType = null;
  const closeList = () => {
    if (listType) {
      html.push(`</${listType}>`);
      listType = null;
    }
  };
  const inline = (s) =>
    s
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*\s][^*]*)\*/g, "<em>$1</em>");
  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      if (inCode) {
        html.push(`<pre><code>${code.join("\n")}</code></pre>`);
        code = [];
      } else {
        closeList();
      }
      inCode = !inCode;
      continue;
    }
    if (inCode) {
      code.push(line);
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (heading) {
      closeList();
      html.push(`<h4>${inline(heading[2])}</h4>`);
    } else if (bullet || ordered) {
      const type = bullet ? "ul" : "ol";
      if (listType !== type) {
        closeList();
        html.push(`<${type}>`);
        listType = type;
      }
      html.push(`<li>${inline((bullet || ordered)[1])}</li>`);
    } else if (!line.trim()) {
      closeList();
    } else {
      closeList();
      html.push(`<p>${inline(line)}</p>`);
    }
  }
  if (inCode && code.length) {
    html.push(`<pre><code>${code.join("\n")}</code></pre>`);
  }
  closeList();
  return html.join("");
}

function highlightText(value, query) {
  const escaped = escapeHtml(value);
  const terms = String(query || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .sort((a, b) => b.length - a.length);
  if (!terms.length) return escaped;
  const pattern = new RegExp(`(${terms.join("|")})`, "gi");
  return escaped.replace(pattern, "<mark>$1</mark>");
}

async function requestJson(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(url, {
    ...options,
    headers,
  });
  if (response.status === 204) {
    return null;
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || response.statusText);
  }
  return response.json();
}

function renderTags(tags = [], { highlightActive = true } = {}) {
  return tags
    .map((tag) => {
      const active = highlightActive && tag === activeTag ? " active" : "";
      return `<span class="tag-pill${active}" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</span>`;
    })
    .join("");
}

function renderNote(note) {
  return `
    <article class="note-card" data-note-id="${note.id}">
      <div class="note-card-header">
        <h3>${escapeHtml(note.title)}</h3>
        <time>${escapeHtml(String(note.created_at || "").slice(0, 10))}</time>
      </div>
      <p>${escapeHtml(note.summary || note.content || "")}</p>
      <div class="tag-row">${renderTags(note.tags)}</div>
      <div class="note-card-actions">
        <button type="button" class="link-button" data-action="view">View</button>
        <button type="button" class="link-button" data-action="edit">Edit</button>
        <button type="button" class="link-button danger" data-action="delete">Delete</button>
      </div>
    </article>
  `;
}

function renderResult(note, query) {
  const score = typeof note.score === "number" ? Math.round(note.score * 100) : 0;
  if (note.kind === "document") {
    const citation = [note.course_name, note.location_label].filter(Boolean).join(" · ");
    return `
      <article class="result-item document-result" data-kind="document" data-document-id="${note.source_document_id}">
        <div>
          <strong>${highlightText(note.source_title || note.title, query)}</strong>
          <span class="citation-label">${escapeHtml(citation)}</span>
          <p>${highlightText(note.content || "", query)}</p>
        </div>
        <span class="score">${score}</span>
      </article>
    `;
  }
  return `
    <article class="result-item" data-kind="note" data-note-id="${note.id}">
      <div>
        <strong>${highlightText(note.title, query)}</strong>
        <p>${highlightText(note.summary || note.content || "", query)}</p>
        <div class="tag-row">${renderTags(note.tags)}</div>
      </div>
      <span class="score">${score}</span>
    </article>
  `;
}

function courseOptions(courses, emptyLabel) {
  return [
    `<option value="">${emptyLabel}</option>`,
    ...courses.map((course) => {
      const label = [course.code, course.name, course.term].filter(Boolean).join(" · ");
      return `<option value="${course.id}">${escapeHtml(label)}</option>`;
    }),
  ].join("");
}

async function loadCourses(preferredCourseId = null) {
  const previousImport = preferredCourseId || courseSelect.value;
  const previousNote = noteCourseSelect.value;
  const previousSearch = searchCourseSelect.value;
  const previousAsk = askCourseSelect.value;
  const data = await requestJson("/api/courses");
  const courses = data.courses;

  courseSelect.innerHTML = courses.length
    ? courseOptions(courses, "Select course")
    : '<option value="">Create a course first</option>';
  courseSelect.disabled = !courses.length;
  libraryImportForm.querySelector("button[type=submit]").disabled = !courses.length;
  noteCourseSelect.innerHTML = courseOptions(courses, "No course");
  searchCourseSelect.innerHTML = courseOptions(courses, "All courses");
  askCourseSelect.innerHTML = courseOptions(courses, "All courses");

  if (courses.length) {
    const available = new Set(courses.map((course) => String(course.id)));
    courseSelect.value = available.has(String(previousImport))
      ? String(previousImport)
      : String(courses[0].id);
    if (available.has(previousNote)) noteCourseSelect.value = previousNote;
    if (available.has(previousSearch)) searchCourseSelect.value = previousSearch;
    if (available.has(previousAsk)) askCourseSelect.value = previousAsk;
  }
  await loadDocuments();
}

function renderDocument(document) {
  const locationCount = document.chunks?.length || 0;
  const retry = document.status === "failed"
    ? `<button type="button" class="link-button" data-retry-document="${document.id}">Retry</button>`
    : "";
  return `
    <article class="document-item">
      <div class="document-main">
        <strong title="${escapeHtml(document.title)}">${escapeHtml(document.title)}</strong>
        <span>${escapeHtml(document.source_type.toUpperCase())} · ${locationCount} chunks</span>
      </div>
      <div class="document-state">
        <span class="status-badge status-${escapeHtml(document.status)}">${escapeHtml(document.status.replaceAll("_", " "))}</span>
        ${retry}
      </div>
      ${document.error_message ? `<p>${escapeHtml(document.error_message)}</p>` : ""}
    </article>
  `;
}

async function loadDocuments() {
  const courseId = courseSelect.value;
  if (!courseId) {
    documentList.innerHTML = '<p class="muted">Create a course to import files.</p>';
    libraryStatus.textContent = "No courses";
    return;
  }
  try {
    const params = new URLSearchParams({ course_id: courseId });
    const data = await requestJson(`/api/library/documents?${params.toString()}`);
    documentList.innerHTML = data.documents.map(renderDocument).join("") ||
      '<p class="muted">No files in this course.</p>';
    libraryStatus.textContent = `${data.documents.length} local file${data.documents.length === 1 ? "" : "s"}`;
  } catch (error) {
    libraryStatus.textContent = error.message;
  }
}

async function loadTags() {
  try {
    const data = await requestJson("/api/tags");
    const chips = data.tags
      .map((entry) => {
        const active = entry.tag === activeTag ? " active" : "";
        return `<button type="button" class="tag-chip${active}" data-tag="${escapeHtml(entry.tag)}">${escapeHtml(entry.tag)} <span>${entry.count}</span></button>`;
      })
      .join("");
    const allActive = activeTag ? "" : " active";
    tagFilters.innerHTML = `<button type="button" class="tag-chip${allActive}" data-tag="">All</button>${chips}`;
  } catch (error) {
    tagFilters.innerHTML = "";
  }
}

async function loadNotes() {
  const params = new URLSearchParams({ limit: "30" });
  if (activeTag) params.set("tag", activeTag);
  const data = await requestJson(`/api/notes?${params.toString()}`);
  notesList.innerHTML = data.notes.map(renderNote).join("") || "<p class='muted'>No notes yet.</p>";
  noteCount.textContent = `${data.notes.length} loaded`;
}

async function loadModels() {
  try {
    const data = await requestJson("/api/models");
    const models = data.models.length ? data.models : [data.current].filter(Boolean);
    if (data.current && !models.includes(data.current)) {
      models.unshift(data.current);
    }
    modelSelect.innerHTML = models
      .map(
        (model) =>
          `<option value="${escapeHtml(model)}"${model === data.current ? " selected" : ""}>${escapeHtml(model)}</option>`
      )
      .join("");
    modelStatus.textContent = data.available
      ? "Ollama ready."
      : "Ollama offline - local fallback.";
  } catch (error) {
    modelSelect.innerHTML = "<option value=''>unavailable</option>";
    modelStatus.textContent = error.message;
  }
}

modelSelect.addEventListener("change", async () => {
  const model = modelSelect.value;
  if (!model) return;
  modelStatus.textContent = "Saving...";
  try {
    await requestJson("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ ollama_model: model }),
    });
    modelStatus.textContent = `Using ${model}.`;
  } catch (error) {
    modelStatus.textContent = error.message;
  }
});

let studyQueue = [];
let studyRevealed = false;

async function loadStudyQueue() {
  try {
    const data = await requestJson("/api/study/queue?limit=20");
    studyQueue = data.notes;
    studyRevealed = false;
    renderStudyCard();
  } catch (error) {
    studyCard.innerHTML = `<p class='muted'>${escapeHtml(error.message)}</p>`;
  }
}

function renderStudyCard() {
  studyCount.textContent = `${studyQueue.length} due`;
  if (!studyQueue.length) {
    studyCard.innerHTML =
      "<p class='muted'>Nothing due right now. New notes join the queue automatically.</p>";
    return;
  }
  const note = studyQueue[0];
  if (!studyRevealed) {
    studyCard.innerHTML = `
      <span class="study-label">Can you recall this note?</span>
      <h3>${escapeHtml(note.title)}</h3>
      <div class="tag-row">${renderTags(note.tags)}</div>
      <button type="button" id="studyReveal">Show answer</button>
    `;
    studyCard.querySelector("#studyReveal").addEventListener("click", () => {
      studyRevealed = true;
      renderStudyCard();
    });
  } else {
    studyCard.innerHTML = `
      <h3>${escapeHtml(note.title)}</h3>
      <div class="md-content study-answer">${renderMarkdown(note.content)}</div>
      <div class="study-grades">
        <button type="button" class="grade-again" data-grade="again">Again</button>
        <button type="button" class="grade-good" data-grade="good">Good</button>
        <button type="button" class="grade-easy" data-grade="easy">Easy</button>
      </div>
      <p class="muted study-hint">Again: soon again · Good: ~1 day+ · Easy: ~3 days+</p>
    `;
    studyCard.querySelectorAll("[data-grade]").forEach((button) => {
      button.addEventListener("click", () => gradeCurrentNote(button.dataset.grade));
    });
  }
}

async function gradeCurrentNote(grade) {
  const note = studyQueue[0];
  if (!note) return;
  try {
    await requestJson(`/api/study/${note.id}/grade`, {
      method: "POST",
      body: JSON.stringify({ grade }),
    });
    studyQueue.shift();
    studyRevealed = false;
    if (!studyQueue.length) {
      await loadStudyQueue();
    } else {
      renderStudyCard();
    }
    loadStats();
  } catch (error) {
    studyCard.innerHTML = `<p class='muted'>${escapeHtml(error.message)}</p>`;
  }
}

async function loadStats() {
  try {
    const data = await requestJson("/api/stats");
    const max = Math.max(1, ...data.daily_activity.map((day) => day.count));
    const bars = data.daily_activity
      .map(
        (day) =>
          `<div class="bar" style="height:${Math.max(4, Math.round((day.count / max) * 100))}%" title="${day.date}: ${day.count}"></div>`
      )
      .join("");
    statsBox.innerHTML = `
      <div class="stat-grid">
        <div class="stat"><strong>${data.total_notes}</strong><span>Total notes</span></div>
        <div class="stat"><strong>${data.notes_this_week}</strong><span>This week</span></div>
        <div class="stat"><strong>${data.streak_days}</strong><span>Day streak</span></div>
        <div class="stat"><strong>${data.due_now}</strong><span>Due to review</span></div>
        <div class="stat"><strong>${data.reviewed_today}</strong><span>Reviewed today</span></div>
      </div>
      <div class="bar-chart">${bars}</div>
      <p class="muted bar-caption">Notes created over the last 14 days</p>
    `;
  } catch (error) {
    statsBox.innerHTML = `<p class='muted'>${escapeHtml(error.message)}</p>`;
  }
}

function setActiveTag(tag) {
  activeTag = tag || null;
  loadTags();
  loadNotes().catch((error) => {
    noteCount.textContent = error.message;
  });
}

noteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(noteForm);
  noteStatus.textContent = "Saving...";
  try {
    await requestJson("/api/notes", {
      method: "POST",
      body: JSON.stringify({
        title: form.get("title"),
        source: form.get("source"),
        content: form.get("content"),
        course_id: form.get("course_id") ? Number(form.get("course_id")) : null,
      }),
    });
    noteForm.reset();
    noteStatus.textContent = "Saved locally.";
    await loadNotes();
    await loadTags();
    loadStudyQueue();
    loadStats();
  } catch (error) {
    noteStatus.textContent = error.message;
  }
});

searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(searchForm);
  const query = String(form.get("q") || "").trim();
  if (!query) return;
  lastQuery = query;
  searchResults.innerHTML = "<p class='muted'>Searching...</p>";
  try {
    const params = new URLSearchParams({ q: query });
    if (activeTag) params.set("tag", activeTag);
    if (form.get("course_id")) params.set("course_id", form.get("course_id"));
    const data = await requestJson(`/api/search?${params.toString()}`);
    searchResults.innerHTML =
      data.results.map((note) => renderResult(note, query)).join("") ||
      "<p class='muted'>No matching notes.</p>";
  } catch (error) {
    searchResults.innerHTML = `<p class='muted'>${escapeHtml(error.message)}</p>`;
  }
});

askForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(askForm);
  answerBox.textContent = "Thinking locally...";
  try {
    const data = await requestJson("/api/ask", {
      method: "POST",
      body: JSON.stringify({
        question: form.get("question"),
        course_id: form.get("course_id") ? Number(form.get("course_id")) : null,
      }),
    });
    const sources = data.sources
      .map((source) => {
        const location = source.kind === "document" && source.location_label
          ? ` · ${source.location_label}`
          : "";
        return `<li>${escapeHtml(source.title)}${escapeHtml(location)}</li>`;
      })
      .join("");
    answerBox.innerHTML = `
      <div class="md-content">${renderMarkdown(data.answer)}</div>
      <strong>Sources</strong>
      <ul>${sources}</ul>
    `;
  } catch (error) {
    answerBox.textContent = error.message;
  }
});

reviewButton.addEventListener("click", async () => {
  reviewButton.disabled = true;
  reviewButton.textContent = "Generating...";
  try {
    const review = await requestJson("/api/reviews/weekly", {
      method: "POST",
      body: JSON.stringify({}),
    });
    reviewBox.innerHTML = `
      <strong>${escapeHtml(review.week_start)} to ${escapeHtml(review.week_end)}</strong>
      <div class="md-content">${renderMarkdown(review.content)}</div>
    `;
  } catch (error) {
    reviewBox.innerHTML = `<p class='muted'>${escapeHtml(error.message)}</p>`;
  } finally {
    reviewButton.disabled = false;
    reviewButton.textContent = "Generate this week";
  }
});

refreshNotes.addEventListener("click", () => {
  loadNotes().catch((error) => {
    noteCount.textContent = error.message;
  });
});

tagFilters.addEventListener("click", (event) => {
  const chip = event.target.closest("[data-tag]");
  if (!chip) return;
  setActiveTag(chip.dataset.tag || null);
});

function findNoteCard(target) {
  return target.closest(".note-card, .result-item");
}

notesList.addEventListener("click", (event) => {
  const tagPill = event.target.closest(".tag-pill");
  if (tagPill) {
    setActiveTag(tagPill.dataset.tag);
    return;
  }
  const card = findNoteCard(event.target);
  if (!card) return;
  const noteId = Number(card.dataset.noteId);
  const action = event.target.dataset.action;
  if (action === "delete") {
    deleteNote(noteId);
  } else if (action === "edit") {
    openNoteModal(noteId, { editing: true });
  } else {
    openNoteModal(noteId, { editing: false });
  }
});

searchResults.addEventListener("click", (event) => {
  const tagPill = event.target.closest(".tag-pill");
  if (tagPill) {
    setActiveTag(tagPill.dataset.tag);
    return;
  }
  const card = findNoteCard(event.target);
  if (!card) return;
  if (card.dataset.kind === "document") return;
  openNoteModal(Number(card.dataset.noteId), { editing: false });
});

courseForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(courseForm);
  libraryStatus.textContent = "Adding course...";
  try {
    const course = await requestJson("/api/courses", {
      method: "POST",
      body: JSON.stringify({
        name: form.get("name"),
        code: form.get("code"),
        term: form.get("term"),
      }),
    });
    courseForm.reset();
    await loadCourses(course.id);
  } catch (error) {
    libraryStatus.textContent = error.message;
  }
});

libraryImportForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const files = Array.from(libraryImportForm.elements.files.files || []);
  const courseId = courseSelect.value;
  if (!files.length || !courseId) return;

  const failures = [];
  for (const [index, file] of files.entries()) {
    libraryStatus.textContent = `Importing ${index + 1} of ${files.length}...`;
    const body = new FormData();
    body.set("course_id", courseId);
    body.set("file", file);
    try {
      await requestJson("/api/library/import", { method: "POST", body });
    } catch (error) {
      failures.push(`${file.name}: ${error.message}`);
    }
  }
  libraryImportForm.elements.files.value = "";
  await loadDocuments();
  if (failures.length) {
    libraryStatus.textContent = `${files.length - failures.length} imported, ${failures.length} failed`;
  }
});

courseSelect.addEventListener("change", loadDocuments);
documentList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-retry-document]");
  if (!button) return;
  button.disabled = true;
  libraryStatus.textContent = "Retrying...";
  try {
    await requestJson(`/api/library/documents/${button.dataset.retryDocument}/retry`, {
      method: "POST",
    });
    await loadDocuments();
  } catch (error) {
    libraryStatus.textContent = error.message;
    button.disabled = false;
  }
});

async function deleteNote(noteId) {
  if (!window.confirm("Delete this note? This cannot be undone.")) return;
  try {
    await requestJson(`/api/notes/${noteId}`, { method: "DELETE" });
    closeModal();
    await loadNotes();
    await loadTags();
    loadStudyQueue();
    loadStats();
  } catch (error) {
    window.alert(error.message);
  }
}

function closeModal() {
  noteModal.classList.add("hidden");
  modalBody.innerHTML = "";
}

modalClose.addEventListener("click", closeModal);
noteModal.addEventListener("click", (event) => {
  if (event.target === noteModal) closeModal();
});

function renderNoteView(note, similar) {
  const similarItems = similar
    .map(
      (item) => `
        <li class="similar-item" data-note-id="${item.id}">
          <span>${escapeHtml(item.title)}</span>
          <span class="score">${Math.round((item.score || 0) * 100)}</span>
        </li>
      `
    )
    .join("");
  return `
    <div class="modal-meta">
      <span>${escapeHtml(note.source || "uncategorized")}</span>
      <time>${escapeHtml(String(note.created_at || "").slice(0, 10))}</time>
    </div>
    <div class="tag-row">${renderTags(note.tags)}</div>
    <div class="modal-content-text md-content">${renderMarkdown(note.content)}</div>
    <div class="modal-actions">
      <button type="button" class="ghost-button" id="modalEditButton">Edit</button>
      <button type="button" class="link-button danger" id="modalDeleteButton">Delete</button>
    </div>
    <div class="section-heading modal-similar-heading">
      <h3>Similar notes</h3>
    </div>
    <ul class="similar-list">${similarItems || "<li class='muted'>No similar notes yet.</li>"}</ul>
  `;
}

function renderNoteEdit(note) {
  return `
    <form id="modalEditForm" class="stack">
      <label>
        Title
        <input name="title" type="text" value="${escapeHtml(note.title)}" required maxlength="160">
      </label>
      <label>
        Source
        <input name="source" type="text" value="${escapeHtml(note.source || "")}" maxlength="80">
      </label>
      <label>
        Note
        <textarea name="content" required>${escapeHtml(note.content)}</textarea>
      </label>
      <div class="modal-actions">
        <button type="submit">Save changes</button>
        <button type="button" class="ghost-button" id="modalCancelButton">Cancel</button>
      </div>
      <p class="form-status" id="modalEditStatus" role="status"></p>
    </form>
  `;
}

async function openNoteModal(noteId, { editing = false } = {}) {
  noteModal.classList.remove("hidden");
  modalTitle.textContent = "Loading...";
  modalBody.innerHTML = "<p class='muted'>Loading note...</p>";
  try {
    const data = await requestJson(`/api/notes/${noteId}`);
    const note = data.note;
    modalTitle.textContent = note.title;
    if (editing) {
      modalBody.innerHTML = renderNoteEdit(note);
      bindEditForm(note, data.similar);
    } else {
      modalBody.innerHTML = renderNoteView(note, data.similar);
      bindViewActions(note, data.similar);
    }
  } catch (error) {
    modalTitle.textContent = "Note";
    modalBody.innerHTML = `<p class='muted'>${escapeHtml(error.message)}</p>`;
  }
}

function bindViewActions(note) {
  const editButton = modalBody.querySelector("#modalEditButton");
  const deleteButton = modalBody.querySelector("#modalDeleteButton");
  const similarList = modalBody.querySelector(".similar-list");
  editButton?.addEventListener("click", () => openNoteModal(note.id, { editing: true }));
  deleteButton?.addEventListener("click", () => deleteNote(note.id));
  similarList?.addEventListener("click", (event) => {
    const item = event.target.closest(".similar-item");
    if (!item) return;
    openNoteModal(Number(item.dataset.noteId), { editing: false });
  });
}

function bindEditForm(note) {
  const form = modalBody.querySelector("#modalEditForm");
  const cancelButton = modalBody.querySelector("#modalCancelButton");
  const status = modalBody.querySelector("#modalEditStatus");
  cancelButton.addEventListener("click", () => openNoteModal(note.id, { editing: false }));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    status.textContent = "Saving...";
    try {
      await requestJson(`/api/notes/${note.id}`, {
        method: "PUT",
        body: JSON.stringify({
          title: formData.get("title"),
          source: formData.get("source"),
          content: formData.get("content"),
        }),
      });
      await loadNotes();
      await loadTags();
      openNoteModal(note.id, { editing: false });
    } catch (error) {
      status.textContent = error.message;
    }
  });
}

document.addEventListener("keydown", (event) => {
  const tag = document.activeElement?.tagName;
  if (event.key === "Escape") {
    closeModal();
    return;
  }
  if (tag === "INPUT" || tag === "TEXTAREA" || event.metaKey || event.ctrlKey || event.altKey) {
    return;
  }
  if (event.key === "/") {
    event.preventDefault();
    searchForm.querySelector("input[name=q]").focus();
  } else if (event.key === "n") {
    event.preventDefault();
    noteForm.querySelector("input[name=title]").focus();
  }
});

loadTags();
loadStudyQueue();
loadStats();
loadModels();
loadCourses().catch((error) => {
  libraryStatus.textContent = error.message;
});
