import { reactive } from "vue";
import {
  deleteKnowledgeDocument,
  fetchKnowledgeDashboard,
  fetchKnowledgeOverview,
  reindexKnowledgeDocuments,
  retryKnowledgeDocument,
  uploadKnowledgeDocument
} from "../lib/api";

const defaultState = () => ({
  loading: false,
  uploading: false,
  reindexing: false,
  retryingDocumentId: "",
  polling: false,
  error: "",
  info: "",
  knowledgeBase: null,
  documents: [],
  summary: {
    document_count: 0,
    ready_count: 0,
    processing_count: 0,
    failed_count: 0
  },
  overview: {
    document_count: 0,
    indexed_document_count: 0,
    total_file_size_bytes: 0,
    total_file_size_label: "0 B"
  }
});

const state = reactive(defaultState());
let pollTimer = null;

function applyPayload(payload = {}) {
  state.knowledgeBase = payload.knowledge_base || null;
  state.documents = payload.documents || [];
  state.summary = {
    document_count: 0,
    ready_count: 0,
    processing_count: 0,
    failed_count: 0,
    ...(payload.summary || {})
  };
}

function syncSummaryFromDocuments() {
  state.summary = {
    document_count: state.documents.length,
    ready_count: state.documents.filter((item) => item.status === "ready").length,
    processing_count: state.documents.filter((item) => ["pending", "processing"].includes(item.status)).length,
    failed_count: state.documents.filter((item) => item.status === "failed").length
  };
}

function upsertDocument(payload) {
  if (!payload?.document_id) {
    return;
  }
  const next = [...state.documents];
  const index = next.findIndex((item) => item.document_id === payload.document_id);
  if (index >= 0) {
    next.splice(index, 1, payload);
  } else {
    next.unshift(payload);
  }
  state.documents = next;
  syncSummaryFromDocuments();
}

function hasActiveProcessingDocuments() {
  return state.documents.some((item) => ["pending", "processing"].includes(item.status));
}

export function useKnowledgeBase() {
  function stopPolling() {
    if (pollTimer) {
      window.clearTimeout(pollTimer);
      pollTimer = null;
    }
    state.polling = false;
  }

  function schedulePolling() {
    if (typeof window === "undefined") {
      return;
    }
    if (!hasActiveProcessingDocuments()) {
      stopPolling();
      return;
    }
    if (pollTimer) {
      return;
    }
    state.polling = true;
    pollTimer = window.setTimeout(async () => {
      pollTimer = null;
      try {
        await refresh({ silent: true, preserveError: true });
      } catch (_error) {}
      schedulePolling();
    }, 1800);
  }

  function clearFeedback() {
    state.error = "";
    state.info = "";
  }

  async function refresh(options = {}) {
    const { silent = false, preserveError = false } = options;
    if (!silent) {
      state.loading = true;
    }
    if (!preserveError) {
      state.error = "";
    }
    try {
      const [payload, overviewPayload] = await Promise.all([
        fetchKnowledgeDashboard(),
        fetchKnowledgeOverview().catch(() => ({}))
      ]);
      applyPayload(payload);
      if (overviewPayload) {
        state.overview = {
          document_count: overviewPayload.document_count || 0,
          indexed_document_count: overviewPayload.indexed_document_count || 0,
          total_file_size_bytes: overviewPayload.total_file_size_bytes || 0,
          total_file_size_label: overviewPayload.total_file_size_label || "0 B"
        };
      }
      schedulePolling();
      return payload;
    } catch (error) {
      if (!silent) {
        state.error = error.message || "知识库加载失败";
      }
      throw error;
    } finally {
      if (!silent) {
        state.loading = false;
      }
    }
  }

  async function upload(file) {
    state.uploading = true;
    state.error = "";
    state.info = "";
    try {
      const payload = await uploadKnowledgeDocument(file);
      upsertDocument(payload);
      state.info = "文档已上传，正在后台解析。";
      schedulePolling();
      return payload;
    } catch (error) {
      try {
        await refresh({ silent: true });
      } catch (_refreshError) {}
      state.error = error.message || "知识库上传失败";
      throw error;
    } finally {
      state.uploading = false;
    }
  }

  async function remove(documentId) {
    state.error = "";
    state.info = "";
    try {
      await deleteKnowledgeDocument(documentId);
      state.info = "文档已删除。";
      await refresh({ silent: true });
      return true;
    } catch (error) {
      state.error = error.message || "知识库文档删除失败";
      throw error;
    }
  }

  async function reindex() {
    state.reindexing = true;
    state.error = "";
    state.info = "";
    try {
      const payload = await reindexKnowledgeDocuments();
      state.info = `已加入 ${payload.queued || 0} 份文档的重建队列。`;
      await refresh({ silent: true });
      schedulePolling();
      return payload;
    } catch (error) {
      state.error = error.message || "知识库重建索引失败";
      throw error;
    } finally {
      state.reindexing = false;
    }
  }

  async function retry(documentId) {
    state.retryingDocumentId = documentId;
    state.error = "";
    state.info = "";
    try {
      const payload = await retryKnowledgeDocument(documentId);
      upsertDocument(payload);
      state.info = "文档已重新加入解析队列。";
      schedulePolling();
      return payload;
    } catch (error) {
      try {
        await refresh({ silent: true });
      } catch (_refreshError) {}
      state.error = error.message || "知识库文档重试失败";
      throw error;
    } finally {
      state.retryingDocumentId = "";
    }
  }

  function dispose() {
    stopPolling();
  }

  return {
    state,
    clearFeedback,
    refresh,
    upload,
    retry,
    remove,
    reindex,
    dispose
  };
}

export function resetKnowledgeBaseStateForTests() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  Object.assign(state, defaultState());
}
