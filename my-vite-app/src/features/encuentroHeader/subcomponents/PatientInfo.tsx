import React from "react";
import { PatientInfoProps } from "../utils/EncuentroHeaderInterface";

// Update the PatientInfoProps interface to include new props
export interface ExtendedPatientInfoProps extends PatientInfoProps {
  isPatientConnected?: boolean;
  onUnlink?: () => void;
  onDelete?: () => void;
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
}) => (
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
    <span className="text-xs text-gray-500">{encounterDate}</span>
  </div>
);

export default PatientInfo;
