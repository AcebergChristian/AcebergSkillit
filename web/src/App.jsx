import React, { useEffect, useMemo, useState } from 'react'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import DashPage from './pages/DashPage'
import SessionsPage from './pages/SessionsPage'
import SkillsPage from './pages/SkillsPage'
import { getRuntime } from './lib/api'

const THEME_STORAGE_KEY = 'skillit-theme'
const DEFAULT_ROUTE = '/dash'
const ROUTE_TO_PAGE = {
  '/dash': 'dash',
  '/sessions': 'sessions',
  '/skills': 'skills',
}
const PAGE_TO_ROUTE = {
  dash: '/dash',
  sessions: '/sessions',
  skills: '/skills',
}

function getInitialDarkMode() {
  if (typeof window === 'undefined') return true
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
  if (stored === 'dark') return true
  if (stored === 'light') return false
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? true
}

function normalizePath(pathname) {
  return ROUTE_TO_PAGE[pathname] ? pathname : DEFAULT_ROUTE
}

export default function App() {
  const [activePage, setActivePage] = useState(() => {
    if (typeof window === 'undefined') return 'dash'
    return ROUTE_TO_PAGE[normalizePath(window.location.pathname)] || 'dash'
  })
  const [darkMode, setDarkMode] = useState(getInitialDarkMode)
  const [runtime, setRuntime] = useState(null)

  useEffect(() => {
    document.body.classList.toggle('light', !darkMode)
    document.documentElement.classList.toggle('dark', darkMode)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(THEME_STORAGE_KEY, darkMode ? 'dark' : 'light')
    }
  }, [darkMode])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const nextPath = normalizePath(window.location.pathname)
    if (window.location.pathname !== nextPath) {
      window.history.replaceState({}, '', nextPath)
    }

    function handlePopState() {
      setActivePage(ROUTE_TO_PAGE[normalizePath(window.location.pathname)] || 'dash')
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

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

  function handlePageChange(nextPage) {
    const nextPath = PAGE_TO_ROUTE[nextPage] || DEFAULT_ROUTE
    setActivePage(nextPage)
    if (typeof window !== 'undefined' && window.location.pathname !== nextPath) {
      window.history.pushState({}, '', nextPath)
    }
  }

  const page = useMemo(() => {
    if (activePage === 'sessions') return <SessionsPage runtime={runtime} />
    if (activePage === 'skills') return <SkillsPage />
    return <DashPage />
  }, [activePage, runtime])

  return (
    <div className={`h-screen overflow-hidden ${darkMode ? 'bg-ink-950 text-paper-100' : 'bg-paper-50 text-zinc-900'}`}>
      <div className="mx-auto flex h-full max-w-[1440px] flex-col gap-3 p-3 md:flex-row md:p-3">
        <div className="md:w-[280px] md:min-w-[280px]">
          <Sidebar activePage={activePage} onChange={handlePageChange} darkMode={darkMode} runtime={runtime} />
        </div>

        <main className="flex h-full min-h-0 flex-1 flex-col rounded-[28px] border border-white/[0.05] bg-ink-950/60 p-4 light:border-black/8 light:bg-paper-100 md:p-4">
          <TopBar darkMode={darkMode} onToggleTheme={() => setDarkMode((v) => !v)} runtime={runtime} />
          {page}
        </main>
      </div>
    </div>
  )
}
