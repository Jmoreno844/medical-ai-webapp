import React, {
  createContext,
  useState,
  useEffect,
  useMemo,
  useCallback,
} from "react";
import { useNavigate, useLocation } from "react-router-dom";
import axiosInstance from "../utils/axiosInstance";
import LoadingCircle from "../components/LoadingCircle";
import { getCookie } from "../utils/cookieUtils";
import { logger } from "@/lib/logger";

// Define the shape of our user data
export interface UserProfile {
  id: number;
  email: string;
  name: string;
  last_name: string;
  role: string;
  capabilities: {
    can_access_admin_panel: boolean;
    can_view_audit: boolean;
    can_manage_users: boolean;
  };
}

// Define the shape of our authentication context
export interface AuthContextType {
  isAuthenticated: boolean;
  isAuthLoading: boolean;
  userData: UserProfile | null;
  csrfToken: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUserData: () => Promise<void>;
}

// Create context with default values
export const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false,
  isAuthLoading: false,
  userData: null,
  csrfToken: null,
  login: async () => {},
  logout: async () => {},
  refreshUserData: async () => {},
});

// Logger utility for consistent logging
const logAuth = (type: "info" | "error", message: string, data?: any) => {
  const prefix = "[AuthContext]";
  if (type === "info") {
    logger.debug(`${prefix} ${message}`, data || "");
  } else {
    logger.error(`${prefix} ${message}`, data || "");
  }
};

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const pathname = location.pathname;
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [userData, setUserData] = useState<UserProfile | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);

  // Memoize public routes to prevent unnecessary re-renders
  const publicRoutes = useMemo(
    () => ["/login", "/registro", "/forgot-password"],
    []
  );

  // Function to update CSRF token
  const updateCsrfToken = useCallback(() => {
    const token = getCookie("_xsrf") || getCookie("csrftoken");
    if (token) {
      setCsrfToken(token);
    }
  }, []);

  // Function to refresh user data
  const refreshUserData = useCallback(async () => {
    if (!isAuthenticated) return;

    try {
      logAuth("info", "Fetching user data");
      const response = await axiosInstance.get("/api/v1/auth/me");
      logAuth("info", "User data fetched successfully", response.data);
      setUserData(response.data);
    } catch (error: any) {
      logAuth("error", "Failed to fetch user data:", {
        status: error.response?.status,
        data: error.response?.data,
      });
    }
  }, [isAuthenticated]);

  // Login function
  const login = useCallback(
    async (email: string, password: string) => {
      // Add immediate synchronous log to confirm function entry
      logger.debug("🔐 AUTH-CONTEXT LOGIN FUNCTION CALLED with email:", email);
      try {
        logAuth("info", "Attempting login with email", { email });
        logger.debug("🔐 AUTH-CONTEXT: Before API call");
        const response = await axiosInstance.post("/api/v1/auth/login", {
          email,
          password,
        });
        logger.debug(
          "🔐 AUTH-CONTEXT: API call completed with status:",
          response.status
        );
        logAuth("info", "Login successful", {
          status: response.status,
        });
        setIsAuthenticated(true);
        if (response.data?.user) {
          setUserData(response.data.user);
        }
        updateCsrfToken();
        await refreshUserData();
        logAuth("info", "Redirecting to home page");
        navigate("/home"); // Using navigate instead of router.push
      } catch (error: any) {
        logger.error("🔴 AUTH-CONTEXT LOGIN ERROR:", error);
        logAuth("error", "Login failed", {
          status: error.response?.status,
          data: error.response?.data,
        });
        throw error;
      }
    },
    [navigate, refreshUserData, updateCsrfToken]
  );

  // Logout function
  const logout = useCallback(async () => {
    try {
      logAuth("info", "Attempting logout");
      await axiosInstance.post("/api/v1/auth/logout");
      logAuth("info", "Logout successful");
    } catch (error: any) {
      logAuth("error", "Logout error", {
        status: error.response?.status,
        message: error.message,
      });
    } finally {
      setIsAuthenticated(false);
      setUserData(null);
      navigate("/login"); // Using navigate instead of router.push
    }
  }, [navigate]);

  // Initial authentication check and CSRF token setup on mount
  useEffect(() => {
    logAuth("info", "Checking authentication status");
    updateCsrfToken();

    // Check whether the FastAPI JWT cookie exists.
    const hasCookie = document.cookie
      .split(";")
      .some((item) => {
        const cookie = item.trim();
        return cookie.startsWith("medical_access_token=");
      });
    logAuth("info", "Auth cookie exists:", hasCookie);

    axiosInstance
      .get("/api/v1/auth/me")
      .then((response) => {
        logAuth("info", "User is authenticated", response.data);
        setIsAuthenticated(true);
        updateCsrfToken();
        refreshUserData();
      })
      .catch((error) => {
        logAuth("error", "Auth check failed", {
          status: error.response?.status,
          data: error.response?.data,
        });
        setIsAuthenticated(false);
        setUserData(null);
      })
      .finally(() => {
        setIsAuthLoading(false);
      });
  }, [updateCsrfToken, refreshUserData]);

  // Handle 401 unauthorized responses globally
  useEffect(() => {
    const interceptor = axiosInstance.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          logAuth("info", "Unauthorized access detected, logging out user");
          setIsAuthenticated(false);
          setUserData(null);

          // Only redirect if not already on a public route
          if (!publicRoutes.includes(pathname)) {
            navigate("/login"); // Using navigate instead of router.push
          }
        }
        return Promise.reject(error);
      }
    );
    // Cleanup interceptor on unmount
    return () => {
      axiosInstance.interceptors.response.eject(interceptor);
    };
  }, [navigate, pathname, publicRoutes]);

  // Protected route navigation guard
  useEffect(() => {
    if (
      !isAuthLoading &&
      !isAuthenticated &&
      !publicRoutes.includes(pathname)
    ) {
      logAuth("info", "Redirecting unauthenticated user from protected route", {
        currentPath: pathname,
      });
      navigate("/login"); // Using navigate instead of router.push
    }
  }, [isAuthenticated, navigate, pathname, isAuthLoading, publicRoutes]);

  // Show loading state while checking authentication
  if (isAuthLoading || (!isAuthenticated && !publicRoutes.includes(pathname))) {
    return <LoadingCircle />;
  }

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        isAuthLoading,
        userData,
        csrfToken,
        login,
        logout,
        refreshUserData,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
