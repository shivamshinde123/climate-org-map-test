/**
 * survey.html: the Localized Climate Action survey, which replaces the Google
 * Form "Climate Organizations Map VERIFICATION". Every section, question,
 * option, required flag and branch comes from data/survey.json (imported from
 * the form), shown one section at a time like the original.
 *
 * Answers go to the Supabase `survey_responses` table, keyed by question id.
 * An organization's response waits for the admin to verify it on the map; a
 * municipal or individual response is research only. Opening the survey from a
 * map listing (?org=…&name=…) pre-fills that organization. Helpers
 * (organizationControl, enhanceOrganizationFields, …) come from forms.js.
 */

const SURVEY_URL = "data/survey.json";
const CONNECTIONS = ["organization", "municipality", "individual"]; // Order of the first question's options.
const ORG_FIELDS = ["name", "website_url", "address", "city", "state", "postal_code"];

const page = {
  form: document.querySelector("#survey-form"),
  sections: document.querySelector("#survey-sections"),
  back: document.querySelector("#survey-back"),
  next: document.querySelector("#survey-next"),
  message: document.querySelector("#survey-message"),
  done: document.querySelector("#survey-done"),
  verifying: document.querySelector("#survey-verifying"),
};

let survey;
let sectionById;
let questionById;
const history = []; // Sections visited before the current one.
let current;
const params = new URLSearchParams(location.search);

/** Help text as HTML: paragraphs, "* " bullet lists, "____" rules, and the GCC link. */
function richText(text) {
  const link = (html) =>
    html.replace(
      /GreenCommunityCatalysts\.com\/localized-climate-action-initiative/g,
      '<a class="popup-link" href="https://greencommunitycatalysts.com/localized-climate-action-initiative" target="_blank" rel="noopener noreferrer">$&</a>',
    );
  return String(text ?? "")
    .trim()
    .split(/\n\s*\n/)
    .map((block) => {
      if (/^_{5,}$/.test(block.trim())) return "<hr />";
      const lines = block.split("\n");
      const bullets = lines.filter((line) => line.startsWith("* "));
      const prose = lines.filter((line) => !line.startsWith("* ") && !/^_{5,}$/.test(line.trim()));
      const list = bullets.length ? `<ul>${bullets.map((b) => `<li>${link(escapeText(b.slice(2)))}</li>`).join("")}</ul>` : "";
      const rule = lines.some((line) => /^_{5,}$/.test(line.trim())) ? "<hr />" : "";
      return `${prose.length ? `<p>${link(escapeText(prose.join(" ")))}</p>` : ""}${list}${rule}`;
    })
    .join("");
}

/** The form's example image, redrawn as a real map listing card. */
function exampleListing(question) {
  return `
    <figure class="survey-example">
      <figcaption class="question-title">${escapeText(question.title)}</figcaption>
      <div class="example-card">
        <span class="popup-verified">Verified organization</span>
        <div class="popup-name">Example Climate Group</div>
        <div class="popup-address">123 Main St<br />Boston, MA 02130</div>
        <dl class="popup-fields">
          <div><dt>Type:</dt><dd>Nonprofit / Grassroots</dd></div>
          <div><dt>Audience:</dt><dd>Residents / Municipality</dd></div>
          <div><dt>Resilience:</dt><dd>Both</dd></div>
          <div><dt>Activity:</dt><dd>Action</dd></div>
          <div><dt>Climate:</dt><dd>Energy Efficiency</dd></div>
          <div><dt>Reach:</dt><dd>Town / City</dd></div>
        </dl>
        <section class="popup-profile"><span class="popup-link">Website →</span></section>
      </div>
    </figure>`;
}

function choiceList(question) {
  const kind = question.type === "checkbox" ? "checkbox" : "radio";
  const options = question.options
    .map(
      (option) => `
        <label class="choice"><input type="${kind}" name="${question.id}" value="${escapeText(option.label)}" />
          <span>${escapeText(option.label)}</span></label>`,
    )
    .join("");
  const other = question.other
    ? `<label class="choice choice-other"><input type="${kind}" name="${question.id}" value="__other__" />
         <span>Other:</span><input type="text" name="${question.id}__other" aria-label="Other answer" /></label>`
    : "";
  return `<div class="choices" role="${kind === "radio" ? "radiogroup" : "group"}" aria-labelledby="q-${question.id}">${options}${other}</div>`;
}

function renderQuestion(question) {
  if (question.type === "example") return exampleListing(question);
  const required = question.required ? ' <span class="required-mark" aria-hidden="true">*</span>' : "";
  const help = question.help ? `<p class="question-help">${escapeText(question.help)}</p>` : "";
  let control;
  if (ORG_FIELDS.includes(question.map_field)) {
    control = organizationControl(question.map_field, page.form.id, { required: question.required });
  } else if (question.options) {
    control = choiceList(question);
  } else if (question.type === "paragraph") {
    control = `<textarea name="${question.id}" rows="3"></textarea>`;
  } else {
    const type = question.map_field === "respondent_email" ? "email" : "text";
    control = `<input name="${question.id}" type="${type}" ${type === "email" ? 'autocomplete="email"' : ""} />`;
  }
  const tag = question.options ? "div" : "label";
  return `
    <${tag} class="question" data-question="${question.id}">
      <span class="question-title" id="q-${question.id}">${escapeText(question.title)}${required}</span>
      ${help}
      ${control}
      <span class="question-error" hidden>This is a required question</span>
    </${tag}>`;
}

function renderSections() {
  page.sections.innerHTML = survey.sections
    .map(
      (section, index) => `
        <section class="form-card survey-section" data-section="${section.id}" hidden>
          <h2 class="${index ? "survey-section-title" : "visually-hidden"}">${escapeText(section.title)}</h2>
          ${section.help ? `<div class="survey-help">${richText(section.help)}</div>` : ""}
          ${section.questions.map(renderQuestion).join("")}
        </section>`,
    )
    .join("");
  // "Other:" text counts as choosing Other.
  page.sections.querySelectorAll(".choice-other input[type=text]").forEach((input) => {
    input.addEventListener("input", () => {
      const choice = input.closest(".choice-other").querySelector("input[value=__other__]");
      if (input.value.trim()) choice.checked = true;
      updateNextLabel();
    });
  });
}

/**
 * A field by name. Question ids are numbers, and form.elements["554755556"]
 * would be read as a position, not a name, so look fields up by name.
 */
const field = (name) => page.form.querySelector(`[name="${name}"]`);

/** One question's answer: text, a chosen option, or a list of ticked options. */
function answerOf(question) {
  if (ORG_FIELDS.includes(question.map_field)) return field(question.map_field).value.trim();
  if (question.options) {
    const other = (field(`${question.id}__other`)?.value ?? "").trim();
    const picked = [...page.form.querySelectorAll(`input[name="${question.id}"]:checked`)]
      .map((input) => (input.value === "__other__" ? other : input.value))
      .filter(Boolean);
    return question.type === "checkbox" ? picked : picked[0] ?? "";
  }
  return (field(question.id)?.value ?? "").trim();
}

const isEmpty = (answer) => (Array.isArray(answer) ? answer.length === 0 : !answer);

function validateSection(section) {
  let firstProblem = null;
  section.questions.forEach((question) => {
    if (question.type === "example") return;
    const box = page.sections.querySelector(`[data-question="${question.id}"]`);
    const error = box.querySelector(".question-error");
    const answer = answerOf(question);
    let problem = question.required && isEmpty(answer) ? "This is a required question" : "";
    if (!problem && question.map_field === "respondent_email" && answer && !box.querySelector("input").checkValidity()) {
      problem = "Please enter a valid email address";
    }
    error.textContent = problem;
    error.hidden = !problem;
    box.classList.toggle("has-error", Boolean(problem));
    if (problem && !firstProblem) firstProblem = box;
  });
  if (firstProblem) {
    firstProblem.scrollIntoView({ behavior: "smooth", block: "center" });
    firstProblem.querySelector("input, textarea, select")?.focus({ preventScroll: true });
  }
  return !firstProblem;
}

/** Where the survey goes after `section`: a branch picked by an answer, the next section, or null to submit. */
function nextSectionId(section) {
  for (const question of section.questions) {
    const branch = question.options?.find((option) => option.goto && option.label === answerOf(question));
    if (branch) return branch.goto;
  }
  if (section.after === "submit") return null;
  if (section.after === "next") return survey.sections[survey.sections.indexOf(section) + 1]?.id ?? null;
  return section.after;
}

/** The pages still ahead from `section`, following the answers given so far (defaults where unanswered). */
function remainingPath(section) {
  const path = [section];
  for (let id = nextSectionId(section); id && path.length < survey.sections.length; id = nextSectionId(sectionById[id])) {
    path.push(sectionById[id]);
  }
  return path;
}

/** "Page 2 of 5", the progress bar, and page buttons (earlier pages can be revisited). */
function updateProgress() {
  const pages = [...history, ...remainingPath(current)];
  const number = history.length + 1;
  document.querySelector("#survey-page-label").textContent = `Page ${number} of ${pages.length}`;
  document.querySelector("#survey-progress-fill").style.width = `${(number / pages.length) * 100}%`;
  document.querySelector("#survey-pages").innerHTML = pages
    .map((section, index) => {
      const state = index < history.length ? "done" : index === history.length ? "current" : "ahead";
      const label = `Page ${index + 1}${state === "done" ? " (go back)" : state === "current" ? " (current)" : ""}`;
      return `<li><button type="button" class="survey-page ${state}" data-page="${index}" aria-label="${label}"
        ${state === "current" ? 'aria-current="step"' : ""} ${state === "ahead" ? "disabled" : ""}>${index + 1}</button></li>`;
    })
    .join("");
}

function updateNextLabel() {
  page.next.textContent = nextSectionId(current) ? "Next" : "Submit";
  updateProgress();
}

function show(section) {
  page.sections.querySelectorAll(".survey-section").forEach((el) => (el.hidden = el.dataset.section !== section.id));
  current = section;
  page.back.hidden = history.length === 0;
  page.message.hidden = true;
  updateNextLabel();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/** Answers from every section on the path taken, keyed by question id. */
function collectAnswers() {
  const answers = {};
  [...history, current].forEach((section) =>
    section.questions.forEach((question) => {
      if (question.type === "example") return;
      const answer = answerOf(question);
      if (!isEmpty(answer)) answers[question.id] = answer;
    }),
  );
  // An exact address picked from the suggestions saves the admin a lookup.
  const values = Object.fromEntries(ORG_FIELDS.map((key) => [key, field(key)?.value.trim() ?? ""]));
  const picked = pickedSuggestion(page.form, values);
  if (picked) answers._location = { latitude: picked.latitude, longitude: picked.longitude, location_precision: "address_suggestion" };
  return answers;
}

async function submitSurvey() {
  const config = supabaseConfig();
  if (!config) throw new Error("The survey is not accepting responses yet. Please try again later.");
  const connectionQuestion = Object.values(questionById).find((q) => q.map_field === "connection");
  const connection = CONNECTIONS[connectionQuestion.options.findIndex((option) => option.label === answerOf(connectionQuestion))];
  const row = {
    connection,
    organization_id: connection === "organization" ? params.get("org") || null : null,
    answers: collectAnswers(),
    review_status: connection === "organization" ? "pending" : "research",
  };
  const response = await fetch(`${config.url}/rest/v1/survey_responses`, {
    method: "POST",
    headers: {
      apikey: config.anonKey,
      Authorization: `Bearer ${config.anonKey}`,
      "Content-Type": "application/json",
      Prefer: "return=minimal",
    },
    body: JSON.stringify(row),
  });
  if (!response.ok) throw new Error(`Your answers could not be saved (${response.status}). Please try again.`);
}

/** Opening the survey from a map listing fills in that organization. */
function prefillFromListing() {
  if (!params.get("org")) return;
  const connection = Object.values(questionById).find((q) => q.map_field === "connection");
  const first = page.form.querySelector(`input[name="${connection.id}"]`);
  first.checked = true;
  const fill = { name: "name", website_url: "website", address: "address", city: "city", state: "state", postal_code: "zip" };
  Object.entries(fill).forEach(([key, param]) => {
    const value = params.get(param);
    if (!value) return;
    field(key).value = key === "state" ? stateCode(value) ?? "" : value;
  });
  field("state").dispatchEvent(new Event("change"));
  if (params.get("name")) {
    page.verifying.hidden = false;
    page.verifying.querySelector("strong").textContent = params.get("name");
  }
}

async function startSurvey() {
  const response = await fetch(SURVEY_URL);
  if (!response.ok) throw new Error(`Survey request failed with ${response.status}`);
  survey = await response.json();
  sectionById = Object.fromEntries(survey.sections.map((section) => [section.id, section]));
  questionById = Object.fromEntries(survey.sections.flatMap((section) => section.questions.map((q) => [q.id, q])));
  renderSections();
  enhanceOrganizationFields(page.form);
  prefillFromListing();
  show(survey.sections[0]);

  page.form.addEventListener("change", updateNextLabel);
  page.back.addEventListener("click", () => show(history.pop()));
  // A page button jumps back to an earlier page; answers on every page are kept.
  document.querySelector("#survey-pages").addEventListener("click", (event) => {
    const button = event.target.closest("button.done");
    if (!button) return;
    const index = Number(button.dataset.page);
    const target = history[index];
    history.length = index;
    show(target);
  });
  page.form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!validateSection(current)) return;
    const next = nextSectionId(current);
    if (next) {
      history.push(current);
      return show(sectionById[next]);
    }
    page.next.disabled = true;
    showMessage(page.message, "Submitting…");
    try {
      await submitSurvey();
      page.form.hidden = true;
      page.message.hidden = true;
      page.verifying.hidden = true;
      page.done.hidden = false;
      page.done.querySelector(".survey-help").innerHTML = richText(survey.confirmation);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (error) {
      showMessage(page.message, escapeText(error.message), "error");
    } finally {
      page.next.disabled = false;
    }
  });
}

startSurvey().catch((error) => {
  console.error(error);
  showMessage(page.message, "The survey could not be loaded. Please try again later.", "error");
});
