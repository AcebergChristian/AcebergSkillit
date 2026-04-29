import React from 'react'
import { ChatIcon, FolderIcon, GridIcon, SparkIcon } from './Icons'

const items = [
  { id: 'dash', label: 'Dash', icon: GridIcon },
  { id: 'sessions', label: '会话列表', icon: ChatIcon },
  { id: 'skills', label: 'Skill 管理', icon: SparkIcon },
]

export default function Sidebar({ activePage, onChange, darkMode, runtime }) {
  return (
    <aside className="panel-border flex h-full w-full flex-col rounded-[28px] border border-white/[0.05] bg-ink-900/95 bg-grain p-4 text-paper-100 shadow-panel dark:border-white/[0.04] dark:bg-ink-900 light:border-black/8 light:bg-white light:text-zinc-900">
      <div className="mb-5 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm uppercase tracking-[0.35em] text-white/45 light:text-zinc-500">
          <span className="h-2.5 w-2.5 rounded-full bg-rust-400" />
          SkillIt
        </div>
        <div className="rounded-full border border-white/[0.06] px-3 py-1 text-xs text-white/55 light:border-black/10 light:text-zinc-500">
          {darkMode ? 'Dark' : 'Light'}
        </div>
      </div>

      <button className="mb-5 flex items-center gap-3 rounded-2xl bg-white/7 px-4 py-3 text-left text-sm font-medium text-paper-50 transition hover:bg-white/10 light:bg-black/5 light:text-zinc-900 light:hover:bg-black/10">
        <span className="rounded-xl bg-black/30 p-2 light:bg-white">
          <FolderIcon className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <div className="truncate">Current workspace</div>
          <div className="truncate text-xs font-normal text-white/38 light:text-zinc-500">{runtime?.workspace_name || ''}</div>
        </div>
      </button>

      <nav className="space-y-1.5">
        {items.map((item) => {
          const Icon = item.icon
          const active = item.id === activePage
          return (
            <button
              key={item.id}
              onClick={() => onChange(item.id)}
              className={`flex w-full items-center gap-3 rounded-2xl px-4 py-2.5 text-left transition ${
                active
                  ? 'bg-white/12 text-paper-50 light:bg-zinc-900 light:text-white'
                  : 'text-white/65 hover:bg-white/6 hover:text-paper-50 light:text-zinc-600 light:hover:bg-black/5 light:hover:text-zinc-900'
              }`}
            >
              <Icon className="h-4 w-4" />
              <span className="text-[14px] font-medium">{item.label}</span>
            </button>
          )
        })}
      </nav>

      <div className="mt-6 border-t border-white/[0.05] pt-5 light:border-black/8">
        <p className="mb-3 text-xs uppercase tracking-[0.28em] text-white/35 light:text-zinc-500">Pinned</p>
        <div className="rounded-2xl bg-white/7 px-4 py-4 light:bg-black/5">
          <div className="mb-2 flex items-center gap-2 text-sm text-mint">
            <span className="h-2 w-2 rounded-full bg-mint" />
            active workflow
          </div>
          <p className="text-sm font-medium text-paper-50 light:text-zinc-900">Research today&apos;s news and export workbook</p>
          <p className="mt-2 text-xs leading-5 text-white/45 light:text-zinc-500">Current flow: research → codegen → export → execute</p>
        </div>
      </div>

      <div className="mt-auto rounded-2xl border border-white/[0.05] bg-black/20 p-4 text-sm light:border-black/8 light:bg-zinc-50">
        <p className="text-white/45 light:text-zinc-500">Runtime</p>
        <p className="mt-1 font-medium text-paper-50 light:text-zinc-900">Import-first runtime</p>
        <p className="mt-2 truncate text-xs text-white/36 light:text-zinc-500">{runtime?.workspace_path || ''}</p>
      </div>
    </aside>
  )
}
