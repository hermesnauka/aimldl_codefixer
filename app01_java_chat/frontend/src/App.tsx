import { useState } from "react";
import { getStoredToken } from "./api/client";
import Chat from "./pages/Chat";
import Login from "./pages/Login";

/**
 * Simple state-based route guard: react-router would be overkill for a
 * two-screen Phase-1 app (Login / Chat) — see frontend/README.md.
 */
export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(
    () => getStoredToken() !== null,
  );

  if (!isAuthenticated) {
    return <Login onLoginSuccess={() => setIsAuthenticated(true)} />;
  }

  return <Chat onLogout={() => setIsAuthenticated(false)} />;
}
