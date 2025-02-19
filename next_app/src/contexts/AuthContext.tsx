"use client";
import React, { createContext, useState, useEffect, useMemo } from "react";
import { useRouter, usePathname } from "next/navigation";
import axiosInstance from "../utils/axiosInstance";
import LoadingCircle from "../components/ui/loading_circle";

export interface AuthContextType {
  isAuthenticated: boolean;
  setAuthenticated: (auth: boolean) => void;
}

export const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false,
  setAuthenticated: () => {},
});

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const router = useRouter();
  const pathname = usePathname();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isAuthLoading, setIsAuthLoading] = useState(true);

  const setAuthenticated = (auth: boolean) => {
    setIsAuthenticated(auth);
  };

  const publicRoutes = useMemo(
    () => ["/login", "/registro", "/forgot-password"],
    []
  );

  // Check auth status via axios on mount after reload
  useEffect(() => {
    axiosInstance
      .get("api/auth/me")
      .then(() => {
        setAuthenticated(true);
      })
      .catch(() => {
        setAuthenticated(false);
      })
      .finally(() => {
        setIsAuthLoading(false);
      });
  }, []);

  useEffect(() => {
    const interceptor = axiosInstance.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response && error.response.status === 401) {
          router.refresh();
        }
        return Promise.reject(error);
      }
    );
    return () => {
      axiosInstance.interceptors.response.eject(interceptor);
    };
  }, [router]);

  // Redirect on non-public routes if not authenticated
  useEffect(() => {
    if (
      !isAuthLoading &&
      !isAuthenticated &&
      !publicRoutes.includes(pathname)
    ) {
      router.push("/login");
    }
  }, [isAuthenticated, router, pathname, isAuthLoading, publicRoutes]);

  // Use LoadingCircle component for fallback UI
  if (isAuthLoading) {
    return <LoadingCircle />;
  }
  if (!isAuthenticated && !publicRoutes.includes(pathname)) {
    return <LoadingCircle />;
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, setAuthenticated }}>
      {children}
    </AuthContext.Provider>
  );
};
