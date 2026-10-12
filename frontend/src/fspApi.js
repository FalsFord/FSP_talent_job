import { api } from './api';

export const native = (path, method = 'GET', body) => api('/api/v1' + path, { method, body });
