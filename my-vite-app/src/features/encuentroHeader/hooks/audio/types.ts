/**
 * Interface for the return value of useVoiceRecorder hook
 */
export interface UseVoiceRecorderReturn {
    isRecording: boolean;
    isPaused: boolean;
    duration: number;
    audioBlob: Blob | null;
    transcriptionDocId?: number;
    audioExists: boolean;
    isCheckingAudio: boolean;
    startRecording: () => Promise<void>;
    stopRecording: () => void;
    pauseResumeRecording: () => void;
    deleteRecording: () => void;
}
