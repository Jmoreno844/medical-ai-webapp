import axios from "axios";
import { getCookie } from "./cookieUtils";

// Use VITE_API_URL prefix for client-side environment variables
const API_URL = import.meta.env.VITE_API_URL || "";
console.log("API URL:", API_URL); // Helps with debugging

// Function to get CSRF token from cookiess
const getCsrfToken = (): string | null => {
  return getCookie("csrftoken");
};

const axiosInstance = axios.create({
  baseURL: API_URL,
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

// Add request interceptor to include CSRF token in every request
axiosInstance.interceptors.request.use(
  (config) => {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      config.headers["X-CSRFToken"] = csrfToken;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Add response interceptor for better error handling
axiosInstance.interceptors.response.use(
  (response) => {
    // Check if there's a new CSRF token in the response headers or cookies
    const setCookieHeader = response.headers["set-cookie"];
    if (setCookieHeader && typeof document !== "undefined") {
      // The browser will automatically handle the cookie update
      console.debug("New cookies received from server");
    }
    return response;
  },
  (error) => {
    // Enhanced error handling with specific CORS error detection
    if (error.message === "Network Error" || error.code === "ERR_NETWORK") {
      console.error(
        "CORS or network error detected. Check your CORS configuration."
      );
    }

    console.error("API Error:", {
      status: error.response?.status,
      data: error.response?.data,
      config: error.config,
    });
    return Promise.reject(error);
  }
);

export default axiosInstance;
