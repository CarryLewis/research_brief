const SELECTORS = {
  knowledge: "#knowledge-objects",
  questions: "#thinking-objects",
  projects: "#project-objects",
  observatory: "#observatory-objects",
};

function text(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value) node.textContent = value;
  return node;
}

function formatMeta(value) {
  if (!value) return "";
  if (/^\d{4}-\d{2}-\d{2}/.test(value)) return value;
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function metaRow(item) {
  const row = document.createElement("p");
  row.className = "meta";
  const parts = [item.status, item.date, item.source]
    .filter(Boolean)
    .map(formatMeta);
  parts.forEach((part) => {
    const span = document.createElement("span");
    span.textContent = part;
    row.appendChild(span);
  });
  return row;
}

function relations(related) {
  if (!related || related.length === 0) return null;
  const details = document.createElement("details");
  details.className = "relations";
  const summary = document.createElement("summary");
  summary.textContent =
    related.length === 1
      ? "1 related"
      : `${related.length} related`;
  details.appendChild(summary);
  const line = document.createElement("p");
  line.className = "relation-list";
  line.textContent = related.join(" · ");
  details.appendChild(line);
  return details;
}

function knowledgeObject(item) {
  const article = document.createElement("article");
  article.className = `object object--${item.kind || "knowledge"}`;
  article.append(
    text("p", "object-type", item.type),
    text("h3", "object-title", item.title),
    text("p", "object-body", item.description),
    metaRow(item)
  );
  const rel = relations(item.related);
  if (rel) article.appendChild(rel);
  return article;
}

function questionObject(item) {
  const article = document.createElement("article");
  article.className = "object object--question";
  article.append(
    text("p", "object-type", item.type),
    text("h3", "object-title", item.title),
    metaRow(item)
  );
  const rel = relations(item.related);
  if (rel) article.appendChild(rel);
  return article;
}

function projectObject(item) {
  const article = document.createElement("article");
  article.className = "object object--project";
  article.append(
    text("p", "object-type", item.type),
    text("h3", "object-title", item.title)
  );

  const fields = document.createElement("dl");
  fields.className = "project-fields";
  [
    ["Problem", item.problem],
    ["Approach", item.approach],
    ["Current state", item.state],
  ].forEach(([label, value]) => {
    if (!value) return;
    const wrap = document.createElement("div");
    wrap.className = "project-field";
    wrap.append(text("dt", "", label), text("dd", "", value));
    fields.appendChild(wrap);
  });
  article.appendChild(fields);
  article.appendChild(metaRow(item));
  const rel = relations(item.related);
  if (rel) article.appendChild(rel);
  return article;
}

function renderList(selector, items, factory) {
  const root = document.querySelector(selector);
  if (!root) return;
  root.replaceChildren();
  items.forEach((item) => root.appendChild(factory(item)));
}

function watchSections() {
  const links = [...document.querySelectorAll('.index-nav a[href^="#"]')];
  const sections = links
    .map((link) => document.querySelector(link.getAttribute("href")))
    .filter(Boolean);

  if (sections.length === 0) return;

  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      links.forEach((link) => {
        const current = link.getAttribute("href") === `#${visible.target.id}`;
        if (current) link.setAttribute("aria-current", "true");
        else link.removeAttribute("aria-current");
      });
    },
    { rootMargin: "-20% 0px -60% 0px", threshold: [0.1, 0.25, 0.5] }
  );

  sections.forEach((section) => observer.observe(section));
}

async function loadContent() {
  const response = await fetch("content/homepage.json");
  if (!response.ok) {
    throw new Error("Could not load homepage content.");
  }
  return response.json();
}

async function init() {
  watchSections();
  try {
    const data = await loadContent();
    renderList(SELECTORS.knowledge, data.knowledge, knowledgeObject);
    renderList(SELECTORS.questions, data.questions, questionObject);
    renderList(SELECTORS.projects, data.projects, projectObject);
    renderList(SELECTORS.observatory, data.observatory, knowledgeObject);
  } catch (error) {
    document.querySelectorAll(".objects-slot").forEach((slot) => {
      slot.replaceChildren(
        text(
          "p",
          "placeholder-note",
          "Serve this folder over HTTP to load the records. From frontend/: python -m http.server 4173"
        )
      );
    });
    console.error(error);
  }
}

init();
