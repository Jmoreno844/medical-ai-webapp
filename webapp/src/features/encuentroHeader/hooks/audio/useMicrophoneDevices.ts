import { useCallback, useEffect, useState } from "react";
import { logger } from "@/lib/logger";

const SELECTED_MICROPHONE_STORAGE_KEY = "selectedMicrophoneDeviceId";

export const getStoredMicrophoneDeviceId = (): string | null => {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(SELECTED_MICROPHONE_STORAGE_KEY);
  } catch {
    return null;
  }
};

const setStoredMicrophoneDeviceId = (deviceId: string | null) => {
  if (typeof window === "undefined") return;
  try {
    if (deviceId) {
      window.localStorage.setItem(SELECTED_MICROPHONE_STORAGE_KEY, deviceId);
    } else {
      window.localStorage.removeItem(SELECTED_MICROPHONE_STORAGE_KEY);
    }
  } catch {
    /* ignore storage failures */
  }
};

export type MicrophoneDevice = {
  deviceId: string;
  label: string;
};

type UseMicrophoneDevicesReturn = {
  devices: MicrophoneDevice[];
  selectedDeviceId: string | null;
  needsPermissionForLabels: boolean;
  refresh: () => Promise<void>;
  selectDevice: (deviceId: string | null) => void;
};

export const useMicrophoneDevices = (): UseMicrophoneDevicesReturn => {
  const [devices, setDevices] = useState<MicrophoneDevice[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(
    () => getStoredMicrophoneDeviceId(),
  );
  const [needsPermissionForLabels, setNeedsPermissionForLabels] =
    useState(false);

  const enumerate = useCallback(async () => {
    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices?.enumerateDevices
    ) {
      setDevices([]);
      return;
    }

    try {
      const allDevices = await navigator.mediaDevices.enumerateDevices();
      const audioInputs = allDevices.filter(
        (device) => device.kind === "audioinput" && device.deviceId,
      );
      const mapped: MicrophoneDevice[] = audioInputs.map((device, index) => ({
        deviceId: device.deviceId,
        label: device.label || `Micrófono ${index + 1}`,
      }));
      setDevices(mapped);
      setNeedsPermissionForLabels(
        audioInputs.length > 0 && audioInputs.every((d) => !d.label),
      );
    } catch (error) {
      logger.warn("[MIC_DEVICES] Failed to enumerate microphones:", error);
      setDevices([]);
    }
  }, []);

  const refresh = useCallback(async () => {
    if (
      typeof navigator !== "undefined" &&
      navigator.mediaDevices?.getUserMedia
    ) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
        });
        stream.getTracks().forEach((track) => track.stop());
        setNeedsPermissionForLabels(false);
      } catch (error) {
        logger.warn("[MIC_DEVICES] Permission request failed:", error);
      }
    }
    await enumerate();
  }, [enumerate]);

  useEffect(() => {
    void enumerate();

    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices?.addEventListener
    ) {
      return;
    }

    const handleChange = () => {
      void enumerate();
    };
    navigator.mediaDevices.addEventListener("devicechange", handleChange);
    return () => {
      navigator.mediaDevices.removeEventListener("devicechange", handleChange);
    };
  }, [enumerate]);

  useEffect(() => {
    if (!selectedDeviceId || devices.length === 0) return;
    const stillAvailable = devices.some(
      (device) => device.deviceId === selectedDeviceId,
    );
    if (!stillAvailable) {
      setSelectedDeviceId(null);
      setStoredMicrophoneDeviceId(null);
    }
  }, [devices, selectedDeviceId]);

  const selectDevice = useCallback((deviceId: string | null) => {
    setSelectedDeviceId(deviceId);
    setStoredMicrophoneDeviceId(deviceId);
  }, []);

  return {
    devices,
    selectedDeviceId,
    needsPermissionForLabels,
    refresh,
    selectDevice,
  };
};
