"use client";
import React, { createContext, useState, useEffect, useMemo } from "react";
import { useRouter, usePathname } from "next/navigation";
import axiosInstance from "../utils/axiosInstance";
import LoadingCircle from "../components/ui/loading_circle";
import { getCookie } from "../utils/cookieUtils";

// Define the shape of our authentication context
export interface AuthContextType {
  isAuthenticated: boolean;
  isAuthLoading: boolean;
  setIsAuthenticated: (auth: boolean) => void;
  csrfToken: string | null;
}

// Create context with default values
export const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false,
  isAuthLoading: false,
  setIsAuthenticated: () => {},
  csrfToken: null,
});

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const router = useRouter();
  const pathname = usePathname();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);

  // Memoize public routes to prevent unnecessary re-renders
  const publicRoutes = useMemo(
    () => ["/login", "/registro", "/forgot-password"],
    []
  );

  // Initial authentication check and CSRF token setup on mount
  useEffect(() => {
    // Get initial CSRF token if it exists
    const initialToken = getCookie("csrftoken");
    if (initialToken) {
      setCsrfToken(initialToken);
    }

    axiosInstance
      .get("api/auth/me")
      .then((response) => {
        setIsAuthenticated(true);

        // Check for CSRF token in cookies after successful auth
        const token = getCookie("csrftoken");
        if (token) {
          setCsrfToken(token);
        }
      })
      .catch((error) => {
        console.error("Auth check failed:", error);
        setIsAuthenticated(false);
      })
      .finally(() => {
        setIsAuthLoading(false);
      });
  }, []);

  // Handle 401 unauthorized responses globally
  useEffect(() => {
    const interceptor = axiosInstance.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          router.refresh();
        }
        return Promise.reject(error);
      }
    );
    // Cleanup interceptor on unmount
    return () => {
      axiosInstance.interceptors.response.eject(interceptor);
    };
  }, [router]);

  // Protected route navigation guard
  useEffect(() => {
    if (
      !isAuthLoading &&
      !isAuthenticated &&
      !publicRoutes.includes(pathname)
    ) {
      router.push("/login");
    }
  }, [isAuthenticated, router, pathname, isAuthLoading, publicRoutes]);

  // Show loading state while checking authentication
  if (isAuthLoading || (!isAuthenticated && !publicRoutes.includes(pathname))) {
    return <LoadingCircle />;
  }

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        isAuthLoading,
        setIsAuthenticated,
        csrfToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
