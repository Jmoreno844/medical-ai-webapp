"use client";

import React, { ReactNode } from "react";
import { StatusMessageContainer } from "@/components/StatusMessage";
import { ToastContainer } from "react-toastify";

interface ProvidersProps {
  children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
  return (
    <>
      {/* Global toast notification container */}
      <StatusMessageContainer />

      {/* Alternative direct ToastContainer if the custom one fails */}
      <ToastContainer
        position="top-right"
        autoClose={5000}
        hideProgressBar={false}
        newestOnTop={true}
        closeOnClick
        rtl={false}
        pauseOnFocusLoss
        draggable
        pauseOnHover
        style={{ zIndex: 9999 }}
      />

      {children}
    </>
  );
}
