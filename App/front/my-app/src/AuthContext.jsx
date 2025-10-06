// AuthContext.jsx
import { createContext, useContext, useEffect, useState } from "react";

const API_BASE = "http://127.0.0.1:8000"; // ajusta en prod
const AuthContext = createContext(null);

async function getJSON(path) {
  const res = await fetch(API_BASE + path, { credentials: "include" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function postJSON(path, body) {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);

  // check session on mount (me → refresh → unauth)
  useEffect(() => {
    (async () => {
      try {
        const me = await getJSON("/auth/me");
        setUser(me);
      } catch {
        try {
          await postJSON("/auth/refresh");
          const me = await getJSON("/auth/me");
          setUser(me);
        } catch {
          setUser(null);
        }
      } finally {
        setChecking(false);
      }
    })();
  }, []);

  const login = async (username, password) => {
    await postJSON("/auth/login", { username, password }); // backend expects JSON
    const me = await getJSON("/auth/me");
    setUser(me);
  };

  const logout = async () => {
    try { await postJSON("/auth/logout"); } catch {}
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, checking, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
