/**
 * Central frontend logger. Use instead of raw console.* so local/staging stays verbose
 * and production builds stay quiet (see also vite esbuild.drop).
 *
 * Override in dev: VITE_LOG_LEVEL=silent disables all client logs.
 * Sensitive payload logs are allowed by default in dev/test/staging-like modes
 * and can be disabled with VITE_ENABLE_SENSITIVE_LOGS=false. They are never
 * allowed in production.
 */

const env = import.meta.env;
const isDevOrTest = Boolean(env.DEV || env.MODE === "test");
const isStagingLike =
  typeof env.MODE === "string" && env.MODE.toLowerCase().includes("staging");
const nonProductionLogging = Boolean(isDevOrTest || isStagingLike);
const silent =
  typeof env.VITE_LOG_LEVEL === "string" &&
  env.VITE_LOG_LEVEL.toLowerCase() === "silent";
const sensitiveLoggingEnabled =
  nonProductionLogging && env.VITE_ENABLE_SENSITIVE_LOGS !== "false";

const enabled = nonProductionLogging && !silent;

function emit(
  method: "debug" | "info" | "warn" | "error",
  args: unknown[],
): void {
  if (!enabled || args.length === 0) return;
  const fn = console[method];
  if (typeof fn === "function") {
    (fn as (...a: unknown[]) => void)(...args);
  }
}

export const logger = {
  debug: (...args: unknown[]) => emit("debug", args),
  info: (...args: unknown[]) => emit("info", args),
  warn: (...args: unknown[]) => emit("warn", args),
  error: (...args: unknown[]) => emit("error", args),
  sensitiveDebug: (...args: unknown[]) => {
    if (!sensitiveLoggingEnabled) return;
    emit("debug", args);
  },
};

/**
 * Scoped prefix for noisy modules (e.g. createChildLogger("Transcription")).
 */
export function createChildLogger(scope: string) {
  const p = `[${scope}]`;
  return {
    debug: (...args: unknown[]) => logger.debug(p, ...args),
    info: (...args: unknown[]) => logger.info(p, ...args),
    warn: (...args: unknown[]) => logger.warn(p, ...args),
    error: (...args: unknown[]) => logger.error(p, ...args),
  };
}
