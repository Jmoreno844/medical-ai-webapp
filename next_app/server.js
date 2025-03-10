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
        const port = process.env.PORT || 3000;
;
        await app.prepare();        const handle = app.getRequestHandler();
.env.PORT || 3000;
        createServer((req, res) => {
            const parsedUrl = parse(req.url, true);
            handle(req, res, parsedUrl);
        }).listen(port, (err) => {
            if (err) throw err;e(req.url, true);
            const environment = process.env.ENVIRONMENT || "development";rsedUrl);
            console.log(`> Ready on http://localhost:${port} (${environment})`);
        }); if (err) throw err;
    } catch (err) {.log(`> Ready on http://localhost:${port}`);
        console.error("Error starting server:", err);
        process.exit(1);
    }   console.error("Error starting server:", err);
}       process.exit(1);
    }
startServer();

startServer();
