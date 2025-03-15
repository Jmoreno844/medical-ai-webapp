"use client";
import React, {
    createContext,
    useState,
    useEffect,
    useMemo,
    useCallback,
} from "react";
import { useRouter, usePathname } from "next/navigation";
import axiosInstance from "../utils/axiosInstance";
import LoadingCircle from "../components/ui/loading_circle";
import { getCookie } from "../utils/cookieUtils";

// Define the shape of our user data
export interface UserProfile {
    id: number;
    email: string;
    name: string;
    lastName: string;
    role: string;
    // Add other user fields as needed
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

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
    const router = useRouter();
    const pathname = usePathname();
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
        const token = getCookie("csrftoken");
        if (token) {
            setCsrfToken(token);
        }
    }, []);

    // Function to refresh user data
    const refreshUserData = useCallback(async () => {
        if (!isAuthenticated) return;

        try {
            const response = await axiosInstance.get("api/auth/me/data");
            setUserData(response.data);
        } catch (error) {
            console.error("Failed to fetch user data:", error);
        }
    }, [isAuthenticated]);

    // Login function
    const login = useCallback(
        async (email: string, password: string) => {
            try {
                await axiosInstance.post("api/auth/login", { email, password });
                setIsAuthenticated(true);
                updateCsrfToken();
                await refreshUserData();
                router.push("/dashboard");
            } catch (error) {
                console.error("Login failed:", error);
                throw error;
            }
        },
        [router, refreshUserData, updateCsrfToken]
    );

    // Logout function
    const logout = useCallback(async () => {
        try {
            await axiosInstance.post("api/auth/logout");
        } catch (error) {
            console.error("Logout error:", error);
        } finally {
            setIsAuthenticated(false);
            setUserData(null);
            router.push("/login");
        }
    }, [router]);

    // Initial authentication check and CSRF token setup on mount
    useEffect(() => {
        updateCsrfToken();

        axiosInstance
            .get("api/auth/me")
            .then((response) => {
                setIsAuthenticated(true);
                updateCsrfToken();
                refreshUserData();
            })
            .catch((error) => {
                console.error("Auth check failed:", error);
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
                    setIsAuthenticated(false);
                    setUserData(null);

                    // Only redirect if not already on a public route
                    if (!publicRoutes.includes(pathname)) {
                        router.push("/login");
                    }
                }
                return Promise.reject(error);
            }
        );
        // Cleanup interceptor on unmount
        return () => {
            axiosInstance.interceptors.response.eject(interceptor);
        };
    }, [router, pathname, publicRoutes]);

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
    if (
        isAuthLoading ||
        (!isAuthenticated && !publicRoutes.includes(pathname))
    ) {
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
