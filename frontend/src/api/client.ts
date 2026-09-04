const BASE_URL = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || '';

export class ApiError extends Error {
  status: number;
  code?: string;
  detail?: string;
  requestId?: string;

  constructor(message: string, status: number, code?: string, detail?: string, requestId?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.requestId = requestId;
  }
}

export interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined | null>;
  timeoutMs?: number;
}

export async function apiClient<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { params, timeoutMs = 45000, headers, ...rest } = options;

  let url = endpoint.startsWith('http') ? endpoint : `${BASE_URL}${endpoint}`;

  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    });
    const queryString = searchParams.toString();
    if (queryString) {
      url += (url.includes('?') ? '&' : '?') + queryString;
    }
  }

  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);

  const clientRequestId = `req_${Math.random().toString(36).substring(2, 11)}`;

  try {
    const response = await fetch(url, {
      ...rest,
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': clientRequestId,
        ...headers,
      },
      signal: controller.signal,
    });

    clearTimeout(id);

    const serverRequestId = (typeof response.headers?.get === 'function' ? response.headers.get('X-Request-ID') : null) || clientRequestId;

    if (!response.ok) {
      let errorData: any = {};
      try {
        errorData = await response.json();
      } catch {
        errorData = { detail: response.statusText };
      }

      const message =
        errorData.error?.message ||
        errorData.detail ||
        `Request failed with status ${response.status}`;
      const code = errorData.error?.code || (response.status === 404 ? 'NOT_FOUND' : 'ERROR');

      throw new ApiError(
        message,
        response.status,
        code,
        errorData.detail || message,
        errorData.request_id || serverRequestId
      );
    }

    if (response.status === 204) {
      return {} as T;
    }

    return await response.json();
  } catch (err: any) {
    clearTimeout(id);
    if (err.name === 'AbortError') {
      throw new ApiError('Request timed out', 408, 'TIMEOUT', undefined, clientRequestId);
    }
    if (err instanceof ApiError) {
      throw err;
    }
    throw new ApiError(err.message || 'Network request failed', 0, 'NETWORK_ERROR', undefined, clientRequestId);
  }
}
