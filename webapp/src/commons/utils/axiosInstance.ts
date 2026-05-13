import axios from "axios";
import { logger } from "@/lib/logger";
import { getCookie } from "./cookieUtils";

// Use VITE_API_URL prefix for client-side environment variables
const API_URL = import.meta.env.VITE_API_URL || "";
logger.debug("API URL:", API_URL); // Helps with debugging

// Function to get CSRF token from cookiess
const getCsrfToken = (): string | null => {
  return getCookie("_xsrf") || getCookie("csrftoken");
};

const axiosInstance = axios.create({
  baseURL: API_URL,
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

let refreshRequest: Promise<void> | null = null;

const shouldAttemptRefresh = (url?: string): boolean => {
  if (!url) return true;
  return !url.includes("/api/v1/auth/login") && !url.includes("/api/v1/auth/refresh");
};

const refreshSession = async (): Promise<void> => {
  if (!refreshRequest) {
    refreshRequest = axiosInstance
      .post("/api/v1/auth/refresh")
      .then(() => undefined)
      .finally(() => {
        refreshRequest = null;
      });
  }
  await refreshRequest;
};

// Add request interceptor to include CSRF token in every request
axiosInstance.interceptors.request.use(
  async (config) => {
    // Check if CSRF token already exists in cookies
    let csrfToken = getCsrfToken();

    // Only fetch CSRF token if not already available
    if (!csrfToken) {
      try {
        logger.debug("🔄 No CSRF token found. Fetching from /api/v1/csrf...");
        await axios.get(`${API_URL}/api/v1/csrf`, {
          withCredentials: true,
        });
        //   logger.debug("📥 CSRF Response:", csrfResponse.data);
        // Get the token after the API call
        csrfToken = getCsrfToken();
      } catch (error) {
        logger.error("❌ Error fetching CSRF token:", error);
      }
    } else {
      // logger.debug("✅ Using existing CSRF token from cookies");
    }

    // Add logging for CSRF token and request details
    logger.debug(`🔒 Request: ${config.method?.toUpperCase()} ${config.url}`);
    // logger.debug(`🔑 CSRF Token: ${csrfToken || "NOT SET"}`);
    //  logger.debug(`🍪 All Cookies: ${document.cookie}`);

    if (csrfToken) {
      config.headers["X-CSRFToken"] = csrfToken;
      //   logger.debug(   `✅ Added X-CSRFToken header: ${csrfToken.substring(0, 10)}...`);
    } else {
      //  logger.warn(`⚠️ No CSRF token available for request to ${config.url}`);
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
      //  logger.debug("New cookies received from server");
    }
    return response;
  },
  (error) => {
    const originalRequest = error.config;

    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      shouldAttemptRefresh(originalRequest.url)
    ) {
      originalRequest._retry = true;

      return refreshSession()
        .then(() => axiosInstance(originalRequest))
        .catch((refreshError) => Promise.reject(refreshError));
    }

    if (error.message === "Network Error" || error.code === "ERR_NETWORK") {
      logger.error("Network/API response was not readable:", {
        method: error.config?.method,
        url: error.config?.url,
        message:
          "The browser could not read the backend response. This is often a backend crash, timeout, or missing CORS headers on an error response.",
      });
      return Promise.reject(error);
    }

    logger.error("API Error:", {
      status: error.response?.status,
      method: error.config?.method,
      url: error.config?.url,
      data: error.response?.data,
    });
    return Promise.reject(error);
  }
);

export default axiosInstance;
