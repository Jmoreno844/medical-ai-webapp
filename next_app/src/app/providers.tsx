"use client";

import React, { ReactNode } from "react";

interface ProvidersProps {
    children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
    return (
        <>
            {/* Alternative direct ToastContainer if the custom one fails */}

            {children}
        </>
    );
}
