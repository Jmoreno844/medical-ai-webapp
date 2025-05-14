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
  primaryButtonVariant?: "default" | "purple";
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
  isPrimaryDisabled = false,
  primaryButtonVariant = "default",
}) => {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
      data-testid="modal-overlay"
    >
      <div className="bg-card text-card-foreground rounded-lg shadow-xl p-6 w-full max-w-md">
        {/* Modal header */}
        <h2 className="text-xl font-semibold mb-4">{title}</h2>

        {/* Modal content */}
        <div className="mb-6">{children}</div>

        {/* Modal actions */}
        <div className="flex justify-end space-x-3">
          <button
            className="px-4 py-2 bg-secondary text-secondary-foreground rounded hover:bg-secondary/80"
            onClick={onClose}
          >
            {secondaryButtonText}
          </button>
          {onPrimaryAction && (
            <button
              className={`px-4 py-2 rounded ${
                isPrimaryDestructive
                  ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  : primaryButtonVariant === "purple"
                  ? "bg-purple-600 text-white hover:bg-purple-700 font-medium"
                  : "bg-primary text-primary-foreground hover:bg-primary/90"
              }`}
              onClick={onPrimaryAction}
              disabled={isPrimaryDisabled}
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
