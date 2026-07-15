const API_BASE_URL = import.meta.env.VITE_ADMIN_API_URL || '/api/admin';

function getToken(): string | null {
  return localStorage.getItem('ai_portfolio_admin_token');
}

interface RequestOptions extends RequestInit {
  requireAuth?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { requireAuth = true, headers, ...rest } = options;

  const requestHeaders = new Headers({
    'Content-Type': 'application/json',
    Accept: 'application/json',
  });

  if (headers) {
    const initHeaders = new Headers(headers);
    initHeaders.forEach((value, key) => {
      requestHeaders.set(key, value);
    });
  }

  if (requireAuth) {
    const token = getToken();
    if (!token) {
      throw new Error('Authentication required');
    }
    requestHeaders.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: requestHeaders,
  });

  if (response.status === 403) {
    throw new Error('Access denied: invalid or missing admin token');
  }

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

export const apiClient = {
  get: <T,>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'GET' }),
  post: <T,>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, {
      ...options,
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),
  patch: <T,>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, {
      ...options,
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    }),
  delete: <T,>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'DELETE' }),
};

export function getDashboard() {
  return apiClient.get<{ workspace: string; status: string }>('/dashboard');
}

export function getKnowledgeBaseStatus() {
  return apiClient.get<{ workspace: string; status: string }>('/knowledge-base/status');
}

export function getLogs() {
  return apiClient.get<{ workspace: string; items: unknown[] }>('/logs');
}
