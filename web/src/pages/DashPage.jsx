import React, { useEffect, useState } from 'react'
import { getOverview } from '../lib/api'

function formatEvent(event) {
  if (!event) return 'No runtime events yet.'
  if (event.type === 'workflow') {
    const tasks = (event.workflow?.tasks || []).map((item) => item.kind).join(' -> ')
    return `[workflow] ${tasks || 'no tasks'}`
  }
  if (event.type === 'tool') {
    return `[tool] ${event.step_id} ${event.tool} ${event.ok ? 'ok' : 'failed'}`
  }
  if (event.type === 'run') {
    return `[run] ${event.path || event.script || 'script'} exit=${event.exit_code}`
  }
  return `[${event.type}] ${event.message || event.task_dir || event.skill_id || ''}`.trim()
}

export default function DashPage() {
  const [overview, setOverview] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const data = await getOverview()
        if (!cancelled) setOverview(data)
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load overview')
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  const stats = overview?.stats || {}
  const active = overview?.active_session
  const events = overview?.recent_events || []

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-4">
        {[
          { title: 'Active Sessions', value: stats.active_sessions || 0 },
          { title: 'Skills Loaded', value: stats.skills_loaded || 0 },
          { title: 'Learned Skills', value: stats.learned_skills || 0 },
          { title: 'Recent Outputs', value: stats.output_files || 0 },
        ].map((card) => (
          <div key={card.title} className="rounded-[24px] border border-white/[0.05] bg-white/[0.04] p-5 light:border-black/8 light:bg-white">
            <p className="text-sm text-white/45 light:text-zinc-500">{card.title}</p>
            <div className="mt-3 flex items-end justify-between">
              <span className="text-4xl font-semibold text-paper-50 light:text-zinc-900">{card.value}</span>
            </div>
          </div>
        ))}
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-[28px] border border-white/[0.05] bg-white/[0.04] p-6 light:border-black/8 light:bg-white">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-white/35 light:text-zinc-500">Active session</p>
              <h2 className="mt-2 text-xl font-semibold text-paper-50 light:text-zinc-900">
                {active?.title || 'No session'}
              </h2>
            </div>
            <span className="rounded-full bg-rust-500/15 px-3 py-1 text-xs text-rust-300">
              {active?.status || 'idle'}
            </span>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-3xl bg-black/20 p-5 light:bg-zinc-50">
              <p className="text-xs uppercase tracking-[0.25em] text-white/35 light:text-zinc-500">Session</p>
              <p className="mt-3 font-mono text-sm text-white/60 light:text-zinc-700">{active?.id || '-'}</p>
              <p className="mt-4 text-sm text-white/50 light:text-zinc-600">{active?.updated_at || '-'}</p>
            </div>

            <div className="rounded-3xl bg-black/20 p-5 light:bg-zinc-50">
              <p className="text-xs uppercase tracking-[0.25em] text-white/35 light:text-zinc-500">Workflow</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {(active?.workflow?.tasks || []).map((task) => (
                  <span key={task.id} className="rounded-full border border-white/[0.05] px-3 py-1 text-xs text-white/70 light:border-black/8 light:text-zinc-700">
                    {task.kind}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-[28px] border border-white/[0.05] bg-white/[0.04] p-6 light:border-black/8 light:bg-white">
          <p className="text-xs uppercase tracking-[0.28em] text-white/35 light:text-zinc-500">Recent events</p>
          <div className="mt-5 space-y-3">
            {events.length === 0 && (
              <div className="rounded-2xl bg-black/20 px-4 py-3 text-sm text-white/50 light:bg-zinc-50 light:text-zinc-600">
                {error || 'No runtime events yet.'}
              </div>
            )}
            {events.map((event, index) => (
              <div key={`${event.ts || index}-${event.type}`} className="rounded-2xl bg-black/20 px-4 py-3 text-sm text-white/70 light:bg-zinc-50 light:text-zinc-700">
                {formatEvent(event)}
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}
