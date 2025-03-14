/** @type {import('next').NextConfig} */
const nextConfig = {
    reactStrictMode: true,
    swcMinify: true,
    // Enable public runtime config only for NEXT_PUBLIC_ prefixed variables
    publicRuntimeConfig: {
        // Will be available on both server and client
        NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    },
    // Disable ESLint during builds
    eslint: {
        ignoreDuringBuilds: true, // Set to false to enable ESLint during build
    },
    // Log environment for debugging deployment
    onDemandEntries: {
        // Making the production/test process more verbose
        webpack(config, options) {
            const { dev, isServer } = options;

            if (!dev && isServer) {
                console.log(
                    `Environment: ${process.env.ENVIRONMENT || "not set"}`
                );
                console.log(
                    `API URL: ${process.env.NEXT_PUBLIC_API_URL || "not set"}`
                );
            }

            return config;
        },
    },
};

module.exports = nextConfig;
