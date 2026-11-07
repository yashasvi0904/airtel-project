"use client";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, tokenStore } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<User>;
  register: (data: { email: string; name: string; password: string; phone?: string }) => Promise<User>;
  googleSignIn: (credential: string) => Promise<User>;
  signOut: () => void;
}

const Ctx = createContext<AuthState>({
  user: null, loading: true,
  signIn: async () => { throw new Error("no provider"); },
  register: async () => { throw new Error("no provider"); },
  googleSignIn: async () => { throw new Error("no provider"); },
  signOut: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tokenStore.get()) {
      setLoading(false);
      return;
    }
    api<User>("/auth/me")
      .then(setUser)
      // only a real 401 means the token is bad; a network blip or a sleeping server must not sign the customer out (e.g. mid-payment)
      .catch((e) => { if (e instanceof ApiError && e.status === 401) tokenStore.set(null); })
      .finally(() => setLoading(false));
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const r = await api<{ token: string; user: User }>("/auth/login", { body: { email, password } });
    tokenStore.set(r.token);
    setUser(r.user);
    return r.user;
  }, []);
  const register = useCallback(async (data: { email: string; name: string; password: string; phone?: string }) => {
    const r = await api<{ token: string; user: User }>("/auth/register", { body: data });
    tokenStore.set(r.token);
    setUser(r.user);
    return r.user;
  }, []);
  const googleSignIn = useCallback(async (credential: string) => {
    const r = await api<{ token: string; user: User }>("/auth/google", { body: { credential } });
    tokenStore.set(r.token);
    setUser(r.user);
    return r.user;
  }, []);
  const signOut = useCallback(() => {
    tokenStore.set(null);
    setUser(null);
  }, []);

  return <Ctx.Provider value={{ user, loading, signIn, register, googleSignIn, signOut }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
