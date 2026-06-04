import React from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/commons/components/ui/dropdown-menu";
import { useMicrophoneDevices } from "../hooks/audio/useMicrophoneDevices";
import { useTranscriptionContext } from "@/contexts/TranscriptionContext";

const DEFAULT_VALUE = "__default__";

/**
 * Settings dropdown — currently exposes microphone selection.
 */
const SettingsIcon: React.FC = () => {
  const {
    devices,
    selectedDeviceId,
    needsPermissionForLabels,
    refresh,
    selectDevice,
  } = useMicrophoneDevices();
  const { isRecording } = useTranscriptionContext();

  const handleOpenChange = (open: boolean) => {
    if (open) {
      void refresh();
    }
  };

  const value = selectedDeviceId ?? DEFAULT_VALUE;

  const handleValueChange = (next: string) => {
    selectDevice(next === DEFAULT_VALUE ? null : next);
  };

  const activeLabel =
    devices.find((device) => device.deviceId === selectedDeviceId)?.label ??
    "Predeterminado del sistema";

  return (
    <DropdownMenu onOpenChange={handleOpenChange}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Ajustes de micrófono"
          className="rounded p-1 text-gray-500 hover:text-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-500"
        >
          <img src="/settings.svg" alt="" width={24} height={24} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="min-w-[260px] border-2 border-gray-300 shadow-lg"
      >
        <DropdownMenuLabel>Micrófono</DropdownMenuLabel>
        <div className="px-2 pb-1 text-xs text-gray-500 truncate">
          Activo: {activeLabel}
        </div>
        <DropdownMenuSeparator />
        {isRecording && (
          <div className="px-2 py-1 text-xs text-amber-700">
            Detén la grabación para cambiar de micrófono.
          </div>
        )}
        {devices.length === 0 ? (
          <DropdownMenuItem
            onSelect={(event) => {
              event.preventDefault();
              void refresh();
            }}
          >
            {needsPermissionForLabels
              ? "Conceder permiso para listar micrófonos"
              : "Buscar micrófonos…"}
          </DropdownMenuItem>
        ) : (
          <DropdownMenuRadioGroup
            value={value}
            onValueChange={handleValueChange}
          >
            <DropdownMenuRadioItem
              value={DEFAULT_VALUE}
              disabled={isRecording}
            >
              Predeterminado del sistema
            </DropdownMenuRadioItem>
            {devices.map((device) => (
              <DropdownMenuRadioItem
                key={device.deviceId}
                value={device.deviceId}
                disabled={isRecording}
              >
                <span className="truncate">{device.label}</span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default SettingsIcon;
