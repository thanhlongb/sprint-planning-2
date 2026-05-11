import { useEffect, useState } from "react";

const PLATFORM_URL = import.meta.env.VITE_PLATFORM_URL ?? "http://localhost:8000";

type Participant = { id: string; name: string; role: string; endpoint: string };

export default function App() {
  const [health, setHealth] = useState<string>("…");
  const [participants, setParticipants] = useState<Participant[]>([]);

  useEffect(() => {
    fetch(`${PLATFORM_URL}/health`)
      .then((r) => r.json())
      .then((d) => setHealth(d.status))
      .catch(() => setHealth("unreachable"));
    fetch(`${PLATFORM_URL}/participants`)
      .then((r) => r.json())
      .then(setParticipants)
      .catch(() => setParticipants([]));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 720 }}>
      <h1>Sprint Planning 2.0</h1>
      <p>
        Platform: <code>{PLATFORM_URL}</code> — status: <strong>{health}</strong>
      </p>
      <h2>Registered participants</h2>
      {participants.length === 0 ? (
        <p>No participants registered yet.</p>
      ) : (
        <ul>
          {participants.map((p) => (
            <li key={p.id}>
              <strong>{p.name}</strong> ({p.role}) — {p.endpoint}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
