import api from './axios'

export const authAPI = {
  // Sign-up is two steps: `register` emails a code, `registerVerify` creates
  // the account once that code comes back.
  register:       (data)  => api.post('/api/auth/register/', data),
  registerVerify: (data)  => api.post('/api/auth/register/verify/', data),
  registerResend: (data)  => api.post('/api/auth/register/resend/', data),

  login:          (data)  => api.post('/api/auth/login/', data),
  adminLogin:     (data)  => api.post('/api/auth/admin/login/', data),
  google:         (data)  => api.post('/api/auth/google/', data),
  googleConfig:   ()      => api.get('/api/auth/google/config/'),

  // Forgotten password: request a code, trade the code for a ticket, then set
  // the new password with that ticket.
  resetRequest:   (data)  => api.post('/api/auth/password-reset/', data),
  resetVerify:    (data)  => api.post('/api/auth/password-reset/verify/', data),
  resetConfirm:   (data)  => api.post('/api/auth/password-reset/confirm/', data),

  logout:         (data)  => api.post('/api/auth/logout/', data),
  refreshToken:   (data)  => api.post('/api/auth/token/refresh/', data),
  getProfile:     ()      => api.get('/api/auth/profile/'),
  updateProfile:  (data)  => api.put('/api/auth/profile/', data),
  changePassword: (data)  => api.post('/api/auth/change-password/', data),
}
