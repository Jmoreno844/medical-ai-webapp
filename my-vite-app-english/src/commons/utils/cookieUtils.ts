/**
 * Gets a cookie value by name
 */
export const getCookie = (name: string): string | null => {
  if (typeof document === "undefined") return null;

  const cookies = document.cookie.split(";");
  for (let i = 0; i < cookies.length; i++) {
    const cookie = cookies[i].trim();
    if (cookie.startsWith(name + "=")) {
      return cookie.substring(name.length + 1);
    }
  }
  return null;
};

/**
 * Sets a cookie with the given name, value and options
 */
export const setCookie = (
  name: string,
  value: string,
  options: {
    expires?: Date;
    path?: string;
    sameSite?: "strict" | "lax" | "none";
    secure?: boolean;
  } = {}
): void => {
  if (typeof document === "undefined") return;

  let cookieString = `${name}=${value}`;

  if (options.expires) {
    cookieString += `; expires=${options.expires.toUTCString()}`;
  }

  if (options.path) {
    cookieString += `; path=${options.path}`;
  }

  if (options.sameSite) {
    cookieString += `; samesite=${options.sameSite}`;
  }

  if (options.secure) {
    cookieString += `; secure`;
  }

  document.cookie = cookieString;
};

/**
 * Removes a cookie by name
 */
export const removeCookie = (name: string, path = "/"): void => {
  setCookie(name, "", {
    expires: new Date(0),
    path,
  });
};
