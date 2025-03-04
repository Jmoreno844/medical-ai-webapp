import { toast, ToastContainer, Id } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";

/**
 * Status message type definitions
 */
export interface StatusMessageProps {
  /** Type of message - success or error */
  type: "success" | "error";
  /** Message content to display */
  message: string;
}

let toastContainerMounted = false;

/**
 * Register that the toast container has been mounted
 */
export const registerToastContainer = () => {
  toastContainerMounted = true;
  console.log("Toast container registered as mounted");
};

/**
 * Shows a toast notification using react-toastify
 * This approach is CSP compatible by avoiding inline styles
 *
 * @param type - Type of message (success or error)
 * @param message - Message content
 */
export const showStatusMessage = ({
  type,
  message,
}: StatusMessageProps): Id => {
  console.log(`Showing ${type} notification: ${message}`);

  if (!toastContainerMounted) {
    console.warn("Toast container not registered as mounted yet!");
  }

  const toastId = `toast-${Date.now()}-${Math.random()
    .toString(36)
    .substring(2, 9)}`;

  if (type === "success") {
    return toast.success(message, {
      toastId,
      position: "top-right",
      autoClose: 5000,
      hideProgressBar: false,
      closeOnClick: true,
      pauseOnHover: true,
      draggable: true,
      className: "status-toast status-toast-success",
      bodyClassName: "status-toast-body",
      progressClassName: "status-toast-progress",
    });
  } else {
    return toast.error(message, {
      toastId,
      position: "top-right",
      autoClose: 5000,
      hideProgressBar: false,
      closeOnClick: true,
      pauseOnHover: true,
      draggable: true,
      className: "status-toast status-toast-error",
      bodyClassName: "status-toast-body",
      progressClassName: "status-toast-progress",
    });
  }
};

/**
 * Force show a test notification - useful for debugging
 */
export const showTestNotification = () => {
  showStatusMessage({
    type: "success",
    message: "This is a test notification",
  });

  setTimeout(() => {
    showStatusMessage({
      type: "error",
      message: "This is a test error notification",
    });
  }, 1000);
};

/**
 * Toast container component that should be mounted once in your app layout
 * CSP compatible by avoiding inline styles
 */
export const StatusMessageContainer = () => {
  React.useEffect(() => {
    registerToastContainer();
    return () => {
      toastContainerMounted = false;
      console.log("Toast container unmounted");
    };
  }, []);

  return (
    <ToastContainer
      position="top-right"
      autoClose={5000}
      hideProgressBar={false}
      newestOnTop
      closeOnClick
      rtl={false}
      pauseOnFocusLoss
      draggable
      pauseOnHover
      theme="light"
      // Ensure CSP compatibility
      enableMultiContainer={false}
      className="status-toast-container"
      bodyClassName="status-toast-body"
      toastClassName="status-toast"
      progressClassName="status-toast-progress"
      style={{ zIndex: 9999 }}
    />
  );
};
