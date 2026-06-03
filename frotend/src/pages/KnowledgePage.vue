<template>
  <div class="knowledge-page page-shell">
    <transition name="fade-slide">
      <p v-if="toast.message" class="knowledge-toast" :data-tone="toast.tone">{{ toast.message }}</p>
    </transition>

    <article v-if="!canManage" class="collection-state">
      当前账号无权访问知识库。
    </article>

    <template v-else>
      <div class="knowledge-head-container" style="flex-wrap: wrap; gap: 16px;">
        <div class="knowledge-head-intro">
          <h1>内部数据大盘</h1>
          <p>管理和浏览所有系统核心业务数据及知识归档。</p>
        </div>
        <div class="knowledge-upload-inline" style="display: flex; gap: 12px; align-items: center;">
            <input
              ref="fileInput"
              class="hidden-input"
              type="file"
              accept=".md,.txt,.pdf,text/plain,text/markdown,application/pdf"
              @change="onFileChange"
              style="display: none"
            />
            <span v-if="selectedFile" style="font-size: 0.9rem; color: var(--text-soft);">已选择: {{ selectedFile.name }}</span>
            <button
              class="primary-button bounce upload-button"
              type="button"
              :disabled="knowledge.state.uploading"
              @click="handleUploadAction"
              style="border-radius: var(--radius-xl); padding: 10px 20px;"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 6px;">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
              </svg>
              {{ knowledge.state.uploading ? "上传中..." : (selectedFile ? "确认上传" : "上传文件") }}
            </button>
        </div>
      </div>

      <!-- 顶部总览统计信息 -->
      <div class="knowledge-stats-grid">
        <!-- 统计卡片 1：总数 -->
        <div class="stat-card bounce">
          <div class="stat-icon-wrapper">
            <div class="stat-icon">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            </div>
            <span class="stat-badge neutral">全量档案</span>
          </div>
          <div class="stat-details">
            <span class="stat-title">总文档数量</span>
            <span class="stat-value">{{ knowledge.state.overview?.document_count || 0 }}</span>
          </div>
        </div>

        <!-- 统计卡片 2：处理完成 -->
        <div class="stat-card bounce">
          <div class="stat-icon-wrapper">
            <div class="stat-icon" style="color: #10b981; border-color: rgba(16, 185, 129, 0.4); background: rgba(16, 185, 129, 0.1)">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
            </div>
            <span class="stat-badge positive">已就绪</span>
          </div>
          <div class="stat-details">
            <span class="stat-title">已入库索引</span>
            <span class="stat-value">{{ knowledge.state.overview?.indexed_document_count || 0 }}</span>
          </div>
        </div>

        <!-- 统计卡片 3：已使用空间 -->
        <div class="stat-card bounce">
          <div class="stat-icon-wrapper">
            <div class="stat-icon" style="color: #6366f1; border-color: rgba(99, 102, 241, 0.4);">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path></svg>
            </div>
            <span class="stat-badge active" style="background: rgba(99, 102, 241, 0.1); color: #6366f1;">容量</span>
          </div>
          <div class="stat-details">
            <span class="stat-title">已使用空间</span>
            <span class="stat-value" style="font-size: 1.5rem; margin-top: 8px;">{{ knowledge.state.overview?.total_file_size_label || "0 B" }}</span>
          </div>
        </div>

        <!-- 统计卡片 4：系统负载 -->
        <div class="stat-card bounce" style="cursor: pointer" @click="showReindexConfirm = true">
          <div class="stat-icon-wrapper">
            <div class="stat-icon" :style="knowledge.state.reindexing ? 'color: #3b82f6; animation: spin 2s linear infinite;' : 'color: #3b82f6; border-color: rgba(59, 130, 246, 0.4);'">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
            </div>
            <span class="stat-badge active" style="transition: all 0.2s" :style="knowledge.state.reindexing ? 'background: #3b82f6; color: white' : ''">操作</span>
          </div>
          <div class="stat-details">
            <span class="stat-title">维护操作</span>
            <span class="stat-value" style="font-size: 1.5rem; margin-top: 8px;">{{ knowledge.state.reindexing ? "正在刷新..." : "刷新全局索引" }}</span>
          </div>
        </div>

       
      </div>

      <!-- 文档列表区域 -->
      <section class="knowledge-inventory-container">
        <div class="inventory-header">
          <h2>文档检索及管理</h2>
          <div class="inventory-tabs">
            <button class="inventory-tab active">全部</button>
            <button class="inventory-tab" v-if="knowledge.state.summary?.processing_count">处理中 ({{ knowledge.state.summary.processing_count }})</button>
          </div>
        </div>

        <div v-if="knowledge.state.loading" style="display:flex; justify-content: center; padding: 60px;">
           <span style="color: var(--text-soft)">正在加载库目...</span>
        </div>

        <div v-else-if="knowledge.state.documents.length === 0" style="display:flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px; gap: 16px;">
           <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--text-soft)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="opacity: 0.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><line x1="12" y1="18" x2="12" y2="12"></line><line x1="9" y1="15" x2="15" y2="15"></line></svg>
           <span style="color: var(--text-soft)">还没有知识库文档，请在上方上传</span>
        </div>

        <!-- 表格内容 -->
        <div class="inventory-table" v-else>
          <div class="inventory-table-header">
            <div>档案名称</div>
            <div>文件大小</div>
            <div>数据标识</div>
            <div>状态</div>
            <div style="text-align: right">操作时间</div>
            <div style="text-align: right">操作</div>
          </div>

          <ul class="inventory-list">
            <li v-for="item in knowledge.state.documents" :key="item.document_id" class="inventory-row bounce">
              <div class="doc-name-cell">
                <div class="doc-icon" :class="getFileTypeClass(item.file_name)">
                  {{ fileExtension(item.file_name) || 'TXT' }}
                </div>
                <div class="doc-meta" style="max-width: 250px;">
                  <strong style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block;">{{ displayFileName(item) }}</strong>
                  <span v-if="item.status === 'ready'" style="color: #10b981">{{ item.chunk_count ? `${item.chunk_count} 个数据块` : '已入库' }}</span>
                  <span v-else-if="item.status === 'failed'" style="color: #ef4444; max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block;" :title="item.error_message">{{ item.error_message || '处理错误' }}</span>
                  <span v-else>{{ progressLabel(item) }}</span>
                </div>
              </div>
              
              <div style="color: var(--text-soft); font-size: 0.9rem;">
                {{ formatBytes(item.file_size_bytes) }}
              </div>

              <div>
                <span class="type-badge">{{ getDocTypeLabel(item.file_name) }}</span>
              </div>
              
              <div>
                <div class="status-cell">
                   <span class="status-dot" :class="item.status"></span>
                   {{ statusLabel(item.status) }}
                 </div>
              </div>
              
              <div class="date-cell" style="text-align: right">
                {{ formatTimestampShort(item.updated_at) }}
              </div>
              
              <div class="actions-cell">
                <button 
                  v-if="item.status === 'failed'"
                  class="icon-btn bounce" 
                  title="重试"
                  :disabled="knowledge.state.retryingDocumentId === item.document_id"
                  @click="handleRetry(item.document_id)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
                </button>
                <button class="icon-btn danger bounce" @click="handleDelete(item.document_id)" title="删除">
                  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                </button>
              </div>
            </li>
          </ul>
        </div>

        <!-- 底部与分页 (预留结构) -->
        <div class="inventory-footer" v-if="knowledge.state.documents.length > 0">
          <div class="pagination-info">
            总共 {{ knowledge.state.summary?.document_count || 0 }} 项档案
          </div>
          <div class="pagination-controls">
            <button class="page-btn" disabled>上一页</button>
            <button class="page-number active">1</button>
            <button class="page-btn" disabled>下一页</button>
          </div>
        </div>
      </section>
    </template>

    <!-- 弹窗 -->
    <Teleport to="body">
      <transition name="modal-bounce">
        <div v-if="showReindexConfirm" class="dialog-backdrop" @click.self="showReindexConfirm = false" style="background: rgba(0,0,0,0.4); position: fixed; inset: 0; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 9999; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(8px);">
          <section class="dialog-card" style="background: var(--bg-surface-elevated-strong); border: 1px solid var(--border-soft); padding: 32px; border-radius: 24px; max-width: 400px; box-shadow: 0 24px 48px rgba(0,0,0,0.12);">
            <div class="dialog-header" style="margin-bottom: 24px;">
              <p style="color: var(--text-soft); font-size: 0.85rem; font-weight: 600; text-transform: uppercase; margin: 0 0 8px 0;">确认操作</p>
              <h2 style="margin: 0; font-size: 1.5rem;">刷新知识库索引</h2>
            </div>
            <p style="color: var(--text-soft); line-height: 1.5; margin-bottom: 32px;">这会重新处理全部文档索引，期间可能耗时较长。确认继续吗？</p>
            <div class="dialog-actions" style="display: flex; justify-content: flex-end; gap: 12px;">
              <button class="ghost-button" type="button" @click="showReindexConfirm = false" style="padding: 8px 16px; border-radius: 12px; cursor: pointer;">取消</button>
              <button class="primary-button" type="button" @click="handleReindex" style="padding: 8px 24px; border-radius: 12px; cursor: pointer;">确认刷新</button>
            </div>
          </section>
        </div>
      </transition>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { useAuth } from "../composables/useAuth";
import { useKnowledgeBase } from "../composables/useKnowledgeBase";
import '../styles/knowledge.css'

const auth = useAuth();
const knowledge = useKnowledgeBase();
const fileInput = ref(null);
const selectedFile = ref(null);
const canManage = computed(() => auth.state.capabilities.can_manage_knowledge_base);
const toast = reactive({
  message: "",
  tone: "success"
});
const showReindexConfirm = ref(false);

let toastTimer = null;

watch(
  canManage,
  async (allowed) => {
    if (!allowed) {
      return;
    }
    try {
      await knowledge.refresh();
    } catch (_error) {}
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  clearToastTimer();
  knowledge.dispose?.();
});

watch(
  () => knowledge.state.info,
  (message) => {
    if (message) {
      showToast(message, "success");
    }
  }
);

watch(
  () => knowledge.state.error,
  (message) => {
    if (message) {
      showToast(message, "error");
    }
  }
);

function clearToastTimer() {
  if (toastTimer) {
    window.clearTimeout(toastTimer);
    toastTimer = null;
  }
}

function showToast(message, tone) {
  toast.message = message;
  toast.tone = tone;
  clearToastTimer();
  toastTimer = window.setTimeout(() => {
    toast.message = "";
    knowledge.clearFeedback?.();
    toastTimer = null;
  }, 2600);
}

function onFileChange(event) {
  selectedFile.value = event.target.files?.[0] || null;
}

function openFilePicker() {
  fileInput.value?.click();
}

async function handleUploadAction() {
  if (!selectedFile.value) {
    openFilePicker();
    return;
  }
  await handleUpload();
}

async function handleUpload() {
  if (!selectedFile.value) {
    return;
  }
  try {
    await knowledge.upload(selectedFile.value);
    selectedFile.value = null;
    if (fileInput.value) {
      fileInput.value.value = "";
    }
  } catch (_error) {}
}

async function handleDelete(documentId) {
  if (confirm('确认删除此文档？')) {
    try {
      await knowledge.remove(documentId);
    } catch (_error) {}
  }
}

async function handleRetry(documentId) {
  try {
    await knowledge.retry(documentId);
  } catch (_error) {}
}

async function handleReindex() {
  showReindexConfirm.value = false;
  try {
    await knowledge.reindex();
  } catch (_error) {}
}

function formatTimestampShort(value) {
  if (!value) {
    return "刚刚";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "刚刚";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function statusLabel(status) {
  if (status === "pending") {
    return "排队中";
  }
  if (status === "ready") {
    return "已就绪";
  }
  if (status === "processing") {
    return "处理中";
  }
  if (status === "failed") {
    return "解析失败";
  }
  return "待处理";
}

function fileExtension(fileName) {
  if (!fileName || !fileName.includes(".")) {
    return "TXT";
  }
  return fileName.split(".").pop().toUpperCase();
}

function getFileTypeClass(fileName) {
  const ext = fileExtension(fileName).toLowerCase()
  if (ext === 'pdf') return 'pdf'
  if (ext === 'md') return 'md'
  return 'txt'
}

function getDocTypeLabel(fileName) {
  const ext = fileExtension(fileName).toLowerCase()
  if (ext === 'pdf') return 'PDF扫描件'
  if (ext === 'md') return 'Markdown文件'
  return '通用文本'
}

function displayFileName(item) {
  const fileName = item?.file_name || "";
  if (fileName.includes(".")) {
    return fileName.slice(0, fileName.lastIndexOf(".")) || item?.title || fileName;
  }
  return fileName || item?.title || "";
}

function progressLabel(item) {
  if (!item) {
    return "";
  }
  if (item.status === "ready") {
    return "100%";
  }
  if (item.status === "failed") {
    return item.status_detail || "处理出错";
  }
  const percent = Number(item.progress_percent || 0);
  return `处理进度: ${Math.max(0, Math.min(99, percent))}%`;
}

function formatBytes(bytes) {
  if (bytes === undefined || bytes === null || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}
</script>

<style scoped>
@keyframes spin {
  100% {
    transform: rotate(360deg);
  }
}

/* 弹窗专用进入退出动画 */
.modal-bounce-enter-active,
.modal-bounce-leave-active {
  transition: opacity 0.3s ease;
}
.modal-bounce-enter-active .dialog-card {
  transition: transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.modal-bounce-leave-active .dialog-card {
  transition: transform 0.3s ease;
}

.modal-bounce-enter-from,
.modal-bounce-leave-to {
  opacity: 0;
}
.modal-bounce-enter-from .dialog-card,
.modal-bounce-leave-to .dialog-card {
  transform: scale(0.9) translateY(20px);
}
</style>
