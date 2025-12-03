// main.jsx
// Punto de entrada del frontend. Monta el árbol de React y aplica AuthProvider.

import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";

import LoginPage from "./LoginPage.jsx";
import { AuthProvider, useAuth } from "./AuthContext.jsx";
import "./styles.css";

// Envuelve la App y decide si mostrar login o dashboard según el estado de auth
function ProtectedApp() {
  const { user, checking } = useAuth();
  if (checking) return <div style={{ padding: 20 }}>Cargando…</div>;
  if (!user) return <LoginPage />;
  return <App />;
}

// Montaje de la aplicación React en el elemento root del HTML
createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AuthProvider>
      <ProtectedApp />
    </AuthProvider>
  </React.StrictMode>
);
