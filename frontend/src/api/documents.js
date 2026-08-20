import api from './axios'

export const documentsAPI = {
  list:       (params) => api.get('/api/documents/', { params }),
  upload:     (formData, onUploadProgress) => api.post('/api/documents/', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress,
  }),
  get:        (id)     => api.get(`/api/documents/${id}/`),
  rename:     (id, original_filename) => api.patch(`/api/documents/${id}/`, { original_filename }),
  delete:     (id)     => api.delete(`/api/documents/${id}/`),
  getSummary: (id)     => api.get(`/api/documents/${id}/summary/`),
  regenSummary: (id)   => api.post(`/api/documents/${id}/summary/`),

  // One request for a whole batch, not one per document: the upload screen
  // polls this every couple of seconds while files ingest.
  status:      (ids)   => api.get('/api/documents/status/', {
    params: { ids: (Array.isArray(ids) ? ids : [ids]).join(',') },
  }),
  reprocess:   (id)    => api.post(`/api/documents/${id}/reprocess/`),
}
