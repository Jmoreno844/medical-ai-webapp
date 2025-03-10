import { SecretManagerServiceClient } from "@google-cloud/secret-manager";

// This will only run on the server side
export async function getSecret(secretName: string): Promise<string> {
    // Use local env variables during development
    if (process.env.NODE_ENV === "development") {
        return process.env[secretName] || "";
    }

    try {
        // Get environment suffix for test or production
        const environment = process.env.ENVIRONMENT || "test"; // Default to test if not specified
        const client = new SecretManagerServiceClient();
        const projectId = process.env.GCP_PROJECT_ID;

        if (!projectId) {
            console.error("GCP_PROJECT_ID environment variable is not set");
            return "";
        }

        // Format the secret name with environment suffix for different environments
        // For example: NEXT_PUBLIC_API_URL_test or NEXT_PUBLIC_API_URL_production
        const environmentSpecificName = `${secretName}_${environment}`;

        try {
            // First try to get environment-specific secret
            const [version] = await client.accessSecretVersion({
                name: `projects/${projectId}/secrets/${environmentSpecificName}/versions/latest`,
            });
            const payload = version.payload?.data?.toString() || "";
            return payload;
        } catch (error) {
            console.log(
                `No environment-specific secret found for ${environmentSpecificName}, trying generic version`
            );

            // Fall back to generic secret name
            const [version] = await client.accessSecretVersion({
                name: `projects/${projectId}/secrets/${secretName}/versions/latest`,
            });
            const payload = version.payload?.data?.toString() || "";
            return payload;
        }
    } catch (error) {
        console.error(`Error fetching secret ${secretName}:`, error);
        return "";
    }
}

// Load all secrets at once
export async function loadSecrets(): Promise<void> {
    if (process.env.NODE_ENV === "development") {
        console.log("Running in development mode, using local .env files");
        return;
    }

    const environment = process.env.ENVIRONMENT || "test";
    console.log(`Loading secrets for ${environment} environment`);

    const secrets = [
        "NEXT_PUBLIC_API_URL",
        // Add other secrets as needed
    ];

    console.log(
        `Loading secrets from Google Cloud Secret Manager for ${environment} environment`
    );

    try {
        await Promise.all(
            secrets.map(async (secretName) => {
                const value = await getSecret(secretName);
                if (value) {
                    process.env[secretName] = value;
                } else {
                    console.warn(`No value found for secret: ${secretName}`);
                }
            })
        );
        console.log(
            "Successfully loaded secrets from Google Cloud Secret Manager"
        );
    } catch (error) {
        console.error("Failed to load secrets:", error);
    }
}
