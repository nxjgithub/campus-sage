export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type?: string;
  expires_in?: number;
}

const ACCESS_TOKEN_KEY = "csage_access_token";
const REFRESH_TOKEN_KEY = "csage_refresh_token";
const TOKEN_TYPE_KEY = "csage_token_type";
const EXPIRES_IN_KEY = "csage_expires_in";

export const AUTH_CLEARED_EVENT = "csage-auth-cleared";

let inMemoryTokens: AuthTokens | null = null;

function getStorage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readTokens(): AuthTokens | null {
  const storage = getStorage();
  if (!storage) {
    return inMemoryTokens;
  }

  const accessToken = storage.getItem(ACCESS_TOKEN_KEY);
  const refreshToken = storage.getItem(REFRESH_TOKEN_KEY);
  if (!accessToken || !refreshToken) {
    return null;
  }

  const tokenType = storage.getItem(TOKEN_TYPE_KEY) ?? "bearer";
  const expiresRaw = storage.getItem(EXPIRES_IN_KEY);
  const expiresIn = expiresRaw ? Number(expiresRaw) : undefined;
  return {
    access_token: accessToken,
    refresh_token: refreshToken,
    token_type: tokenType,
    expires_in: Number.isFinite(expiresIn) ? expiresIn : undefined
  };
}

export function saveTokens(tokens: AuthTokens) {
  inMemoryTokens = tokens;
  const storage = getStorage();
  if (!storage) {
    return;
  }

  storage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  storage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  storage.setItem(TOKEN_TYPE_KEY, tokens.token_type ?? "bearer");
  if (typeof tokens.expires_in === "number") {
    storage.setItem(EXPIRES_IN_KEY, String(tokens.expires_in));
  } else {
    storage.removeItem(EXPIRES_IN_KEY);
  }
}

export function clearTokens() {
  inMemoryTokens = null;
  const storage = getStorage();
  if (storage) {
    storage.removeItem(ACCESS_TOKEN_KEY);
    storage.removeItem(REFRESH_TOKEN_KEY);
    storage.removeItem(TOKEN_TYPE_KEY);
    storage.removeItem(EXPIRES_IN_KEY);
  }
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(AUTH_CLEARED_EVENT));
  }
}

export function getAccessToken() {
  return readTokens()?.access_token ?? null;
}

export function getRefreshToken() {
  return readTokens()?.refresh_token ?? null;
}
