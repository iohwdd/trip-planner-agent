<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import AuthDialog from "./components/AuthDialog.vue";
import { useAuth } from "./composables/useAuth";

const route = useRoute();
const auth = useAuth();
const sidebarPreference = ref(null);

// 定义每个导航项的 SVG 图标
const navItems = computed(() => [
  { 
    to: "/", 
    label: "智能助手", 
    shortLabel: "助",
    icon: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path><circle cx="9" cy="10" r="1"></circle><circle cx="15" cy="10" r="1"></circle></svg>`
  },
  { 
    to: "/workbench", 
    label: "工作台", 
    shortLabel: "台",
    icon: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="9" y1="21" x2="9" y2="9"></line></svg>`
  },
  ...(auth.state.capabilities.can_manage_knowledge_base
    ? [{ 
        to: "/knowledge", 
        label: "知识库", 
        shortLabel: "库",
        icon: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>`
      }]
    : []),
  { 
    to: "/sessions", 
    label: "会话", 
    shortLabel: "话",
    icon: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>`
  },
  { 
    to: "/plans", 
    label: "方案", 
    shortLabel: "案",
    icon: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"></polygon><line x1="9" y1="3" x2="9" y2="18"></line><line x1="15" y1="6" x2="15" y2="21"></line></svg>`
  }
]);

const sidebarCollapsed = computed(() => sidebarPreference.value ?? false);
const sidebarToggleLabel = computed(() => (sidebarCollapsed.value ? "展开导" : "收起导"));

onMounted(async () => {
  await auth.restore();
});

async function handleLogout() {
  await auth.logout();
}

function toggleSidebar() {
  sidebarPreference.value = !sidebarCollapsed.value;
}
</script>

<template>
  <div class="app-shell app-shell-product">
    <header class="app-header app-header-compact app-header-minimal">
      <div class="app-brand">
        <div class="app-logo">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle></svg>
        </div>
        <div>
          <p class="eyebrow">Travel Planner</p>
          <strong>Trip Agent</strong>
        </div>
      </div>

      <div class="user-console user-console-minimal">
        <button
          v-if="!auth.state.authenticated"
          class="primary-button"
          type="button"
          @click="auth.openDialog('登录后可保存方案并管理会话。')"
        >
          账号登录
        </button>
        <div v-else class="user-menu user-menu-minimal">
          <div class="user-summary">
            <strong>{{ auth.userLabel }}</strong>
            <span>已登录</span>
          </div>
          <RouterLink class="ghost-button compact-button" to="/profile">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
          </RouterLink>
          <button class="ghost-button compact-button" type="button" @click="handleLogout" title="退出登录">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
          </button>
        </div>
      </div>
    </header>

    <div class="app-layout" :data-sidebar-collapsed="sidebarCollapsed ? 'true' : 'false'">
      <aside class="app-sidebar" :data-collapsed="sidebarCollapsed ? 'true' : 'false'">
        <div class="sidebar-header">
          <strong>导 航</strong>
          <button class="ghost-button compact-button toggle-sidebar-btn" type="button" @click="toggleSidebar" :title="sidebarToggleLabel">
            <svg v-if="!sidebarCollapsed" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
          </button>
        </div>

        <nav class="sidebar-nav" aria-label="主导航">
          <RouterLink
            v-for="item in navItems"
            :key="item.to"
            :to="item.to"
            class="nav-card fancy-nav-card"
            :class="{ 'is-active': route.path === item.to || (item.to !== '/' && route.path.startsWith(`${item.to}/`)) }"
            :data-collapsed="sidebarCollapsed ? 'true' : 'false'"
          >
            <div class="nav-icon-container" v-html="item.icon"></div>
            <span class="nav-label">{{ item.label }}</span>
            <div class="nav-active-indicator"></div>
          </RouterLink>
        </nav>
        
        <div class="sidebar-footer">
          <div class="weather-widget" v-if="!sidebarCollapsed">
             <div class="weather-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffb74d" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>
             </div>
             <div class="weather-info">
               <span class="weather-temp">24°C</span>
               <span class="weather-desc">开启美好旅程</span>
             </div>
          </div>
        </div>
      </aside>

      <section class="app-content">
        <RouterView />
      </section>
    </div>

    <AuthDialog />
  </div>
</template>

<style scoped>
/* App Brand */
.app-brand {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.app-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: var(--gradient-primary);
  color: white;
  border-radius: 12px;
  box-shadow: var(--shadow-soft);
}

.toggle-sidebar-btn {
  padding: 8px !important;
  width: 34px !important;
  height: 34px !important;
  display: flex !important;
  align-items: center;
  justify-content: center;
}

/* 导航卡片美化 */
.fancy-nav-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4) var(--space-5);
  border-radius: 16px;
  background: transparent !important;
  border: 1px solid transparent !important;
  color: var(--text-soft);
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  box-shadow: none !important;
  margin-bottom: 4px;
}

.fancy-nav-card:hover {
  background: rgba(255, 255, 255, 0.4) !important;
  transform: translateX(4px);
  color: var(--primary-deep);
}

.fancy-nav-card.is-active {
  background: var(--bg-surface-elevated-strong) !important;
  color: var(--primary-deep);
  box-shadow: 0 4px 12px rgba(74, 180, 255, 0.1) !important;
  border: 1px solid var(--border-strong) !important;
}

.nav-icon-container {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.5);
  transition: all 0.3s ease;
  flex-shrink: 0;
}

.fancy-nav-card.is-active .nav-icon-container {
  background: var(--gradient-primary);
  color: white;
  box-shadow: 0 4px 10px rgba(74, 180, 255, 0.3);
}

.nav-label {
  font-weight: 600;
  font-size: 0.95rem;
  transition: all 0.2s ease;
}

.nav-active-indicator {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 0;
  background: var(--primary);
  border-radius: 0 4px 4px 0;
  transition: height 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.fancy-nav-card.is-active .nav-active-indicator {
  height: 24px;
}

/* Sidebar 折叠状态适配 */
.app-sidebar[data-collapsed="true"] .fancy-nav-card {
  padding: var(--space-3);
  justify-content: center;
}

.app-sidebar[data-collapsed="true"] .fancy-nav-card:hover {
  transform: translateY(-2px);
}

.app-sidebar[data-collapsed="true"] .nav-label {
  display: none;
}

/* 侧边栏底部天气小组件 - 增加旅游氛围 */
.sidebar-footer {
  margin-top: auto;
  padding-top: var(--space-6);
}

.weather-widget {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.8), rgba(240, 248, 255, 0.6));
  border-radius: 16px;
  border: 1px solid var(--border-strong);
  box-shadow: var(--shadow-soft);
}

.weather-info {
  display: flex;
  flex-direction: column;
}

.weather-temp {
  font-weight: 700;
  color: var(--text-strong);
  font-size: 0.95rem;
}

.weather-desc {
  font-size: 0.75rem;
  color: var(--text-soft);
}
</style>
