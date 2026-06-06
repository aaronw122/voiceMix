import { useEffect, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'https://voiceapi.awill.co'

export default function App() {
  const [health, setHealth] = useState('checking…')

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((r) => r.json())
      .then((d) => setHealth(d.status ?? 'unknown'))
      .catch(() => setHealth('unreachable'))
  }, [])

  return (
    <main style={{ fontFamily: 'system-ui, sans-serif', padding: '2rem', maxWidth: 640 }}>
      <h1>voiceMix</h1>
      <p>Frontend shell is live.</p>
      <p>
        Backend health: <strong>{health}</strong>
      </p>
    </main>
  )
}
