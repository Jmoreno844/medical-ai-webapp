import { useState, useContext } from "react";
import axiosInstance from "../utils/axiosInstance";
import { AuthContext } from "../contexts/AuthContext";

interface SignupCredentials {
  email: string;
  password: string;
  name: string;
  lastName: string;
}

// Logger utility for consistent logging
const logAuth = (type: "info" | "error", message: string, data?: any) => {
  const prefix = "[useAuth]";
  if (type === "info") {
    console.log(`${prefix} ${message}`, data || "");
  } else {
    console.error(`${prefix} ${message}`, data || "");
  }
};

export const useAuth = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const {
    login: contextLogin,
    logout: contextLogout,
    isAuthLoading,
    userData,
    isAuthenticated,
  } = useContext(AuthContext);

  const login = async (email: string, password: string) => {
    setLoading(true);
    setError(null);
    try {
      logAuth("info", "Delegating login to AuthContext");
      console.log("📱 USEAUTH: About to call contextLogin with email:", email);
      await contextLogin(email, password);
      console.log("📱 USEAUTH: contextLogin call completed");
      logAuth("info", "Login completed successfully");
      return { success: true };
    } catch (err: any) {
      // Extract error message from API response if available
      const errorMessage =
        err.response?.data?.detail ||
        err.response?.data?.message ||
        (err instanceof Error ? err.message : "Error al iniciar sesión");
      logAuth("error", "Login failed", { message: errorMessage });
      setError(errorMessage);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    setLoading(true);
    setError(null);
    try {
      logAuth("info", "Delegating logout to AuthContext");
      await contextLogout();
      return { success: true };
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Error al cerrar sesión";
      logAuth("error", "Logout failed", { message: errorMessage });
      setError(errorMessage);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const forgotPassword = async (email: string) => {
    setLoading(true);
    setError(null);
    try {
      logAuth("info", "Requesting password reset for email", email);
      const response = await axiosInstance.post("/api/auth/forgot-password", {
        email,
      });
      return response.data;
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Error al recuperar contraseña";
      logAuth("error", "Password reset failed", {
        message: errorMessage,
      });
      setError(errorMessage);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const signUp = async ({
    email,
    name,
    lastName,
    password,
  }: SignupCredentials) => {
    setLoading(true);
    setError(null);
    try {
      logAuth("info", "Attempting signup");
      const response = await axiosInstance.post("api/auth/registro", {
        email,
        name,
        lastName,
        password,
      });
      logAuth("info", "Signup successful");
      return response.data;
    } catch (err: any) {
      const errorMessage =
        err.response?.data?.detail ||
        err.response?.data?.message ||
        (err instanceof Error ? err.message : "Error en el registro");
      logAuth("error", "Signup failed", { message: errorMessage });
      setError(errorMessage);
      throw err;
    } finally {
      setLoading(false);
    }
  };

  return {
    login,
    logout,
    forgotPassword,
    signUp,
    loading: loading || isAuthLoading,
    error,
    userData,
    isAuthenticated,
  };
};
