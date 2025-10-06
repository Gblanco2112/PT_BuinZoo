// main.jsx
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";

import LoginPage from "./LoginPage.jsx";
import { AuthProvider, useAuth } from "./AuthContext.jsx";
import "./styles.css";

function ProtectedApp() {
  const { user, checking } = useAuth();
  if (checking) return <div style={{ padding: 20 }}>Cargando…</div>;
  if (!user) return <LoginPage />;
  return <App />;
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AuthProvider>
      <ProtectedApp />
    </AuthProvider>
  </React.StrictMode>
);
