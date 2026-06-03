const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

const ACCESS_TOKEN_KEY = "trip-planner.access-token";
const REFRESH_TOKEN_KEY = "trip-planner.refresh-token";
const GUEST_TOKEN_KEY = "trip-planner.guest-token";

function canUseStorage() {
  return typeof window !== "undefined" && Boolean(window.localStorage);
}

function readStorage(key) {
  return canUseStorage() ? window.localStorage.getItem(key) || "" : "";
}

function writeStorage(key, value) {
  if (!canUseStorage()) {
    return;
  }
  if (!value) {
    window.localStorage.removeItem(key);
    return;
  }
  window.localStorage.setItem(key, value);
}

export function getAccessToken() {
  return readStorage(ACCESS_TOKEN_KEY);
}

export function getRefreshToken() {
  return readStorage(REFRESH_TOKEN_KEY);
}

export function getGuestToken() {
  return readStorage(GUEST_TOKEN_KEY);
}

export function persistAuthTokens({ accessToken = "", refreshToken = "" } = {}) {
  writeStorage(ACCESS_TOKEN_KEY, accessToken);
  writeStorage(REFRESH_TOKEN_KEY, refreshToken);
}

export function clearAuthTokens() {
  persistAuthTokens();
}

export function persistGuestToken(token = "") {
  writeStorage(GUEST_TOKEN_KEY, token);
}

export function clearGuestToken() {
  persistGuestToken();
}

export function resetApiStorageForTests() {
  clearAuthTokens();
  clearGuestToken();
}

async function readJson(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || "请求失败，请稍后重试");
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function buildHeaders(options = {}) {
  const accessToken = getAccessToken();
  const guestToken = getGuestToken();
  const headers = new Headers(options.headers || {});

  if (!headers.has("Content-Type") && options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  } else if (guestToken) {
    headers.set("X-Guest-Token", guestToken);
  }
  return headers;
}

async function readStreamingError(response) {
  const contentType = response.headers.get("Content-Type") || "";
  if (contentType.includes("application/json")) {
    return readJson(response);
  }
  const text = await response.text().catch(() => "");
  const error = new Error(text || "请求失败，请稍后重试");
  error.status = response.status;
  throw error;
}

async function consumeSseResponse(response, { onEvent } = {}) {
  if (!response.ok) {
    await readStreamingError(response);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("当前浏览器不支持流式响应");
  }

  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      const parsed = parseEventBlock(block);
      if (!parsed) {
        continue;
      }
      await onEvent?.(parsed);
    }

    if (done) {
      break;
    }
  }

  if (buffer.trim()) {
    const parsed = parseEventBlock(buffer);
    if (parsed) {
      await onEvent?.(parsed);
    }
  }
}

function parseEventBlock(block) {
  const lines = block.split(/\r?\n/);
  let event = "message";
  const dataLines = [];

  for (const line of lines) {
    if (!line || line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (!dataLines.length) {
    return null;
  }

  const payload = JSON.parse(dataLines.join("\n"));
  if (payload.guest_token) {
    persistGuestToken(payload.guest_token);
  }
  return { event, data: payload };
}

async function request(path, options = {}) {
  const headers = buildHeaders(options);

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers
  });
  const payload = await readJson(response);
  if (payload.guest_token) {
    persistGuestToken(payload.guest_token);
  }
  return payload;
}

export async function requestAuthCode(email) {
  return request("/api/auth/codes/", {
    method: "POST",
    body: JSON.stringify({ email })
  });
}

export async function verifyAuthCode(email, code) {
  const payload = await request("/api/auth/login/verify/", {
    method: "POST",
    body: JSON.stringify({
      email,
      code,
      guest_token: getGuestToken() || null
    })
  });
  persistAuthTokens({
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token
  });
  clearGuestToken();
  return payload;
}

export async function loginWithPassword(email, password) {
  const payload = await request("/api/auth/login/password/", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
      guest_token: getGuestToken() || null
    })
  });
  persistAuthTokens({
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token
  });
  clearGuestToken();
  return payload;
}

export async function updatePassword({ currentPassword = "", newPassword }) {
  return request("/api/auth/password/", {
    method: "POST",
    body: JSON.stringify({
      current_password: currentPassword || null,
      new_password: newPassword
    })
  });
}

export async function fetchCurrentUser() {
  return request("/api/auth/me/", {
    method: "GET"
  });
}

export async function fetchKnowledgeDashboard() {
  return request("/api/knowledge/", {
    method: "GET"
  });
}

export async function fetchKnowledgeOverview() {
  return request("/api/knowledge/overview/", {
    method: "GET"
  });
}

export async function uploadKnowledgeDocument(file) {
  const body = new FormData();
  body.append("file", file);
  return request("/api/knowledge/documents/", {
    method: "POST",
    body
  });
}

export async function deleteKnowledgeDocument(documentId) {
  return request(`/api/knowledge/documents/${documentId}/`, {
    method: "DELETE"
  });
}

export async function retryKnowledgeDocument(documentId) {
  return request(`/api/knowledge/documents/${documentId}/retry/`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export async function reindexKnowledgeDocuments() {
  return request("/api/knowledge/reindex/", {
    method: "POST",
    body: JSON.stringify({})
  });
}

export async function logout() {
  try {
    await request("/api/auth/logout/", {
      method: "POST",
      body: JSON.stringify({
        refresh_token: getRefreshToken() || null
      })
    });
  } finally {
    clearAuthTokens();
  }
}

export async function createPlanRun(form) {
  return request("/api/plans/", {
    method: "POST",
    body: JSON.stringify(form)
  });
}

export async function streamPlanRun(form, { onEvent } = {}) {
  const payload = JSON.stringify(form);
  const response = await fetch(`${API_BASE_URL}/api/plans/stream/`, {
    method: "POST",
    headers: buildHeaders({
      headers: {
        Accept: "text/event-stream"
      },
      body: payload
    }),
    body: payload
  });

  await consumeSseResponse(response, { onEvent });
}

export async function getPlanRun(runId) {
  return request(`/api/plans/${runId}/`);
}

export async function createChatSession() {
  return request("/api/chat/sessions/", {
    method: "POST"
  });
}

export async function createAssistantConversation() {
  return request("/api/assistant/conversations/", {
    method: "POST"
  });
}

export async function listAssistantConversations() {
  return request("/api/assistant/conversations/");
}

export async function getRecentAssistantConversation() {
  return request("/api/assistant/conversations/recent/");
}

export async function getAssistantConversation(conversationId) {
  return request(`/api/assistant/conversations/${conversationId}/`);
}

export async function renameAssistantConversation(conversationId, title) {
  return request(`/api/assistant/conversations/${conversationId}/`, {
    method: "PATCH",
    body: JSON.stringify({ title })
  });
}

export async function deleteAssistantConversation(conversationId) {
  return request(`/api/assistant/conversations/${conversationId}/`, {
    method: "DELETE"
  });
}

export async function sendAssistantMessage(conversationId, message) {
  return request(`/api/assistant/conversations/${conversationId}/messages/`, {
    method: "POST",
    body: JSON.stringify({ message })
  });
}

export async function streamAssistantMessage(conversationId, message, { onEvent } = {}) {
  const payload = JSON.stringify({ message });
  const response = await fetch(`${API_BASE_URL}/api/assistant/conversations/${conversationId}/messages/stream/`, {
    method: "POST",
    headers: buildHeaders({
      headers: {
        Accept: "text/event-stream"
      },
      body: payload
    }),
    body: payload
  });
  await consumeSseResponse(response, { onEvent });
}

export async function listChatSessions() {
  return request("/api/chat/sessions/");
}

export async function getRecentChatSession() {
  return request("/api/chat/sessions/recent/");
}

export async function getChatSession(sessionId) {
  return request(`/api/chat/sessions/${sessionId}/`);
}

export async function renameChatSession(sessionId, title) {
  return request(`/api/chat/sessions/${sessionId}/`, {
    method: "PATCH",
    body: JSON.stringify({ title })
  });
}

export async function deleteChatSession(sessionId) {
  return request(`/api/chat/sessions/${sessionId}/`, {
    method: "DELETE"
  });
}

export async function createChatTurn(sessionId, payload) {
  return request(`/api/chat/sessions/${sessionId}/messages/`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function streamChatTurn(sessionId, payload, { onEvent } = {}) {
  const response = await fetch(`${API_BASE_URL}/api/chat/sessions/${sessionId}/messages/stream/`, {
    method: "POST",
    headers: buildHeaders({
      headers: {
        Accept: "text/event-stream"
      },
      body: JSON.stringify(payload)
    }),
    body: JSON.stringify(payload)
  });
  await consumeSseResponse(response, { onEvent });
}

export async function getChatTurn(sessionId, turnId) {
  return request(`/api/chat/sessions/${sessionId}/turns/${turnId}/`);
}

export async function saveTripPlan(sessionId, payload) {
  return request(`/api/chat/sessions/${sessionId}/plans/`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function saveRunTripPlan(runId, payload) {
  return request(`/api/plans/${runId}/save/`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function listTripPlans() {
  return request("/api/trip-plans/");
}

export async function getTripPlan(planId) {
  return request(`/api/trip-plans/${planId}/`);
}

export async function deleteTripPlan(planId) {
  return request(`/api/trip-plans/${planId}/`, {
    method: "DELETE"
  });
}

export async function resumeTripPlan(planId) {
  return request(`/api/trip-plans/${planId}/resume/`, {
    method: "POST"
  });
}
