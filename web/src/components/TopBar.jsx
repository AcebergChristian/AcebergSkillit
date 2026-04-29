import React from 'react'
import { MoonIcon, SunIcon } from './Icons'

export default function TopBar({ darkMode, onToggleTheme, runtime }) {
  return (
    <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div>
        <p className="text-xs uppercase tracking-[0.3em] text-white/35 light:text-zinc-500">SkillIt Runtime</p>
        <h1 className="mt-1.5 text-2xl font-semibold text-paper-50 light:text-zinc-900 md:text-[28px]">Workspace Console</h1>
      </div>

      <div className="flex items-center gap-3">
        <div className="max-w-[460px] rounded-2xl border border-white/[0.05] bg-white/[0.04] px-4 py-2 text-sm text-white/65 light:border-black/8 light:bg-white light:text-zinc-600">
          <div className="truncate">{runtime?.workspace_name || 'workspace'}</div>
          <div className="truncate text-xs text-white/36 light:text-zinc-500">{runtime?.current_path || ''}</div>
        </div>
        <button
          onClick={onToggleTheme}
          className="rounded-2xl border border-white/[0.05] bg-white/[0.04] p-3 text-white/75 transition hover:bg-white/[0.08] light:border-black/8 light:bg-white light:text-zinc-700 light:hover:bg-zinc-100"
        >
          {darkMode ? <SunIcon /> : <MoonIcon />}
        </button>
      </div>
    </header>
  )
}
