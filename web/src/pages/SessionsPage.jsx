import React, { useEffect, useMemo, useRef, useState } from 'react'
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

function formatTime(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function truncatePreview(text, max = 120) {
  const value = String(text || '').trim()
  if (!value) return ''
  return value.length > max ? `${value.slice(0, max)}...` : value
}

function toTimestamp(value) {
  if (!value) return Number.NaN
  const time = new Date(value).getTime()
  return Number.isNaN(time) ? Number.NaN : time
}

function buildProcessSteps(events, running) {
  const steps = []
  for (const event of events || []) {
    if (!event) continue
    if (event.type === 'session') {
      steps.push({ id: `${event.ts}-session`, title: 'Session Started', detail: event.message || 'session created', ts: event.ts, state: 'done' })
      continue
    }
    if (event.type === 'task_dir') {
      steps.push({ id: `${event.ts}-task_dir`, title: 'Prepare Workspace', detail: event.task_dir || 'task directory ready', ts: event.ts, state: 'done' })
      continue
    }
    if (event.type === 'workflow') {
      const tasks = event.workflow?.tasks || []
      if (tasks.length === 0) {
        steps.push({ id: `${event.ts}-workflow`, title: 'Thinking', detail: 'workflow ready', ts: event.ts, state: 'done' })
      } else {
        tasks.forEach((task, idx) => {
          steps.push({
            id: `${event.ts}-${task.id || idx}`,
            title: `Thinking · ${idx + 1}/${tasks.length}`,
            detail: `${task.kind}: ${task.description}`,
            ts: event.ts,
            state: 'done',
          })
        })
      }
      continue
    }
    if (event.type === 'skill') {
      steps.push({ id: `${event.ts}-skill`, title: 'Pick Skill', detail: event.message || event.skill_id || 'skill selected', ts: event.ts, state: 'done' })
      continue
    }
    if (event.type === 'plan') {
      const planSteps = event.plan?.steps || []
      planSteps.forEach((step, idx) => {
        steps.push({
          id: `${event.ts}-${step.id || idx}`,
          title: `Plan · ${idx + 1}/${planSteps.length}`,
          detail: step.kind === 'tool' ? `${step.tool || 'tool'}: ${step.description}` : step.description,
          ts: event.ts,
          state: 'done',
        })
      })
      continue
    }
    if (event.type === 'tool') {
      const detail = event.tool === 'write_text'
        ? `${event.path || 'file written'}${event.preview ? `\n${truncatePreview(event.preview)}` : ''}`
        : event.path || event.script || event.step_id || 'tool call'
      steps.push({
        id: `${event.ts}-${event.step_id || 'tool'}`,
        title: event.ok ? `Execute · ${event.tool}` : `Failed · ${event.tool}`,
        detail,
        ts: event.ts,
        state: event.ok ? 'done' : 'error',
      })
      continue
    }
    if (event.type === 'run' || event.type === 'repair') {
      const ok = event.exit_code === 0
      steps.push({
        id: `${event.ts}-${event.type}`,
        title: event.type === 'repair' ? 'Repair Script' : 'Run Script',
        detail: `${event.path || event.script || 'script'} exit=${event.exit_code ?? '-'}`,
        ts: event.ts,
        state: ok ? 'done' : 'error',
      })
      continue
    }
    if (event.type === 'reply_start') {
      steps.push({ id: `${event.ts}-reply_start`, title: 'Generate Reply', detail: 'model is drafting the answer', ts: event.ts, state: 'done' })
      continue
    }
    if (event.type === 'final_reply') {
      steps.push({ id: `${event.ts}-final_reply`, title: 'Reply Ready', detail: 'answer streamed to chat', ts: event.ts, state: 'done' })
      continue
    }
  }

  if (steps.length > 0) {
    const lastNonError = [...steps].reverse().find((step) => step.state !== 'error')
    if (lastNonError) {
      lastNonError.state = 'active'
    }
  }
  return steps
}

function buildAssistantStepMap(turns, events) {
  const map = new Map()
  const eventRows = (events || []).map((event, index) => ({
    event,
    index,
    ts: toTimestamp(event?.ts),
  }))

  for (let i = 0; i < turns.length; i += 1) {
    const turn = turns[i]
    if (turn.role !== 'assistant') continue

    let userIndex = -1
    for (let j = i - 1; j >= 0; j -= 1) {
      if (turns[j].role === 'user') {
        userIndex = j
        break
      }
    }
    if (userIndex === -1) continue

    const startTs = toTimestamp(turns[userIndex].ts)
    const endTs = toTimestamp(turn.ts)
    const scopedEvents = eventRows
      .filter((row) => {
        if (Number.isNaN(startTs)) return false
        if (Number.isNaN(row.ts)) return false
        if (row.ts < startTs) return false
        if (!Number.isNaN(endTs) && row.ts > endTs) return false
        return true
      })
      .map((row) => row.event)

    map.set(buildTurnKey(turn, i), buildProcessSteps(scopedEvents, false))
  }

  return map
}

function buildTurnKey(turn, index = 0) {
  return `${turn.ts || 'no-ts'}-${turn.role || 'unknown'}-${turn.content || ''}-${index}`
}

function mergeTurns(baseTurns, extraTurn) {
  const tail = baseTurns.slice(-2)
  const duplicate = tail.some((item) => item.role === extraTurn.role && item.content === extraTurn.content)
  return duplicate ? baseTurns : [...baseTurns, extraTurn]
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

function SectionToggle({ open, count, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="max-w-[92px] shrink-0 truncate rounded-full bg-white/[0.06] px-2.5 py-1 text-[11px] text-white/55 transition hover:bg-white/[0.1] light:bg-black/6 light:text-zinc-500"
      title={open ? `Hide ${count ?? ''}`.trim() : `Show ${count ?? ''}`.trim()}
    >
      {open ? `Hide ${count ?? ''}`.trim() : `Show ${count ?? ''}`.trim()}
    </button>
  )
}

export default function SessionsPage({ runtime }) {
  const [sessions, setSessions] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [snapshot, setSnapshot] = useState(null)
  const [liveEvents, setLiveEvents] = useState([])
  const [streamTurns, setStreamTurns] = useState([])
  const [assistantDraft, setAssistantDraft] = useState(null)
  const [pendingSnapshot, setPendingSnapshot] = useState(null)
  const [requirement, setRequirement] = useState('')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [eventsOpen, setEventsOpen] = useState(false)
  const [overviewOpen, setOverviewOpen] = useState(true)
  const [outputsOpen, setOutputsOpen] = useState(true)
  const [activityOpen, setActivityOpen] = useState(true)
  const [chatScrolling, setChatScrolling] = useState(false)
  const chatScrollRef = useRef(null)
  const shouldAutoScrollRef = useRef(true)
  const typingTimerRef = useRef(null)
  const scrollStateTimerRef = useRef(null)

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

  useEffect(() => {
    return () => {
      if (typingTimerRef.current) window.clearTimeout(typingTimerRef.current)
      if (scrollStateTimerRef.current) window.clearTimeout(scrollStateTimerRef.current)
    }
  }, [])

  useEffect(() => {
    if (!pendingSnapshot) return
    if (assistantDraft && assistantDraft.status !== 'done') return
    setSnapshot(pendingSnapshot)
    setPendingSnapshot(null)
    setStreamTurns([])
    setAssistantDraft(null)
    setLiveEvents([])
  }, [assistantDraft, pendingSnapshot])

  const effectiveSnapshot = pendingSnapshot || snapshot

  const processEvents = useMemo(() => {
    const persistedEvents = snapshot?.events || []
    if (liveEvents.length > 0) return [...persistedEvents, ...liveEvents]
    return effectiveSnapshot?.events || persistedEvents
  }, [effectiveSnapshot, liveEvents, snapshot])

  const turns = useMemo(() => {
    let items = snapshot?.turns || []
    for (const turn of streamTurns) items = mergeTurns(items, turn)
    if (assistantDraft) {
      items = [
        ...items,
        {
          role: 'assistant',
          content: assistantDraft.content,
          ts: assistantDraft.ts,
          loading: assistantDraft.status === 'loading' || assistantDraft.status === 'streaming',
        },
      ]
    }
    return items
  }, [assistantDraft, snapshot, streamTurns])
  const toolRows = effectiveSnapshot?.tool_results || []
  const outputFiles = effectiveSnapshot?.outputs || []
  const workflowTasks = effectiveSnapshot?.workflow?.tasks || []
  const recentTools = toolRows.slice(-5).reverse()
  const sessionMeta = effectiveSnapshot?.session || snapshot?.session || {}
  const latestEvent = processEvents[processEvents.length - 1]
  const processSteps = useMemo(() => buildProcessSteps(liveEvents, running), [liveEvents, running])
  const assistantStepMap = useMemo(() => buildAssistantStepMap(turns, effectiveSnapshot?.events || snapshot?.events || []), [effectiveSnapshot, snapshot, turns])

  function revealReply(content, ts) {
    if (typingTimerRef.current) window.clearTimeout(typingTimerRef.current)
    const fullText = content || ''
    if (!fullText) {
      setAssistantDraft({ content: '', ts, status: 'done' })
      return
    }

    let cursor = 0
    const chunkSize = Math.max(6, Math.ceil(fullText.length / 90))

    const step = () => {
      cursor = Math.min(fullText.length, cursor + chunkSize)
      setAssistantDraft({
        content: fullText.slice(0, cursor),
        ts,
        status: cursor >= fullText.length ? 'done' : 'streaming',
      })
      if (cursor < fullText.length) {
        typingTimerRef.current = window.setTimeout(step, 16)
      }
    }

    setAssistantDraft({ content: '', ts, status: 'streaming' })
    step()
  }

  async function handleRun(event) {
    event.preventDefault()
    const trimmed = requirement.trim()
    if (!trimmed || running) return
    const localTs = new Date().toISOString()
    setRunning(true)
    setError('')
    setLiveEvents([])
    setRequirement('')
    setPendingSnapshot(null)
    setStreamTurns([{ role: 'user', content: trimmed, ts: localTs }])
    setAssistantDraft({ content: '', ts: localTs, status: 'loading' })

    const title = snapshot?.session?.title || sessions.find((item) => item.id === selectedId)?.title || 'web-console'

    try {
      await chatStream(
        {
          requirement: trimmed,
          title,
          session_id: selectedId || undefined,
          reuse_session_by_title: !selectedId,
        },
        {
          onEvent: (payload) => {
            setLiveEvents((prev) => [...prev, payload])
            if (payload.session_id) setSelectedId(payload.session_id)
            if (payload.type === 'turn' && payload.turn?.role === 'user') {
              setStreamTurns((prev) => mergeTurns(prev, payload.turn))
            }
            if (payload.type === 'reply_start') {
              setAssistantDraft((prev) => prev || { content: '', ts: payload.ts || localTs, status: 'loading' })
            }
            if (payload.type === 'final_reply') {
              const replyText = payload.reply || payload.turn?.content || ''
              revealReply(replyText, payload.turn?.ts || payload.ts || new Date().toISOString())
            }
          },
          onFinal: async ({ snapshot: finalSnapshot, result }) => {
            setPendingSnapshot(finalSnapshot)
            setSelectedId(result.session_id)
            await loadSessions(result.session_id)
          },
          onError: (payload) => {
            setError(payload.message || 'Runtime error')
            setAssistantDraft(null)
            setPendingSnapshot(null)
          },
        },
      )
    } catch (err) {
      setError(err.message || 'Failed to run requirement')
      setAssistantDraft(null)
      setPendingSnapshot(null)
    } finally {
      setRunning(false)
    }
  }

  useEffect(() => {
    const el = chatScrollRef.current
    if (!el || !shouldAutoScrollRef.current) return
    el.scrollTop = el.scrollHeight
  }, [assistantDraft?.content, processEvents.length, turns.length])

  function handleChatScroll(event) {
    const el = event.currentTarget
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    shouldAutoScrollRef.current = distanceToBottom < 96
    setChatScrolling(true)
    if (scrollStateTimerRef.current) window.clearTimeout(scrollStateTimerRef.current)
    scrollStateTimerRef.current = window.setTimeout(() => setChatScrolling(false), 240)
  }

  function handleRequirementKeyDown(event) {
    if (event.key !== 'Enter' || event.shiftKey) return
    event.preventDefault()
    event.currentTarget.form?.requestSubmit()
  }

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden rounded-[28px] border border-white/[0.05] bg-white/[0.035] p-3 light:border-black/8 light:bg-white">
      <DrawerToggle open={drawerOpen} onClick={() => setDrawerOpen((v) => !v)} />

      <div className={`grid min-h-0 flex-1 gap-3 overflow-hidden transition-all duration-300 ${drawerOpen ? 'xl:grid-cols-[1fr_280px]' : 'grid-cols-1'}`}>
        <section className="grid min-h-0 h-[86vh] grid-rows-[minmax(0,1fr)_auto] gap-3 overflow-hidden">
          <div className="grid min-h-0 gap-3 overflow-hidden xl:grid-cols-[minmax(0,1.25fr)_312px]">
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

              <div ref={chatScrollRef} onScroll={handleChatScroll} className={`scroll-ghost min-h-0 flex-1 space-y-4 overflow-auto pr-1 ${chatScrolling ? 'scrolling' : ''}`}>
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
                    {turns.map((turn, index) => {
                      const isLatestAssistant = turn.role === 'assistant' && index === turns.length - 1
                      const persistedSteps = assistantStepMap.get(buildTurnKey(turn, index)) || []
                      const scopedSteps = isLatestAssistant && processSteps.length > 0 ? processSteps : persistedSteps
                      const showSteps = turn.role === 'assistant' && scopedSteps.length > 0
                      return (
                      <div
                        key={buildTurnKey(turn, index)}
                        className={`rounded-2xl border px-4 py-3 ${turn.role === 'user'
                            ? 'border-[#c2714c]/45 bg-[#c2714c] text-white shadow-[inset_0_1px_rgba(255,255,255,0.08)]'
                            : 'border-white/[0.04] bg-black/24 light:border-black/8 light:bg-white'
                          }`}
                      >
                        <div className="mb-2 flex items-center justify-between gap-3">
                          <span
                            className={`text-[11px] uppercase tracking-[0.22em] ${turn.role === 'user' ? 'font-semibold text-white/80' : 'text-white/30 light:text-zinc-500'
                              }`}
                          >
                            {turn.role}
                          </span>
                          <span
                            className={`text-[11px] ${turn.role === 'user' ? 'text-white/72' : 'text-white/26 light:text-zinc-400'
                              }`}
                          >
                            {formatTime(turn.ts)}
                          </span>
                        </div>
                        {showSteps && (
                          <div className="mt-4 rounded-2xl border border-white/[0.04] bg-black/18 p-4 light:border-black/8 light:bg-zinc-100">
                            <div className="mb-3 flex items-center justify-between">
                              <p className="text-xs uppercase tracking-[0.24em] text-white/30 light:text-zinc-500">Process Steps</p>
                              <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-[11px] text-white/55 light:bg-black/6 light:text-zinc-500">
                                {scopedSteps.length}
                              </span>
                            </div>
                            <div className="space-y-0">
                              {scopedSteps.map((step, stepIndex) => (
                                <div key={step.id} className="flex gap-3">
                                  <div className="flex w-5 shrink-0 flex-col items-center">
                                    <span
                                      className={`mt-1 h-2.5 w-2.5 rounded-full ${
                                        step.state === 'error' ? 'bg-rust-400' : step.state === 'active' ? 'bg-mint shadow-[0_0_0_4px_rgba(121,210,176,0.12)]' : 'bg-white/30 light:bg-zinc-400'
                                      }`}
                                    />
                                    {stepIndex < processSteps.length - 1 && <span className="mt-1 h-full w-px bg-white/[0.08] light:bg-black/8" />}
                                  </div>
                                  <div className="min-w-0 flex-1 pb-4">
                                    <div className="mb-1 flex items-center justify-between gap-3">
                                      <p className="min-w-0 truncate text-sm font-medium text-paper-50 light:text-zinc-900">{step.title}</p>
                                      <span className="shrink-0 text-[11px] text-white/30 light:text-zinc-500">{formatTime(step.ts)}</span>
                                    </div>
                                    <p className="whitespace-pre-wrap break-words text-sm leading-6 text-white/62 light:text-zinc-700">{step.detail}</p>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        <p className={`${showSteps ? 'mt-4' : ''} whitespace-pre-wrap break-words text-sm leading-6 ${turn.role === 'user' ? 'text-white' : 'text-white/78 light:text-zinc-700'}`}>
                          {turn.content}
                          {turn.loading && (
                            <span className="ml-2 inline-flex items-center gap-1 align-middle text-white/42 light:text-zinc-400">
                              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                              <span className="text-xs">{assistantDraft?.status === 'loading' ? 'thinking' : 'streaming'}</span>
                            </span>
                          )}
                        </p>
                      </div>
                    )})}
                  </div>
                </div>

              </div>
            </div>

            <aside className="min-h-0 overflow-hidden rounded-[24px] border border-white/[0.05] bg-black/14 light:border-black/0 light:bg-transparent">
              
              
              
              <div className="scroll-soft grid h-full min-h-0 gap-3 overflow-auto pr-1 xl:grid-rows-[auto_auto_auto_minmax(0,1fr)]">
                
                
                
                
                <div className="min-w-0 rounded-[24px] border border-white/[0.05] bg-black/22 p-4 light:border-black/8 light:bg-zinc-50">
                  <div className="mb-4 flex items-center justify-between">
                    <div className="min-w-0 pr-2">
                      <p className="text-xs uppercase tracking-[0.28em] text-white/30 light:text-zinc-500">Overview</p>
                      <h2 className="mt-2 text-lg font-semibold text-paper-50 light:text-zinc-900">会话概览</h2>
                    </div>
                    <SectionToggle open={overviewOpen} count={running ? 'running' : 'ready'} onClick={() => setOverviewOpen((v) => !v)} />
                  </div>
                  {overviewOpen && (
                    <div className="grid gap-2">
                      <div className="rounded-2xl border border-white/[0.04] bg-black/24 px-4 py-3 light:border-black/8 light:bg-white">
                        <p className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">Title</p>
                        <p className="mt-2 text-sm text-paper-50 light:text-zinc-900">{sessionMeta.title || 'web-console'}</p>
                      </div>
                      <div className="rounded-2xl border border-white/[0.04] bg-black/24 px-4 py-3 light:border-black/8 light:bg-white">
                        <p className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">Updated</p>
                        <p className="mt-2 text-sm text-paper-50 light:text-zinc-900">{formatTime(sessionMeta.updated_at)}</p>
                      </div>
                      <div className="rounded-2xl border border-white/[0.04] bg-black/24 px-4 py-3 light:border-black/8 light:bg-white">
                        <p className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">Latest Status</p>
                        <p className="mt-2 text-sm text-paper-50 light:text-zinc-900">{latestEvent ? formatEvent(latestEvent) : 'No activity yet.'}</p>
                      </div>
                      {workflowTasks.length > 0 && (
                        <div className="rounded-2xl border border-white/[0.04] bg-black/24 px-4 py-3 light:border-black/8 light:bg-white">
                          <p className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">Current Plan</p>
                          <p className="mt-2 text-sm text-paper-50 light:text-zinc-900">{workflowTasks.map((task) => task.kind).join(' -> ')}</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="min-w-0 rounded-[24px] border border-white/[0.05] bg-black/22 p-4 light:border-black/8 light:bg-zinc-50">
                  <div className="mb-4 flex items-center justify-between">
                    <div className="min-w-0 pr-2">
                      <p className="text-xs uppercase tracking-[0.28em] text-white/30 light:text-zinc-500">Output</p>
                      <h2 className="mt-2 text-lg font-semibold text-paper-50 light:text-zinc-900">产物文件</h2>
                    </div>
                    <SectionToggle open={outputsOpen} count={outputFiles.length} onClick={() => setOutputsOpen((v) => !v)} />
                  </div>
                  {outputsOpen && (
                    <>
                      <div className="mb-3 rounded-2xl border border-white/[0.04] bg-black/24 px-4 py-3 light:border-black/8 light:bg-white">
                        <p className="text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">Output Dir</p>
                        <p className="mt-2 break-all font-mono text-xs text-white/62 light:text-zinc-700">{effectiveSnapshot?.task_output_dir || '-'}</p>
                      </div>
                      <div className="space-y-3">
                        {outputFiles.length === 0 && (
                          <div className="rounded-2xl border border-white/[0.04] bg-black/24 px-4 py-3 text-sm text-white/50 light:border-black/8 light:bg-white light:text-zinc-600">
                            当前这轮没有扫描到产物文件。如果目录里实际有文件，说明后端快照拿到的不是你期望的那一轮输出。
                          </div>
                        )}
                        {outputFiles.slice(0, 6).map((file) => (
                          <div key={file.path} className="rounded-2xl border border-white/[0.04] bg-black/24 p-4 light:border-black/8 light:bg-white">
                            <div className="flex items-center justify-between gap-3">
                              <p className="min-w-0 break-all font-medium text-paper-50 light:text-zinc-900">{file.relative_path}</p>
                              <span className="text-xs text-white/36 light:text-zinc-500">{formatBytes(file.size)}</span>
                            </div>
                            <p className="mt-2 break-all font-mono text-xs text-white/34 light:text-zinc-500">{file.path}</p>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>

                <div className="min-w-0 rounded-[24px] border border-white/[0.05] bg-black/22 p-4 light:border-black/8 light:bg-zinc-50">
                  <div className="mb-4 flex items-center justify-between">
                    <div className="min-w-0 pr-2">
                      <p className="text-xs uppercase tracking-[0.28em] text-white/30 light:text-zinc-500">Recent Activity</p>
                      <h2 className="mt-2 text-lg font-semibold text-paper-50 light:text-zinc-900">最近动作</h2>
                    </div>
                    <SectionToggle open={activityOpen} count={recentTools.length} onClick={() => setActivityOpen((v) => !v)} />
                  </div>
                  {activityOpen && (
                    <div className="space-y-3">
                      {recentTools.length === 0 && (
                        <div className="rounded-2xl border border-white/[0.04] bg-black/24 px-4 py-3 text-sm text-white/50 light:border-black/8 light:bg-white light:text-zinc-600">
                          No recent tool activity.
                        </div>
                      )}
                      {recentTools.map((row) => {
                        const data = (row.result || {}).data || {}
                        return (
                          <div key={`${row.step_id}-${row.tool}-${row.ts}`} className="rounded-2xl border border-white/[0.04] bg-black/24 p-4 light:border-black/8 light:bg-white">
                            <div className="flex items-center justify-between gap-3">
                              <p className="min-w-0 break-all font-mono text-sm text-paper-50 light:text-zinc-900">{row.tool}</p>
                              <span className="text-[11px] text-white/36 light:text-zinc-500">{row.step_id}</span>
                            </div>
                            <p className="mt-2 break-all text-sm text-white/62 light:text-zinc-700">{data.path || data.script || formatTime(row.ts)}</p>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>

                <div className={`min-w-0 ${eventsOpen ? 'h-[400px]' : 'h-[120px]'} rounded-[24px] border border-white/[0.05] bg-black/22 p-4 light:border-black/8 light:bg-zinc-50`}>
                  <div className="mb-4 flex items-center justify-between">
                    <div className="min-w-0 pr-2">
                      <p className="text-xs uppercase tracking-[0.28em] text-white/30 light:text-zinc-500">Runtime Events</p>
                      <h2 className="mt-2 text-lg font-semibold text-paper-50 light:text-zinc-900">运行日志</h2>
                    </div>
                    <SectionToggle open={eventsOpen} count={processEvents.length} onClick={() => setEventsOpen((v) => !v)} />
                  </div>
                  {eventsOpen ? (
                    <div className="space-y-3">
                      <div className="rounded-2xl p-3">
                        <div className="scroll-soft max-h-[34vh] space-y-2 overflow-auto pr-1">
                          {processEvents.length === 0 && (
                            <div className="rounded-2xl bg-black/24 px-4 py-3 text-sm text-white/50 light:bg-white light:text-zinc-600">
                              No events yet.
                            </div>
                          )}
                          {processEvents.map((eventItem, index) => (
                            <div key={`${eventItem.ts || index}-${eventItem.type}`} className="min-w-0 rounded-2xl border border-white/[0.04] bg-black/24 px-3 py-2 light:border-black/8 light:bg-white">
                              <div className="mb-1 flex min-w-0 flex-col gap-1">
                                <span className="truncate text-[11px] uppercase tracking-[0.22em] text-white/30 light:text-zinc-500">
                                  {eventItem.type}
                                </span>
                                <span className="text-[11px] text-white/26 light:text-zinc-400">{formatTime(eventItem.ts)}</span>
                              </div>
                              <p className="whitespace-pre-wrap break-words text-sm leading-6 text-white/68 light:text-zinc-700">{formatEvent(eventItem)}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-2xl border border-white/[0.04] bg-black/24 px-4 py-3 text-sm text-white/50 light:border-black/8 light:bg-white light:text-zinc-600">
                      点击 `Show {processEvents.length}` 查看原始运行日志。
                    </div>
                  )}
                </div>






              </div>





            </aside>
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
              onKeyDown={handleRequirementKeyDown}
              rows={4}
              disabled={running}
              className="w-full resize-y rounded-3xl border border-white/[0.05] bg-black/24 p-4 text-sm leading-6 text-white/82 outline-none placeholder:text-white/25 light:border-black/8 light:bg-white light:text-zinc-900 light:placeholder:text-zinc-400"
              placeholder="输入你的任务需求，Enter 发送，Shift+Enter 换行"
            />

            {error && (
              <div className="mt-4 rounded-2xl border border-rust-500/20 bg-rust-500/10 px-4 py-3 text-sm text-rust-200">
                {error}
              </div>
            )}
          </form>
        </section>

        <aside className={`overflow-scroll rounded-[24px] border border-white/[0.05] bg-black/28 transition-all duration-300 light:border-black/8 light:bg-zinc-50 ${drawerOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0 xl:w-0'}`}>
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
                  className={`w-full rounded-[20px] border p-4 text-left transition ${row.id === selectedId
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
                  <p className="mt-3 text-[11px] text-white/32 light:text-zinc-500">{formatTime(row.updated_at)}</p>
                </button>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </div>
  )
}
