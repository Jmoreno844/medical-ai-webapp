// Simple environment variables helper

/**
 * Gets an environment variable, with fallback to .env.local for development
 */
export function getEnvVariable(name: string): string {
    return process.env[name] || "";
}

/**
 * Log important environment variables for debugging
 */
export function logEnvironment(): void {
    const environment = process.env.NODE_ENV || "development";
    console.log(`Running in ${environment} environment`);

    if (environment === "development") {
        console.log("Using local environment variables (.env.local)");
    } else {
        console.log("Using GitHub-provided environment variables");
    }

    // Log API URL (safe to log as it's public anyway)
    console.log(
        `API URL: ${process.env.TEST_NEXT_PUBLIC_API_URL || "not set"}`
    );
}
