/// <reference types="vite/client" />

/**
 * API root injected by vite.config.ts after validating VITE_API_BASE_URL.
 * It is an absolute HTTPS URL in production and `/api` in local test/dev when
 * no override is supplied.
 */
declare const __API_BASE_URL__: string;

interface ImportMetaEnv {
  /** Backend API root, e.g. https://api.example.com/api. Required in production. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  /** Google Tag Manager queue, initialized by the production container snippet. */
  dataLayer?: Record<string, unknown>[];
}
