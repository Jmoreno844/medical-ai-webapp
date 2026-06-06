import axios from "axios";

import { getCookie } from "./cookieUtils";

let inMemoryCsrfToken: string | null = null;

export function getCsrfToken(): string | null {
  return inMemoryCsrfToken ?? getCookie("_xsrf") ?? getCookie("csrftoken");
}

export function setCsrfToken(token: string | null): void {
  inMemoryCsrfToken = token;
}

export function clearCsrfToken(): void {
  inMemoryCsrfToken = null;
}

export async function fetchCsrfToken(apiBaseUrl: string): Promise<string | null> {
  const base = apiBaseUrl.replace(/\/$/, "");
  if (!base) {
    return getCsrfToken();
  }

  const response = await axios.get(`${base}/api/v1/csrf`, {
    withCredentials: true,
  });
  const token = response.data?.csrfToken;
  if (typeof token === "string" && token.length > 0) {
    setCsrfToken(token);
    return token;
  }

  return getCsrfToken();
}

export async function ensureCsrfToken(apiBaseUrl: string): Promise<string | null> {
  const existing = getCsrfToken();
  if (existing) {
    return existing;
  }
  return fetchCsrfToken(apiBaseUrl);
}
