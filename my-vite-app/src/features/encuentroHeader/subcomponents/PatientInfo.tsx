import React, { useState, useEffect, useCallback } from "react";
import { PatientInfoProps } from "../utils/EncuentroHeaderInterface";
import { DateTimePicker } from "@/commons/components/DateTimePicker";
import { debounce } from "lodash"; // You might need to install lodash if not already used

// Update the PatientInfoProps interface to include new props
export interface ExtendedPatientInfoProps extends PatientInfoProps {
  isPatientConnected?: boolean;
  onUnlink?: () => void;
  onDelete?: () => void;
  // Change onEditDate to take a Date parameter
  onUpdateDate?: (date: Date) => void;
  originalDateString?: string | null;
  isDateUpdating?: boolean;
}

/**
 * Displays patient or encounter information with edit and unlink buttons
 */
const PatientInfo: React.FC<ExtendedPatientInfoProps> = ({
  encounterName,
  encounterDate,
  onEdit,
  isPatientConnected = false,
  onUnlink,
  onDelete,
  onUpdateDate, // Changed prop
  originalDateString,
  isDateUpdating = false,
}) => {
  // Convert originalDateString to Date object and track it
  const [datePickerValue, setDatePickerValue] = useState<Date | undefined>(
    originalDateString ? new Date(originalDateString) : undefined
  );

  // State to control DateTimePicker visibility
  const [isDatePickerOpen, setIsDatePickerOpen] = useState(false);

  // Update datePickerValue when originalDateString changes
  useEffect(() => {
    if (originalDateString) {
      const newDate = new Date(originalDateString);
      // Check if it's a valid date before setting
      if (!isNaN(newDate.getTime())) {
        setDatePickerValue(newDate);
      }
    } else {
      setDatePickerValue(undefined);
    }
  }, [originalDateString]);

  // Debounce only the API call, not the UI update
  const debouncedUpdateDate = useCallback(
    debounce((date: Date) => {
      if (onUpdateDate) {
        onUpdateDate(date);
      }
    }, 800), // 800ms delay
    [onUpdateDate]
  );

  // Handle date change - update local state immediately but debounce API call
  const handleDateChange = (date: Date) => {
    // Update local state immediately
    setDatePickerValue(date);
    // Debounce the API call only
    debouncedUpdateDate(date);
  };

  // Clean up the debounce on unmount
  useEffect(() => {
    return () => {
      debouncedUpdateDate.cancel();
    };
  }, [debouncedUpdateDate]);

  return (
    <div className="flex flex-col">
      <div className="flex items-center space-x-2">
        <span className="font-medium" data-testid="encounter-name">
          {encounterName}
        </span>
        <button
          onClick={onEdit}
          className="p-1 rounded-full hover:bg-gray-200 transition-colors"
          aria-label="Edit patient"
          title="Editar paciente o encuentro"
          data-testid="edit-patient-button"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
            />
          </svg>
        </button>

        {/* Unlink button - only show when a patient is connected */}
        {isPatientConnected && onUnlink && (
          <button
            onClick={onUnlink}
            className="p-1 rounded-full hover:bg-gray-200 transition-colors"
            aria-label="Unlink patient"
            title="Desconectar paciente"
            data-testid="unlink-patient-button"
          >
            <img
              src="/chain.svg"
              alt="Unlink patient"
              width={16}
              height={16}
              className="w-4 h-4"
            />
          </button>
        )}

        {/* Delete encounter button */}
        {onDelete && (
          <button
            onClick={onDelete}
            className="p-1 rounded-full hover:bg-gray-200 transition-colors"
            aria-label="Delete encounter"
            title="Eliminar encuentro"
            data-testid="delete-encounter-button"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
            </svg>
          </button>
        )}
      </div>

      {/* Use DateTimePicker with controlled open state */}
      <div className="mt-2">
        {onUpdateDate ? (
          <div className="flex items-center">
            <DateTimePicker
              key={`date-picker-${originalDateString}`} // Force re-render when date changes
              value={datePickerValue}
              onChange={handleDateChange}
              isOpen={isDatePickerOpen}
              onOpenChange={setIsDatePickerOpen}
            />
            {isDateUpdating && (
              <div className="ml-2 inline-block animate-spin rounded-full h-3 w-3 border-t-2 border-b-2 border-purple-500"></div>
            )}
          </div>
        ) : (
          <div className="flex items-center text-sm text-black">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4 mr-1"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
            <span>{encounterDate}</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default PatientInfo;
