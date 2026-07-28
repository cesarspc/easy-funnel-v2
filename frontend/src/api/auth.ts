/** Admin authentication API client (Requirement 7.1-7.15). */

import { apiClient } from "./client";

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  authenticated: boolean;
  role: string;
}

export interface SessionResponse {
  authenticated: boolean;
  role: string;
}

export const authApi = {
  /**
   * Authenticate and receive an httpOnly session cookie.
   * Throws ApiError(401) on invalid credentials, ApiError(429) when the
   * login rate limit is exceeded.
   */
  login: async (request: LoginRequest): Promise<LoginResponse> => {
    return apiClient.post<LoginResponse>("/auth/login", request);
  },

  /** Invalidate the current session. */
  logout: async (): Promise<void> => {
    await apiClient.post("/auth/logout");
  },

  /** Fetch current session state for guard hydration. Throws ApiError(401) when unauthenticated. */
  getSession: async (): Promise<SessionResponse> => {
    return apiClient.get<SessionResponse>("/auth/session");
  },
};
