import React, { useEffect, useState } from 'react'
import { getSkills } from '../lib/api'

export default function SkillsPage() {
  const [skills, setSkills] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const data = await getSkills()
        if (!cancelled) setSkills(data.items || [])
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load skills')
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

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

        <div className="scroll-soft min-h-0 flex-1 overflow-auto pr-1">
          <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {skills.map((skill) => (
            <div key={skill.id} className="flex min-h-[180px] flex-col rounded-[24px] border border-white/[0.05] bg-black/20 p-5 light:border-black/8 light:bg-zinc-50">
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
                <span className="rounded-full bg-mint/15 px-2.5 py-1 text-xs text-mint">
                  {skill.status}
                </span>
              </div>
              <p className="mt-4 flex-1 text-sm leading-6 text-white/60 light:text-zinc-600">{skill.description}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {(skill.triggers || []).map((trigger) => (
                  <span key={trigger} className="rounded-full border border-white/[0.05] px-3 py-1 text-xs text-white/55 light:border-black/8 light:text-zinc-500">
                    {trigger}
                  </span>
                ))}
              </div>
            </div>
          ))}
          </div>
        </div>
      </section>
    </div>
  )
}
