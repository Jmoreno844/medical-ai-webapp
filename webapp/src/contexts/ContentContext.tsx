import React, {
  createContext,
  useContext,
  useEffect,
  useCallback,
  useMemo,
  useState,
} from "react";
import { useDocumentContext } from "./DocumentContext";
import { logger } from "@/lib/logger";
import { useDocumentDraftStore } from "@/workspace/stores/documentDraftStore";
import { useDocumentSnapshotStore } from "@/workspace/stores/documentSnapshotStore";

type ContentContextType = {
  documentContent: string;
  isLoadingContent: boolean;
  fetchError: string | null;
  contentLoadedSuccessfully: boolean;
  documentContentCache: Map<number, string>;
  editorRefreshTrigger: number;
  loadedDocumentIds: number[];

  fetchDocumentContent: (
    docId: number,
    forceRefresh?: boolean
  ) => Promise<string | null>;
  reloadContent: (forceRefresh?: boolean) => Promise<void>;
  triggerEditorRefresh: () => void;
  saveContent: (docId: number, content: string) => Promise<boolean>;
  updateDocumentContent: (docId: number, content: string) => void; // New function
};

const ContentContext = createContext<ContentContextType | undefined>(undefined);

type ContentWindowBridge = Window & {
  documentContentCache?: Map<number, string>;
  triggerEditorRefresh?: () => void;
};

export function ContentProvider({ children }: { children: React.ReactNode }) {
  const { activeDocumentId, saveDocument } = useDocumentContext();
  const [editorRefreshTrigger, setEditorRefreshTrigger] = useState<number>(0);

  const snapshotsByDocumentId = useDocumentSnapshotStore(
    (state) => state.snapshotsByDocumentId
  );
  const isLoadingByDocumentId = useDocumentSnapshotStore(
    (state) => state.isLoadingByDocumentId
  );
  const fetchErrorByDocumentId = useDocumentSnapshotStore(
    (state) => state.fetchErrorByDocumentId
  );
  const loadedDocumentIds = useDocumentSnapshotStore(
    (state) => state.loadedDocumentIds
  );
  const getSnapshot = useDocumentSnapshotStore((state) => state.getSnapshot);
  const setSnapshot = useDocumentSnapshotStore((state) => state.setSnapshot);
  const fetchSnapshot = useDocumentSnapshotStore((state) => state.fetchSnapshot);

  const draftsByDocumentId = useDocumentDraftStore(
    (state) => state.draftsByDocumentId
  );
  const getDraft = useDocumentDraftStore((state) => state.getDraft);
  const setDraftContent = useDocumentDraftStore((state) => state.setDraftContent);
  const resetDraftFromSnapshot = useDocumentDraftStore(
    (state) => state.resetDraftFromSnapshot
  );
  const markDraftClean = useDocumentDraftStore((state) => state.markDraftClean);

  const triggerEditorRefresh = useCallback(() => {
    setEditorRefreshTrigger((prev) => prev + 1);
  }, []);

  const activeDocumentKey = activeDocumentId ? String(activeDocumentId) : null;
  const activeDraft = activeDocumentKey ? getDraft(activeDocumentKey) : null;
  const activeSnapshot = activeDocumentKey ? getSnapshot(activeDocumentKey) : null;

  const documentContent = activeDraft?.localUnsavedContent ?? activeSnapshot?.contentMarkdown ?? "";
  const isLoadingContent = activeDocumentKey
    ? Boolean(isLoadingByDocumentId[activeDocumentKey])
    : false;
  const fetchError = activeDocumentKey
    ? fetchErrorByDocumentId[activeDocumentKey] ?? null
    : null;
  const contentLoadedSuccessfully = activeDocumentKey
    ? loadedDocumentIds.includes(activeDocumentKey) ||
      activeDraft?.localUnsavedContent !== undefined ||
      Boolean(activeSnapshot)
    : false;

  const documentContentCache = useMemo(() => {
    const cache = new Map<number, string>();

    Object.entries(snapshotsByDocumentId).forEach(([documentId, snapshot]) => {
      if (snapshot) {
        cache.set(Number(documentId), snapshot.contentMarkdown);
      }
    });

    Object.entries(draftsByDocumentId).forEach(([documentId, draft]) => {
      if (draft?.localUnsavedContent !== null && draft?.localUnsavedContent !== undefined) {
        cache.set(Number(documentId), draft.localUnsavedContent);
      }
    });

    return cache;
  }, [draftsByDocumentId, snapshotsByDocumentId]);

  useEffect(() => {
    const contentWindow = window as ContentWindowBridge;
    contentWindow.documentContentCache = documentContentCache;
    contentWindow.triggerEditorRefresh = triggerEditorRefresh;
    return () => {
      delete contentWindow.documentContentCache;
      delete contentWindow.triggerEditorRefresh;
    };
  }, [documentContentCache, triggerEditorRefresh]);

  const fetchDocumentContent = useCallback(
    async (docId: number, forceRefresh = false): Promise<string | null> => {
      const documentKey = String(docId);
      const cachedSnapshot = getSnapshot(documentKey);
      const existingDraft = getDraft(documentKey);

      logger.debug(
        `[DOC_FETCH] Request for document ${docId}, forceRefresh: ${forceRefresh}`
      );

      if (cachedSnapshot && !forceRefresh) {
        if (!existingDraft) {
          resetDraftFromSnapshot(documentKey);
        }

        return cachedSnapshot.contentMarkdown;
      }

      const snapshot = await fetchSnapshot(documentKey, forceRefresh);
      if (!snapshot) {
        return null;
      }

      if (!existingDraft || !existingDraft.isDirty) {
        resetDraftFromSnapshot(documentKey);
      }

      return snapshot.contentMarkdown;
    },
    [fetchSnapshot, getDraft, getSnapshot, resetDraftFromSnapshot]
  );

  const saveContent = useCallback(
    async (docId: number, content: string): Promise<boolean> => {
      const normalizeBreaks = (text: string): string => {
        return text
          .replace(/\r\n/g, "\n")
          .replace(/\r/g, "\n")
          .replace(/\n\n+/g, "\n\n") // Collapse multiple newlines to max two
          .replace(/[ \t]+/g, " ") // Collapse multiple spaces
          .trim();
      };

      try {
        const documentKey = String(docId);
        const snapshot = getSnapshot(documentKey);
        const cachedContent = snapshot?.contentMarkdown;

        if (
          cachedContent &&
          normalizeBreaks(cachedContent) === normalizeBreaks(content)
        ) {
          setDraftContent(documentKey, content);
          resetDraftFromSnapshot(documentKey);
          markDraftClean(documentKey);
          return true;
        }

        setDraftContent(documentKey, content);
        const success = await saveDocument(docId, content);

        if (success) {
          setSnapshot(documentKey, content, snapshot?.version ?? 1);
          resetDraftFromSnapshot(documentKey);
          markDraftClean(documentKey);
        }

        return success;
      } catch (error) {
        logger.error("Error in saveContent:", error);
        return false;
      }
    },
    [
      getSnapshot,
      markDraftClean,
      resetDraftFromSnapshot,
      saveDocument,
      setDraftContent,
      setSnapshot,
    ]
  );

  const reloadContent = useCallback(
    async (forceRefresh: boolean = false): Promise<void> => {
      if (activeDocumentId) {
        logger.debug(
          `[RELOAD_CONTENT] Document ${activeDocumentId}, forceRefresh: ${forceRefresh}`
        );
        const documentKey = String(activeDocumentId);
        const existingDraft = getDraft(documentKey);
        const content = await fetchDocumentContent(activeDocumentId, forceRefresh);

        if (content !== null && (!existingDraft || !existingDraft.isDirty)) {
          resetDraftFromSnapshot(documentKey);
        }
      }
    },
    [activeDocumentId, fetchDocumentContent, getDraft, resetDraftFromSnapshot]
  );

  useEffect(() => {
    if (activeDocumentId) {
      void fetchDocumentContent(activeDocumentId);
    }
  }, [activeDocumentId, fetchDocumentContent]);

  useEffect(() => {
    return () => {
      logger.debug(`[CACHE_CLEAR 🧹] ContentContext unmounting, clearing cache`);
    };
  }, []);

  const updateDocumentContent = useCallback(
    (docId: number, content: string) => {
      const documentKey = String(docId);
      const existingDraft = getDraft(documentKey);
      const snapshot = getSnapshot(documentKey);

      setSnapshot(documentKey, content, snapshot?.version ?? 1);

      if (!existingDraft || !existingDraft.isDirty) {
        resetDraftFromSnapshot(documentKey);
      }
    },
    [getDraft, getSnapshot, resetDraftFromSnapshot, setSnapshot]
  );

  const value: ContentContextType = {
    documentContent,
    isLoadingContent,
    fetchError,
    contentLoadedSuccessfully,
    documentContentCache,
    editorRefreshTrigger,
    loadedDocumentIds: loadedDocumentIds.map((documentId) => Number(documentId)),
    fetchDocumentContent,
    reloadContent,
    triggerEditorRefresh,
    saveContent,
    updateDocumentContent,
  };

  return (
    <ContentContext.Provider value={value}>{children}</ContentContext.Provider>
  );
}

// Custom hook
export function useContentContext() {
  const context = useContext(ContentContext);
  if (context === undefined) {
    throw new Error("useContentContext must be used within a ContentProvider");
  }
  return context;
}
