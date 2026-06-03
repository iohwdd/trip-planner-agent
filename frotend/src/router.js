import { createRouter, createWebHistory } from "vue-router";
import AssistantPage from "./pages/AssistantPage.vue";
import KnowledgePage from "./pages/KnowledgePage.vue";
import WorkbenchPage from "./pages/WorkbenchPage.vue";
import SessionsPage from "./pages/SessionsPage.vue";
import PlansPage from "./pages/PlansPage.vue";
import PlanDetailPage from "./pages/PlanDetailPage.vue";
import ProfilePage from "./pages/ProfilePage.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "assistant",
      component: AssistantPage
    },
    {
      path: "/workbench",
      name: "workbench",
      component: WorkbenchPage
    },
    {
      path: "/knowledge",
      name: "knowledge",
      component: KnowledgePage
    },
    {
      path: "/sessions",
      name: "sessions",
      component: SessionsPage
    },
    {
      path: "/plans",
      name: "plans",
      component: PlansPage
    },
    {
      path: "/plans/:planId",
      name: "plan-detail",
      component: PlanDetailPage,
      props: true
    },
    {
      path: "/profile",
      name: "profile",
      component: ProfilePage
    }
  ]
});

export default router;
