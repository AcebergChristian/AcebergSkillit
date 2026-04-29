import React, { useEffect, useMemo, useState } from 'react'
import { chatStream, getSession, getSessions } from '../lib/api'

function formatEvent(event) {
  if (!event) return ''
  if (event.type === 'workflow') {
    const tasks = (event.workflow?.tasks || []).map((task) => task.kind).join(' -> ')
    return tasks || 'workflow ready'
  }
  if (event.type === 'plan') return `plan: ${(event.plan?.steps || []).length} steps`
  if (event.type === 'tool') return `${event.step_id} ${event.tool} ${event.ok ? 'ok' : 'failed'}`
  if (event.type === 'run') return `${event.path || event.script || 'script'} exit=${event.exit_code}`
  if (event.type === 'repair') return `repair attempt ${event.attempt} exit=${event.exit_code}`
  if (event.type === 'task_dir') return event.task_dir || ''
  return event.message || event.skill_id || event.type
}

function formatBytes(size) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function DrawerToggle({ open, onClick }) {
  return (
    <button
      onClick={onClick}
      className="absolute right-3 top-3 z-20 flex h-11 w-11 items-center justify-center rounded-2xl border border-white/[0.06] bg-black/55 text-white/72 shadow-[0_10px_30px_rgba(0,0,0,0.28)] transition hover:bg-black/70 light:border-black/8 light:bg-white light:text-zinc-700"
      title={open ? '收起会话列表' : '展开会话列表'}
    >
      <svg viewBox="0 0 24 24" className={`h-4 w-4 transition ${open ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M9 6l6 6-6 6" />
      </svg>
    </button>
  )
}

export default function SessionsPage({ runtime }) {
  const [sessions, setSessions] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [snapshot, setSnapshot] = useState(null)
  const [liveEvents, setLiveEvents] = useState([])
  const [requirement, setRequirement] = useState('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)

  async function loadSessions(preferredId = '') {
    const data = await getSessions()
    const items = data.items || []
    setSessions(items)
    const nextId = preferredId || selectedId || items[0]?.id || ''
    if (nextId && nextId !== selectedId) setSelectedId(nextId)
    return items
  }

  useEffect(() => {
    let cancelled = false
    async function boot() {
      try {
        const items = await loadSessions()
        if (!cancelled && items[0]?.id) {
          setSelectedId((prev) => prev || items[0].id)
        }
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load sessions')
      }
    }
    boot()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    if (!selectedId) return undefined
    async function sync() {
      try {
        const data = await getSession(selectedId)
        if (!cancelled) setSnapshot(data)
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load session')
      }
    }
    sync()
    return () => {
      cancelled = true
    }
  }, [selectedId])

  const processEvents = useMemo(() => {
    if (liveEvents.length > 0) return liveEvents
    return snapshot?.events || []
  }, [liveEvents, snapshot])

  const turns = snapshot?.turns || []
  const toolRows = snapshot?.tool_results || []
  const outputFiles = snapshot?.outputs || []
  const workflowTasks = snapshot?.workflow?.tasks || []

  async function handleRun(event) {
    event.preventDefault()
    if (!requirement.trim() || running) return
    setRunning(true)
    setError('')
    setLiveEvents([])

    const title = snapshot?.session?.title || sessions.find((item) => item.id === selectedId)?.title || 'web-console'

    try {
      await chatStream(
        {
          requirement: requirement.trim(),
          title,
          session_id: selectedId || undefined,
          reuse_session_by_title: !selectedId,
        },
        {
          onEvent: (payload) => {
            setLiveEvents((prev) => [...prev, payload])
            if (payload.session_id) setSelectedId(payload.session_id)
          },
          onFinal: async ({ snapshot: finalSnapshot, result }) => {
            setSnapshot(finalSnapshot)
            setSelectedId(result.session_id)
            setLiveEvents([])
            await loadSessions(result.session_id)
          },
          onError: (payload) => {
            setError(payload.message || 'Runtime error')
          },
        },
      )
    } catch (err) {
      setError(err.message || 'Failed to run requirement')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden rounded-[28px] border border-white/[0.05] bg-white/[0.035] p-3 light:border-black/8 light:bg-white">
      <DrawerToggle open={drawerOpen} onClick={() => setDrawerOpen((v) => !v)} />

      <div className={`grid min-h-0 flex-1 gap-3 overflow-hidden transition-all duration-300 ${drawerOpen ? 'xl:grid-cols-[1fr_280px]' : 'grid-cols-1'}`}>
        <section className="grid min-h-0 h-[86vh] grid-rows-[minmax(0,1fr)_auto] gap-3 overflow-hidden">
          <div className="grid min-h-0 gap-3 overflow-hidden xl:grid-cols-[1.08fr_0.92fr]">
            <div className="flex min-h-0 flex-col overflow-hidden rounded-[24px] border border-white/[0.05] bg-black/22 p-4 light:border-black/8 light:bg-zinc-50">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.28em] text-white/30 light:text-zinc-500">Process</p>
                  <h2 className="mt-2 text-lg font-semibold text-paper-50 light:text-zinc-900">运行流程</h2>
                </div>
                <span className="rounded-full bg-mint/12 px-3 py-1 text-xs text-mint">
                  {running ? 'live' : 'snapshot'}
                </span>
              </div>

              <div className="mb-3 grid gap-2 md:grid-cols-3">
                <div className="rounded-2xl border border-white/[0.04] bg-black/24 px-4 py-3 light:border-black/8 light:bg-white">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">Session</p>
                  <p className="mt-2 font-mono text-sm text-paper-50 light:text-zinc-900">{selectedId || runtime?.active_session_id || '-'}</p>
                </div>
                <div className="rounded-2xl border border-white/[0.04] bg-black/24 px-4 py-3 light:border-black/8 light:bg-white">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">Workspace</p>
                  <p className="mt-2 truncate text-sm text-paper-50 light:text-zinc-900">{runtime?.workspace_name || '-'}</p>
                </div>
                <div className="rounded-2xl border border-white/[0.04] bg-black/24 px-4 py-3 light:border-black/8 light:bg-white">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">Path</p>
                  <p className="mt-2 truncate text-sm text-paper-50 light:text-zinc-900">{runtime?.current_path || '-'}</p>
                </div>
              </div>

              <div className="scroll-soft min-h-0 flex-1 space-y-4 overflow-auto pr-1">
                <div>
                  <div className="mb-3 flex items-center justify-between">
                    <p className="text-xs uppercase tracking-[0.24em] text-white/30 light:text-zinc-500">Chat History</p>
                    <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-[11px] text-white/55 light:bg-black/6 light:text-zinc-500">
                      {turns.length}
                    </span>
                  </div>
                  <div className="space-y-3">
                    {turns.length === 0 && (
                      <div className="rounded-2xl border border-white/[0.04] bg-black/24 px-4 py-3 text-sm text-white/50 light:border-black/8 light:bg-white light:text-zinc-600">
                        No messages yet.
                      </div>
                    )}
                    {turns.map((turn, index) => (
                      <div
                        key={`${turn.ts || index}-${turn.role}`}
                        className={`rounded-2xl border px-4 py-3 ${
                          turn.role === 'user'
                            ? 'border-[#c2714c]/45 bg-[#c2714c] text-white shadow-[inset_0_1px_rgba(255,255,255,0.08)]'
                            : 'border-white/[0.04] bg-black/24 light:border-black/8 light:bg-white'
                        }`}
                      >
                        <div className="mb-2 flex items-center justify-between gap-3">
                          <span className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">
                            {turn.role}
                          </span>
                          <span className="text-[11px] text-white/26 light:text-zinc-400">{turn.ts || ''}</span>
                        </div>
                        <p className={`whitespace-pre-wrap break-words text-sm leading-6 ${turn.role === 'user' ? 'text-white' : 'text-white/78 light:text-zinc-700'}`}>
                          {turn.content}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="mb-3 flex items-center justify-between">
                    <p className="text-xs uppercase tracking-[0.24em] text-white/30 light:text-zinc-500">Runtime Events</p>
                    <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-[11px] text-white/55 light:bg-black/6 light:text-zinc-500">
                      {processEvents.length}
                    </span>
                  </div>
                  <div className="rounded-2xl border border-white/[0.04] bg-black/18 p-3 light:border-black/8 light:bg-zinc-100">
                    {processEvents.length === 0 && (
                      <div className="rounded-2xl bg-black/24 px-4 py-3 text-sm text-white/50 light:bg-white light:text-zinc-600">
                        No events yet.
                      </div>
                    )}
                    {processEvents.map((eventItem, index) => (
                      <div key={`${eventItem.ts || index}-${eventItem.type}`} className="border-b border-white/[0.04] px-1 py-2 last:border-b-0 light:border-black/8">
                        <div className="mb-1 flex items-center justify-between gap-3">
                          <span className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">{eventItem.type}</span>
                          <span className="text-[11px] text-white/26 light:text-zinc-400">{eventItem.ts || ''}</span>
                        </div>
                        <p className="whitespace-pre-wrap break-words text-sm leading-6 text-white/68 light:text-zinc-700">{formatEvent(eventItem)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div className="grid min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-3 overflow-hidden">
              <div className="rounded-[24px] border border-white/[0.05] bg-black/22 p-4 light:border-black/8 light:bg-zinc-50">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.28em] text-white/30 light:text-zinc-500">Workflow</p>
                    <h2 className="mt-2 text-lg font-semibold text-paper-50 light:text-zinc-900">任务编排</h2>
                  </div>
                  <span className="rounded-full bg-white/[0.06] px-3 py-1 text-xs text-white/55 light:bg-black/6 light:text-zinc-500">
                    {workflowTasks.length}
                  </span>
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  {workflowTasks.length === 0 && (
                    <div className="rounded-2xl border border-white/[0.04] bg-black/24 p-4 text-sm text-white/50 light:border-black/8 light:bg-white light:text-zinc-600">
                      No workflow yet.
                    </div>
                  )}
                  {workflowTasks.map((task) => (
                    <div key={task.id} className="rounded-2xl border border-white/[0.04] bg-black/24 p-4 light:border-black/8 light:bg-white">
                      <div className="mb-3 flex items-center justify-between">
                        <span className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">{task.id}</span>
                        <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-xs text-white/55 light:bg-black/6 light:text-zinc-500">
                          {task.kind}
                        </span>
                      </div>
                      <p className="text-sm font-medium text-paper-50 light:text-zinc-900">{task.description}</p>
                      <p className="mt-2 text-xs text-white/42 light:text-zinc-500">{task.skill_id || 'default skill'}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid min-h-0 gap-3 overflow-hidden xl:grid-cols-[0.95fr_1.05fr]">
                <div className="flex min-h-0 flex-col overflow-hidden rounded-[24px] border border-white/[0.05] bg-black/22 p-4 light:border-black/8 light:bg-zinc-50">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <p className="text-xs uppercase tracking-[0.28em] text-white/30 light:text-zinc-500">Trace</p>
                      <h2 className="mt-2 text-lg font-semibold text-paper-50 light:text-zinc-900">执行轨迹</h2>
                    </div>
                    <span className="rounded-full bg-white/[0.06] px-3 py-1 text-xs text-white/55 light:bg-black/6 light:text-zinc-500">
                      {toolRows.length}
                    </span>
                  </div>

                  <div className="scroll-soft min-h-0 flex-1 space-y-3 overflow-auto pr-1">
                    {toolRows.length === 0 && (
                      <div className="rounded-2xl border border-white/[0.04] bg-black/24 px-4 py-3 text-sm text-white/50 light:border-black/8 light:bg-white light:text-zinc-600">
                        No tool trace yet.
                      </div>
                    )}
                    {toolRows.map((row) => {
                      const data = (row.result || {}).data || {}
                      return (
                        <div key={`${row.step_id}-${row.tool}-${row.ts}`} className="rounded-2xl border border-white/[0.04] bg-black/24 p-4 light:border-black/8 light:bg-white">
                          <div className="flex items-center justify-between gap-3">
                            <p className="font-mono text-sm text-paper-50 light:text-zinc-900">{row.step_id}</p>
                            <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-xs text-white/55 light:bg-black/6 light:text-zinc-500">
                              {row.tool}
                            </span>
                          </div>
                          <p className="mt-3 text-sm text-white/62 light:text-zinc-600">{data.path || data.script || JSON.stringify(row.input)}</p>
                          {'exit_code' in data && (
                            <p className="mt-2 text-xs text-white/36 light:text-zinc-500">exit_code: {String(data.exit_code)}</p>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>

                <div className="flex min-h-0 flex-col overflow-hidden rounded-[24px] border border-white/[0.05] bg-black/22 p-4 light:border-black/8 light:bg-zinc-50">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <p className="text-xs uppercase tracking-[0.28em] text-white/30 light:text-zinc-500">Output</p>
                      <h2 className="mt-2 text-lg font-semibold text-paper-50 light:text-zinc-900">产物文件</h2>
                    </div>
                    <span className="rounded-full bg-white/[0.06] px-3 py-1 text-xs text-white/55 light:bg-black/6 light:text-zinc-500">
                      {snapshot?.task_output_dir || '-'}
                    </span>
                  </div>

                  <div className="scroll-soft min-h-0 flex-1 space-y-3 overflow-auto pr-1">
                    {outputFiles.length === 0 && (
                      <div className="rounded-2xl border border-white/[0.04] bg-black/24 px-4 py-3 text-sm text-white/50 light:border-black/8 light:bg-white light:text-zinc-600">
                        No output files yet.
                      </div>
                    )}
                    {outputFiles.map((file) => (
                      <div key={file.path} className="rounded-2xl border border-white/[0.04] bg-black/24 p-4 light:border-black/8 light:bg-white">
                        <div className="flex items-center justify-between gap-3">
                          <p className="font-medium text-paper-50 light:text-zinc-900">{file.relative_path}</p>
                          <span className="text-xs text-white/36 light:text-zinc-500">{formatBytes(file.size)}</span>
                        </div>
                        <p className="mt-2 font-mono text-xs text-white/34 light:text-zinc-500">{file.path}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <form onSubmit={handleRun} className="rounded-[24px] border border-white/[0.05] bg-black/22 p-4 light:border-black/8 light:bg-zinc-50">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.28em] text-white/30 light:text-zinc-500">Input</p>
                <h2 className="mt-2 text-lg font-semibold text-paper-50 light:text-zinc-900">用户需求</h2>
              </div>
              <button
                type="submit"
                disabled={running}
                className="rounded-2xl bg-rust-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-rust-400 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {running ? 'Running...' : 'Run'}
              </button>
            </div>

            <textarea
              value={requirement}
              onChange={(e) => setRequirement(e.target.value)}
              rows={4}
              className="w-full resize-y rounded-3xl border border-white/[0.05] bg-black/24 p-4 text-sm leading-6 text-white/82 outline-none placeholder:text-white/25 light:border-black/8 light:bg-white light:text-zinc-900 light:placeholder:text-zinc-400"
              placeholder="输入你的任务需求"
            />

            {error && (
              <div className="mt-4 rounded-2xl border border-rust-500/20 bg-rust-500/10 px-4 py-3 text-sm text-rust-200">
                {error}
              </div>
            )}
          </form>
        </section>

        <aside className={`overflow-hidden rounded-[24px] border border-white/[0.05] bg-black/28 transition-all duration-300 light:border-black/8 light:bg-zinc-50 ${drawerOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0 xl:w-0'}`}>
          <div className="flex h-full min-h-0 flex-col p-4">
            <div className="mb-4 pr-10">
              <p className="text-xs uppercase tracking-[0.28em] text-white/30 light:text-zinc-500">Sessions</p>
              <h2 className="mt-2 text-lg font-semibold text-paper-50 light:text-zinc-900">切换会话</h2>
            </div>

            <div className="scroll-soft min-h-0 flex-1 space-y-3 overflow-auto pr-1">
              {sessions.map((row) => (
                <button
                  key={row.id}
                  onClick={() => {
                    setSelectedId(row.id)
                    setDrawerOpen(false)
                  }}
                  className={`w-full rounded-[20px] border p-4 text-left transition ${
                    row.id === selectedId
                      ? 'border-rust-400/28 bg-rust-500/10'
                      : 'border-white/[0.04] bg-black/20 hover:bg-black/28 light:border-black/8 light:bg-white light:hover:bg-zinc-100'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-paper-50 light:text-zinc-900">{row.title}</p>
                      <p className="mt-2 font-mono text-[11px] text-white/34 light:text-zinc-500">{row.id}</p>
                      {row.last_turn_preview && (
                        <p className="mt-2 max-h-[60px] overflow-hidden text-xs leading-5 text-white/42 light:text-zinc-500">
                          {row.last_turn_preview}
                        </p>
                      )}
                    </div>
                    <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-[11px] text-white/55 light:bg-black/6 light:text-zinc-500">
                      {row.status}
                    </span>
                  </div>
                  <p className="mt-3 text-[11px] text-white/32 light:text-zinc-500">{row.updated_at}</p>
                </button>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}
