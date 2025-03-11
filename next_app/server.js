const { createServer } = require("http");
const { parse } = require("url");
const next = require("next");

// Import the secret manager (will use dynamic import to work with ESM)
async function startServer() {
    try {
        // Only load secrets in non-development environments
        if (process.env.NODE_ENV !== "development") {
            const environment = process.env.ENVIRONMENT || "test";
            console.log(`Starting server in ${environment} environment`);

            // Check if GCP_PROJECT_ID is set
            if (!process.env.GCP_PROJECT_ID) {
                console.error(
                    "GCP_PROJECT_ID environment variable is not set!"
                );
                process.exit(1);
            }

            console.log(`Using GCP Project: ${process.env.GCP_PROJECT_ID}`);

            const { loadSecrets } = await import("./src/lib/secretManager.js");
            await loadSecrets();
        }

        const dev = process.env.NODE_ENV === "development";
        const app = next({ dev });
        const handle = app.getRequestHandler();
        const port = process.env.PORT || 3000;

        await app.prepare();

        createServer((req, res) => {
            const parsedUrl = parse(req.url, true);
            handle(req, res, parsedUrl);
        }).listen(port, (err) => {
            if (err) throw err;
            const environment = process.env.ENVIRONMENT || "development";
            console.log(`> Ready on http://localhost:${port} (${environment})`);
        });
    } catch (err) {
        console.error("Error starting server:", err);
        process.exit(1);
    }
}

startServer();
