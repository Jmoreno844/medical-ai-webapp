import axios from "axios";
import { logger } from "@/lib/logger";
import {
  clearCsrfToken,
  ensureCsrfToken,
  fetchCsrfToken,
  getCsrfToken,
} from "./csrfTokenStore";

const API_URL = import.meta.env.VITE_API_URL || "";
logger.debug("API URL:", API_URL);

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
    refreshRequest = (async () => {
      await ensureCsrfToken(API_URL);
      await axiosInstance.post("/api/v1/auth/refresh");
      await fetchCsrfToken(API_URL);
    })().finally(() => {
      refreshRequest = null;
    });
  }
  await refreshRequest;
};

axiosInstance.interceptors.request.use(
  async (config) => {
    let csrfToken = getCsrfToken();

    if (!csrfToken) {
      try {
        logger.debug("No CSRF token in memory; fetching from /api/v1/csrf");
        csrfToken = await fetchCsrfToken(API_URL);
      } catch (error) {
        logger.error("Error fetching CSRF token:", error);
      }
    }

    logger.debug(`Request: ${config.method?.toUpperCase()} ${config.url}`);

    if (csrfToken) {
      config.headers["X-CSRFToken"] = csrfToken;
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

axiosInstance.interceptors.response.use(
  (response) => response,
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

export { clearCsrfToken, fetchCsrfToken, getCsrfToken };
export default axiosInstance;
