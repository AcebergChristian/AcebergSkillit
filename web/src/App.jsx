import React, { useEffect, useMemo, useState } from 'react'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import DashPage from './pages/DashPage'
import SessionsPage from './pages/SessionsPage'
import SkillsPage from './pages/SkillsPage'
import { getRuntime } from './lib/api'

export default function App() {
  const [activePage, setActivePage] = useState('dash')
  const [darkMode, setDarkMode] = useState(true)
  const [runtime, setRuntime] = useState(null)

  useEffect(() => {
    document.body.classList.toggle('light', !darkMode)
    document.documentElement.classList.toggle('dark', darkMode)
  }, [darkMode])

  useEffect(() => {
    let cancelled = false
    async function loadRuntime() {
      try {
        const data = await getRuntime()
        if (!cancelled) setRuntime(data)
      } catch {
        if (!cancelled) setRuntime(null)
      }
    }
    loadRuntime()
    return () => {
      cancelled = true
    }
  }, [])

  const page = useMemo(() => {
    if (activePage === 'sessions') return <SessionsPage runtime={runtime} />
    if (activePage === 'skills') return <SkillsPage />
    return <DashPage />
  }, [activePage, runtime])

  return (
    <div className={`h-screen overflow-hidden ${darkMode ? 'bg-ink-950 text-paper-100' : 'bg-paper-50 text-zinc-900'}`}>
      <div className="mx-auto flex h-full max-w-[1440px] flex-col gap-3 p-3 md:flex-row md:p-3">
        <div className="md:w-[280px] md:min-w-[280px]">
          <Sidebar activePage={activePage} onChange={setActivePage} darkMode={darkMode} runtime={runtime} />
        </div>

        <main className="flex h-full min-h-0 flex-1 flex-col rounded-[28px] border border-white/[0.05] bg-ink-950/60 p-4 light:border-black/8 light:bg-paper-100 md:p-4">
          <TopBar darkMode={darkMode} onToggleTheme={() => setDarkMode((v) => !v)} runtime={runtime} />
          {page}
        </main>
      </div>
    </div>
  )
}
