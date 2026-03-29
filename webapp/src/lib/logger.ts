/**
 * Central frontend logger. Use instead of raw console.* so dev/test stay verbose
 * and production builds stay quiet (see also vite esbuild.drop).
 *
 * Override in dev: VITE_LOG_LEVEL=silent disables all client logs.
 */

const env = import.meta.env;
const isDevOrTest = Boolean(env.DEV || env.MODE === "test");
const silent =
  typeof env.VITE_LOG_LEVEL === "string" &&
  env.VITE_LOG_LEVEL.toLowerCase() === "silent";

const enabled = isDevOrTest && !silent;

function emit(
  method: "debug" | "info" | "warn" | "error",
  args: unknown[]
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
