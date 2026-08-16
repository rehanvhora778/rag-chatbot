import api from './axios'

export const chatAPI = {
  listSessions:   (params)         => api.get('/api/chat/sessions/', { params }),
  createSession:  (data)           => api.post('/api/chat/sessions/', data),
  getSession:     (id)             => api.get(`/api/chat/sessions/${id}/`),
  updateSession:  (id, data)       => api.patch(`/api/chat/sessions/${id}/`, data),
  deleteSession:  (id)             => api.delete(`/api/chat/sessions/${id}/`),
  // `config` lets a request be cancelled mid-flight (see the Stop button).
  sendMessage:    (id, data, config) => api.post(`/api/chat/sessions/${id}/message/`, data, config),
  exportPDF:      (id)             => api.get(`/api/chat/sessions/${id}/export/`, { responseType: 'blob' }),
  search:         (params)         => api.get('/api/chat/search/', { params }),
  getConfig:      ()               => api.get('/api/chat/config/'),
}
