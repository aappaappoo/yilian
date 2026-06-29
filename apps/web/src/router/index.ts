import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('../pages/index.vue'),
    },
    {
      path: '/chat',
      name: 'chat-default',
      component: () => import('../pages/chat.vue'),
    },
    {
      path: '/chat/:audience',
      name: 'chat',
      component: () => import('../pages/chat.vue'),
    },
    {
      path: '/chat/:audience/:conversationId',
      name: 'chat-conversation',
      component: () => import('../pages/chat.vue'),
    },
  ],
})

export default router
