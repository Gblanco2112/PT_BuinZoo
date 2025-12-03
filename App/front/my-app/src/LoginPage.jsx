// LoginPage.jsx
// Pantalla de login de la aplicación. Maneja usuario/contraseña y estados de carga/error.

import { useState } from "react";
import { useAuth } from "./AuthContext";
// If you place the file in src/assets:
import logo from "./assets/buinzoo_logo_otro.png";
// If you prefer /public, delete the line above and use: <img src="/buinzoo-logo.png" ... />

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Maneja el submit del formulario: llama a login() y controla errores/loader
  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(username, password);
    } catch (err) {
      // Mensaje genérico en caso de credenciales inválidas
      setError("Usuario o contraseña incorrectos");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <form onSubmit={handleSubmit} className="login-form">
        <img
          className="login-logo"
          src={logo}          // o "/buinzoo-logo.png" si el archivo está en /public
          alt="Bioparque Buinzoo"
          width={240}
          height="auto"
        />
        <h2>Iniciar sesión</h2>

        <input
          type="text"
          placeholder="Usuario"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
        <input
          type="password"
          placeholder="Contraseña"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <button type="submit" disabled={loading}>
          {loading ? "Entrando..." : "Entrar"}
        </button>
        {error && <p className="error">{error}</p>}
      </form>
    </div>
  );
}
