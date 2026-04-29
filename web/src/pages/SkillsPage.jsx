import React, { useEffect, useState } from 'react'
import { getSkills } from '../lib/api'

function InfoButton({ onClick }) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/[0.05] bg-white/[0.05] text-white/70 transition hover:bg-white/[0.08] hover:text-white light:border-black/8 light:bg-white light:text-zinc-600 light:hover:bg-zinc-100 light:hover:text-zinc-900"
      title="查看详情"
    >
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 10v6" />
        <path d="M12 7.2h.01" />
      </svg>
    </button>
  )
}

export default function SkillsPage() {
  const [skills, setSkills] = useState([])
  const [error, setError] = useState('')
  const [selectedSkillId, setSelectedSkillId] = useState('')
  const [detailOpen, setDetailOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const data = await getSkills()
        if (!cancelled) {
          const items = data.items || []
          setSkills(items)
          setSelectedSkillId((prev) => prev || items[0]?.id || '')
        }
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load skills')
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  const selectedSkill = skills.find((item) => item.id === selectedSkillId) || null

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <section className="flex h-full min-h-0 flex-col rounded-[28px] border border-white/[0.05] bg-white/[0.04] p-5 light:border-black/8 light:bg-white">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-white/35 light:text-zinc-500">Skill registry</p>
            <h2 className="mt-2 text-xl font-semibold text-paper-50 light:text-zinc-900">Skill 管理</h2>
          </div>
          <div className="rounded-2xl bg-black/20 px-4 py-2 text-sm text-white/60 light:bg-zinc-50 light:text-zinc-600">
            {skills.length} loaded
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-2xl border border-rust-500/25 bg-rust-500/10 px-4 py-3 text-sm text-rust-200">
            {error}
          </div>
        )}

        <div className={`grid min-h-0 flex-1 gap-4 ${detailOpen ? 'lg:grid-cols-[1fr_320px]' : 'grid-cols-1'}`}>
          <div className="scroll-soft min-h-0 overflow-auto pr-1">
            <div className="grid gap-4 md:grid-cols-2">
              {skills.map((skill) => (
                <button
                  key={skill.id}
                  onClick={() => {
                    setSelectedSkillId(skill.id)
                    setDetailOpen(true)
                  }}
                  className={`flex min-h-[200px] flex-col rounded-[24px] border p-5 text-left transition ${
                    skill.id === selectedSkillId && detailOpen
                      ? 'border-rust-400/28 bg-rust-500/[0.08]'
                      : 'border-white/[0.05] bg-black/20 light:border-black/8 light:bg-zinc-50'
                  }`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="mb-2 flex items-center gap-3">
                        <h3 className="text-lg font-medium text-paper-50 light:text-zinc-900">{skill.name}</h3>
                        <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-xs uppercase tracking-[0.18em] text-white/55 light:bg-black/8 light:text-zinc-500">
                          {skill.type}
                        </span>
                      </div>
                      <p className="font-mono text-sm text-white/35 light:text-zinc-500">{skill.id}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-mint/15 px-2.5 py-1 text-xs text-mint">
                        {skill.status}
                      </span>
                      <InfoButton
                        onClick={() => {
                          setSelectedSkillId(skill.id)
                          setDetailOpen(true)
                        }}
                      />
                    </div>
                  </div>

                  <p className="mt-4 flex-1 text-sm leading-6 text-white/60 light:text-zinc-600">{skill.description}</p>

                  <div className="mt-4 flex flex-wrap gap-2">
                    {(skill.triggers || []).map((trigger) => (
                      <span key={trigger} className="rounded-full border border-white/[0.05] px-3 py-1 text-xs text-white/55 light:border-black/8 light:text-zinc-500">
                        {trigger}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <aside
            className={`min-h-0 overflow-hidden rounded-[24px] border border-white/[0.05] bg-black/18 transition-all duration-200 light:border-black/8 light:bg-zinc-50 ${
              detailOpen ? 'block' : 'hidden'
            }`}
          >
            <div className="scroll-soft h-full overflow-auto p-5">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-white/30 light:text-zinc-500">Skill Details</p>
                  <h3 className="mt-2 text-lg font-semibold text-paper-50 light:text-zinc-900">
                    {selectedSkill?.name || 'No skill selected'}
                  </h3>
                </div>
                <div className="flex items-center gap-2">
                  {selectedSkill && (
                    <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-xs uppercase tracking-[0.18em] text-white/55 light:bg-black/8 light:text-zinc-500">
                      {selectedSkill.type}
                    </span>
                  )}
                  <button
                    onClick={() => setDetailOpen(false)}
                    className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/[0.05] bg-white/[0.05] text-white/70 transition hover:bg-white/[0.08] hover:text-white light:border-black/8 light:bg-white light:text-zinc-600 light:hover:bg-zinc-100 light:hover:text-zinc-900"
                    title="隐藏详情"
                  >
                    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <path d="M6 6l12 12M18 6 6 18" />
                    </svg>
                  </button>
                </div>
              </div>

              {!selectedSkill && (
                <div className="rounded-2xl border border-white/[0.05] bg-black/20 px-4 py-3 text-sm text-white/55 light:border-black/8 light:bg-white light:text-zinc-600">
                  点击任意 skill 卡片或右上角的 info 按钮查看详情。
                </div>
              )}

              {selectedSkill && (
                <div className="space-y-4">
                  <div className="rounded-2xl border border-white/[0.05] bg-black/20 p-4 light:border-black/8 light:bg-white">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">ID</p>
                    <p className="mt-2 font-mono text-sm text-paper-50 light:text-zinc-900">{selectedSkill.id}</p>
                  </div>

                  <div className="rounded-2xl border border-white/[0.05] bg-black/20 p-4 light:border-black/8 light:bg-white">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">Description</p>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-white/70 light:text-zinc-700">
                      {selectedSkill.description || '-'}
                    </p>
                  </div>

                  <div className="rounded-2xl border border-white/[0.05] bg-black/20 p-4 light:border-black/8 light:bg-white">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">Triggers</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {(selectedSkill.triggers || []).length === 0 && (
                        <span className="text-sm text-white/50 light:text-zinc-600">No triggers</span>
                      )}
                      {(selectedSkill.triggers || []).map((trigger) => (
                        <span key={trigger} className="rounded-full border border-white/[0.05] px-3 py-1 text-xs text-white/55 light:border-black/8 light:text-zinc-500">
                          {trigger}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-2xl border border-white/[0.05] bg-black/20 p-4 light:border-black/8 light:bg-white">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">Assets</p>
                    <div className="mt-3 space-y-2 text-sm text-white/65 light:text-zinc-700">
                      <p>scripts: {(selectedSkill.scripts || []).length}</p>
                      <p>references: {(selectedSkill.references || []).length}</p>
                      <p>assets: {(selectedSkill.assets || []).length}</p>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-white/[0.05] bg-black/20 p-4 light:border-black/8 light:bg-white">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">Path</p>
                    <p className="mt-2 break-all font-mono text-xs leading-6 text-white/65 light:text-zinc-700">
                      {selectedSkill.path || '-'}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </aside>
        </div>
      </section>
    </div>
  )
}
