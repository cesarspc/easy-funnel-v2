/**
 * Centralized API transport. All backend calls go through `apiClient` so
 * URL construction, auth cookies, headers, and error mapping stay in one
 * place. Individual feature modules add typed helpers on top of this.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly fieldErrors?: Record<string, string>;

  constructor(status: number, message: string, fieldErrors?: Record<string, string>) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

/** API root compiled by Vite from VITE_API_BASE_URL. */
export const API_BASE_URL = __API_BASE_URL__;

export function buildApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

async function fetchApi(path: string, options: RequestInit = {}): Promise<Response> {
  // `FormData` bodies must keep the browser-generated multipart boundary, so
  // the JSON content type is only applied to non-multipart requests.
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const response = await fetch(buildApiUrl(path), {
    ...options,
    credentials: "include",
    headers: {
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });

  if (!response.ok) {
    let message = "Request failed";
    let fieldErrors: Record<string, string> | undefined;
    try {
      const body: unknown = await response.json();
      if (body && typeof body === "object" && "detail" in body) {
        const detail = (body as { detail: unknown }).detail;
        if (typeof detail === "string") {
          message = detail;
        } else if (
          detail &&
          typeof detail === "object" &&
          "field" in detail &&
          "message" in detail
        ) {
          // FastAPI single-field validation errors: detail: {field, message}
          const { field, message: fieldMessage } = detail as {
            field: string;
            message: string;
          };
          message = fieldMessage;
          fieldErrors = { [field]: fieldMessage };
        }
      }
      if (body && typeof body === "object" && "field_errors" in body) {
        fieldErrors = (body as { field_errors: Record<string, string> }).field_errors;
      }
    } catch {
      // Response had no JSON body; fall back to the generic message.
    }
    throw new ApiError(response.status, message, fieldErrors);
  }

  return response;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetchApi(path, options);

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  getBlob: async (path: string): Promise<Blob> => {
    const response = await fetchApi(path, { method: "GET" });
    return response.blob();
  },
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", body: form }),
};
