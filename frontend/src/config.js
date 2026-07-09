// 后端地址集中在这里。部署换域名只改这一处(或设 VITE_API_BASE 环境变量),
// 不用满代码库改字面量。
const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

// WebSocket 地址由 API_BASE 推导:http→ws, https→wss
const WS_BASE = API_BASE.replace(/^http/, 'ws')

export { API_BASE, WS_BASE }
