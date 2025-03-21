export const env = {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL!,
    NODE_ENV: process.env.NODE_ENV || "development",
} as const;

// Add validation to ensure required variables are defined
Object.entries(env).forEach(([key, value]) => {
    if (value === undefined) {
        throw new Error(`Environment variable ${key} is not defined`);
    }
});
