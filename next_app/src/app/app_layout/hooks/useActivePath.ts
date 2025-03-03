"use client";
import { usePathname } from "next/navigation";

/**
 * Custom hook to determine if a given path is active.
 * 
 * @returns {Object} An object containing the isActivePath function to evaluate paths.
 */
export const useActivePath = () => {
  const pathname = usePathname();

  /**
   * Checks if the current pathname matches the provided path or starts with the given pattern.
   * 
   * @param {string | undefined} path - The exact path to match against.
   * @param {string} [pattern] - Optional pattern to check if pathname starts with this string.
   * @returns {boolean} True if the current pathname is active, false otherwise.
   */
  const isActivePath = (path: string | undefined, pattern?: string): boolean => {
    if (!path) return false;
    if (pattern) {
      return pathname.startsWith(pattern);
    }
    return pathname === path;
  };

  return { isActivePath };
};
