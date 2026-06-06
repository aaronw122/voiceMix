import { useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'https://voiceapi.awill.co'

export default function App() {
  const [backendHealth, setBackendHealth] = useState('checking…')

  useEffect(() => {
    fetch(`${API_BASE_URL}/health`)
      .then((response) => response.json())
      .then((payload) => setBackendHealth(payload.status ?? 'unknown'))
      .catch(() => setBackendHealth('unreachable'))
  }, [])

  return (
    <main style={{ fontFamily: 'system-ui, sans-serif', padding: '2rem', maxWidth: 640 }}>
      <h1>voiceMix</h1>
      <p>Frontend shell is live.</p>
      <p>
        Backend health: <strong>{backendHealth}</strong>
      </p>
    </main>
  )
}
