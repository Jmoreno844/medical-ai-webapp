/// <reference types="vite/client" />

/** Optional globals set by ContentContext for cross-feature refresh (legacy bridge). */
interface Window {
  documentContentCache?: Map<number, string>;
  triggerEditorRefresh?: () => void;
}
