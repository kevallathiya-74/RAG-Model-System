/**
 * Minimal Secure API Client for Secure Multi-Modal RAG System
 * 
 * Responsibilities:
 * - Communicates strictly via FastAPI endpoints
 * - Handles JWT bearer tokens without exposing credentials in logs
 * - Normalizes HTTP errors (400, 401, 403, 404, 413, 422, 429, 500)
 * - Triggers re-authentication cleanly on HTTP 401
 */

const TOKEN_KEY = 'secure_rag_jwt_token';
const USER_KEY = 'secure_rag_user_data';

let unauthorizedHandlers = [];

export function onUnauthorized(handler) {
  unauthorizedHandlers.push(handler);
  return () => {
    unauthorizedHandlers = unauthorizedHandlers.filter(h => h !== handler);
  };
}

export function notifyUnauthorized() {
  clearAuth();
  unauthorizedHandlers.forEach(handler => {
    try {
      handler();
    } catch {
      // safe no-op
    }
  });
}

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY) || null;
}

export function getStoredUser() {
  try {
    const data = localStorage.getItem(USER_KEY);
    return data ? JSON.parse(data) : null;
  } catch {
    return null;
  }
}

export function setAuth(token, user) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } else {
    localStorage.removeItem(USER_KEY);
  }
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

const API_BASE = 
  (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE_URL) ||
  (typeof process !== 'undefined' && process.env && process.env.VITE_API_BASE_URL) ||
  '';

export async function apiRequest(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const headers = new Headers(options.headers || {});

  const token = getAuthToken();
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  // Set Content-Type only if not FormData
  const isFormData = options.body instanceof FormData;
  if (!isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  let response;
  try {
    response = await fetch(url, {
      ...options,
      headers
    });
  } catch (err) {
    throw new Error('Network error: Unable to connect to the backend server. Please verify that FastAPI is running.');
  }

  if (response.status === 401) {
    notifyUnauthorized();
    const errorBody = await parseErrorResponse(response);
    const error = new Error(errorBody.detail || 'Session expired or invalid credentials. Please sign in again.');
    error.status = 401;
    throw error;
  }

  if (!response.ok) {
    const errorBody = await parseErrorResponse(response);
    const message = errorBody.detail || getStatusMessage(response.status);
    const error = new Error(message);
    error.status = response.status;
    error.detail = errorBody.detail;
    throw error;
  }

  // 204 No Content
  if (response.status === 204) {
    return null;
  }

  return response.json();
}

async function parseErrorResponse(response) {
  try {
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      return await response.json();
    }
    const text = await response.text();
    return { detail: text || null };
  } catch {
    return { detail: null };
  }
}

function getStatusMessage(status) {
  switch (status) {
    case 400:
      return 'Bad request. Please verify your input.';
    case 403:
      return 'Access denied. You do not have permission to view or perform this action.';
    case 404:
      return 'The requested resource was not found.';
    case 413:
      return 'File size exceeds maximum allowed limit.';
    case 422:
      return 'Validation error. Please check submitted data.';
    case 429:
      return 'Too many requests. Please wait a moment before trying again.';
    case 500:
      return 'Internal server error. Please try again later.';
    default:
      return `Server error (${status}).`;
  }
}

// API Methods
export async function loginApi(username, password) {
  const data = await apiRequest('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password })
  });
  setAuth(data.access_token, data.user);
  return data;
}

export async function chatApi(question) {
  return apiRequest('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ question })
  });
}

export async function getDocumentsApi() {
  return apiRequest('/api/documents', {
    method: 'GET'
  });
}

export async function uploadDocumentApi(formData) {
  return apiRequest('/api/documents/upload', {
    method: 'POST',
    body: formData
  });
}

export async function checkHealthApi() {
  return apiRequest('/api/health', {
    method: 'GET'
  });
}

// Administrative API Methods
export async function getAdminAuditLogsApi({ page = 1, pageSize = 20, action = null, result = null } = {}) {
  const params = new URLSearchParams();
  if (page) params.append('page', page);
  if (pageSize) params.append('page_size', pageSize);
  if (action) params.append('action', action);
  if (result) params.append('result', result);
  const qs = params.toString() ? `?${params.toString()}` : '';
  return apiRequest(`/api/admin/audit${qs}`, {
    method: 'GET'
  });
}

export async function getAdminUsersApi() {
  return apiRequest('/api/admin/users', {
    method: 'GET'
  });
}

export async function updateAdminUserStatusApi(userId, isActive) {
  return apiRequest(`/api/admin/users/${encodeURIComponent(userId)}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ is_active: isActive })
  });
}

export async function updateAdminUserRoleApi(userId, role) {
  return apiRequest(`/api/admin/users/${encodeURIComponent(userId)}/role`, {
    method: 'PATCH',
    body: JSON.stringify({ role })
  });
}

export async function getAdminDocumentsApi() {
  return apiRequest('/api/admin/documents', {
    method: 'GET'
  });
}

export async function grantDocumentPermissionApi(documentId, { targetRole, targetUserId }) {
  return apiRequest(`/api/admin/documents/${encodeURIComponent(documentId)}/permissions`, {
    method: 'POST',
    body: JSON.stringify({ target_role: targetRole || null, target_user_id: targetUserId || null })
  });
}

