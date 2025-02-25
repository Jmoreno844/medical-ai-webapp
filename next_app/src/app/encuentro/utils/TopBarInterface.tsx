export interface TimerDisplayProps {
  duration: number;
}

export interface MicrophoneIconProps {
  isRecording: boolean;
}

export interface StartStopButtonProps {
  isRecording: boolean;
  onClick: () => void;
}

export interface DeleteButtonProps {
  onClick: () => void;
}
