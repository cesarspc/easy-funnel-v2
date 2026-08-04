/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base path (or full URL) for backend API calls. Defaults to "/api". */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
