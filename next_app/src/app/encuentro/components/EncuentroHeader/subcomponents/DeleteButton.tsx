import React from "react";
import { DeleteButtonProps } from "../../../utils/EncuentroHeaderInterface";

/**
 * Button to delete the current recording
 */
const DeleteButton: React.FC<DeleteButtonProps> = ({ onClick }) => (
  <button
    onClick={onClick}
    className="px-4 py-2 rounded-md bg-gray-200 text-black font-medium hover:bg-gray-300 transition-colors"
  >
    Delete
  </button>
);

export default DeleteButton;
