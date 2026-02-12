import {
  createContext,
  PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from "react";
import { AxiosError } from "axios";
import { login, logout } from "../api/modules/auth";
import { fetchCurrentUser, CurrentUser } from "../api/modules/users";
import {
  AUTH_CLEARED_EVENT,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  saveTokens
} from "./token";
import { AppRole, resolveRoleFromRoles } from "./role";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  user: CurrentUser | null;
  role: AppRole;
  isAuthenticated: boolean;
  signIn: (payload: { email: string; password: string }) => Promise<void>;
  signOut: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function isUnauthorizedError(error: unknown) {
  if (!(error instanceof AxiosError)) {
    return false;
  }
  return error.response?.status === 401;
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<CurrentUser | null>(null);

  const loadCurrentUser = useCallback(async () => {
    if (!getAccessToken()) {
      setUser(null);
      setStatus("anonymous");
      return;
    }
    try {
      const me = await fetchCurrentUser();
      setUser(me);
      setStatus("authenticated");
    } catch (error) {
      if (isUnauthorizedError(error)) {
        clearTokens();
      }
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  useEffect(() => {
    void loadCurrentUser();
  }, [loadCurrentUser]);

  useEffect(() => {
    const onAuthCleared = () => {
      setUser(null);
      setStatus("anonymous");
    };
    window.addEventListener(AUTH_CLEARED_EVENT, onAuthCleared);
    return () => {
      window.removeEventListener(AUTH_CLEARED_EVENT, onAuthCleared);
    };
  }, []);

  const signIn = useCallback(
    async (payload: { email: string; password: string }) => {
      const tokens = await login(payload);
      saveTokens(tokens);
      await loadCurrentUser();
    },
    [loadCurrentUser]
  );

  const signOut = useCallback(async () => {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      try {
        await logout({ refresh_token: refreshToken });
      } catch {
        // 退出登录失败不影响本地清理，避免用户被卡住
      }
    }
    clearTokens();
    setUser(null);
    setStatus("anonymous");
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      role: resolveRoleFromRoles(user?.roles),
      isAuthenticated: status === "authenticated",
      signIn,
      signOut,
      refreshUser: loadCurrentUser
    }),
    [loadCurrentUser, signIn, signOut, status, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth 必须在 AuthProvider 内使用");
  }
  return context;
}
