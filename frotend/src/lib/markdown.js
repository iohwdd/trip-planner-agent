const SAFE_PROTOCOL_PATTERN = /^(https?:|mailto:|tel:)/i;

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function sanitizeHref(value = "") {
  const trimmed = String(value).trim();
  if (!trimmed || !SAFE_PROTOCOL_PATTERN.test(trimmed)) {
    return "";
  }
  return escapeHtml(trimmed);
}

function formatInline(text = "") {
  const segments = String(text).split(/(`[^`]+`)/g);
  return segments.map((segment) => {
    if (segment.startsWith("`") && segment.endsWith("`")) {
      return `<code>${escapeHtml(segment.slice(1, -1))}</code>`;
    }

    let escaped = escapeHtml(segment);
    escaped = escaped.replace(
      /\[([^\]]+)\]\(([^)]+)\)/g,
      (_match, label, href) => {
        const safeHref = sanitizeHref(href);
        const safeLabel = label;
        if (!safeHref) {
          return safeLabel;
        }
        return `<a href="${safeHref}" target="_blank" rel="noreferrer">${safeLabel}</a>`;
      }
    );
    escaped = escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    escaped = escaped.replace(/__(.+?)__/g, "<strong>$1</strong>");
    return escaped;
  }).join("");
}

function consumeList(lines, startIndex, { ordered }) {
  const tag = ordered ? "ol" : "ul";
  const pattern = ordered ? /^\d+\.\s+(.*)$/ : /^[*-]\s+(.*)$/;
  let index = startIndex;
  const items = [];

  while (index < lines.length) {
    const line = lines[index].trim();
    const match = line.match(pattern);
    if (!match) {
      break;
    }
    items.push(`<li>${formatInline(match[1])}</li>`);
    index += 1;
  }

  return {
    html: `<${tag}>${items.join("")}</${tag}>`,
    nextIndex: index
  };
}

function consumeCodeFence(lines, startIndex) {
  const fence = lines[startIndex].trim();
  const language = fence.slice(3).trim();
  let index = startIndex + 1;
  const buffer = [];

  while (index < lines.length && !lines[index].trim().startsWith("```")) {
    buffer.push(lines[index]);
    index += 1;
  }

  const className = language ? ` class="language-${escapeHtml(language)}"` : "";
  const html = `<pre><code${className}>${escapeHtml(buffer.join("\n"))}</code></pre>`;
  return {
    html,
    nextIndex: index < lines.length ? index + 1 : index
  };
}

function consumeParagraph(lines, startIndex) {
  let index = startIndex;
  const buffer = [];

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();
    if (
      !trimmed
      || trimmed.startsWith("```")
      || /^#{1,6}\s+/.test(trimmed)
      || /^[*-]\s+/.test(trimmed)
      || /^\d+\.\s+/.test(trimmed)
    ) {
      break;
    }
    buffer.push(trimmed);
    index += 1;
  }

  return {
    html: `<p>${formatInline(buffer.join("<br />"))}</p>`,
    nextIndex: index
  };
}

export function renderMarkdown(content = "") {
  const normalized = String(content || "").replaceAll("\r\n", "\n").trim();
  if (!normalized) {
    return "";
  }

  const lines = normalized.split("\n");
  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const trimmed = lines[index].trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const result = consumeCodeFence(lines, index);
      blocks.push(result.html);
      index = result.nextIndex;
      continue;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      blocks.push(`<h${level}>${formatInline(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }

    if (/^[*-]\s+/.test(trimmed)) {
      const result = consumeList(lines, index, { ordered: false });
      blocks.push(result.html);
      index = result.nextIndex;
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const result = consumeList(lines, index, { ordered: true });
      blocks.push(result.html);
      index = result.nextIndex;
      continue;
    }

    const result = consumeParagraph(lines, index);
    blocks.push(result.html);
    index = result.nextIndex;
  }

  return blocks.join("");
}
