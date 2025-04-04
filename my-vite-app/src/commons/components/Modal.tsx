import React from "react";

interface ModalProps {
  /** Whether the modal is visible */
  isOpen: boolean;
  /** Function to close the modal */
  onClose: () => void;
  /** Modal title */
  title: string;
  /** Modal content */
  children: React.ReactNode;
  /** Primary action button text */
  primaryButtonText?: string;
  /** Primary action function */
  onPrimaryAction?: () => void;
  /** Secondary action button text */
  secondaryButtonText?: string;
  /** Whether the primary button should be destructive (red) */
  isPrimaryDestructive?: boolean;
  isPrimaryDisabled?: boolean;
}

/**
 * Generic modal component with customizable buttons
 */
const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  primaryButtonText = "Confirm",
  onPrimaryAction,
  secondaryButtonText = "Cancel",
  isPrimaryDestructive = false,
}) => {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      data-testid="modal-overlay"
    >
      <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
        {/* Modal header */}
        <h2 className="text-xl font-semibold mb-4">{title}</h2>

        {/* Modal content */}
        <div className="mb-6">{children}</div>

        {/* Modal actions */}
        <div className="flex justify-end space-x-3">
          <button
            className="px-4 py-2 bg-gray-200 text-gray-800 rounded hover:bg-gray-300"
            onClick={onClose}
          >
            {secondaryButtonText}
          </button>
          {onPrimaryAction && (
            <button
              className={`px-4 py-2 rounded text-white ${
                isPrimaryDestructive
                  ? "bg-red-500 hover:bg-red-600"
                  : "bg-purple-500 hover:bg-purple-600"
              }`}
              onClick={onPrimaryAction}
            >
              {primaryButtonText}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default Modal;
