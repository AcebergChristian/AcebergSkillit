export const overviewCards = [
  {
    title: 'Active Sessions',
    value: '12',
    delta: '+3 today',
    tone: 'mint',
  },
  {
    title: 'Skills Loaded',
    value: '9',
    delta: '2 learned',
    tone: 'sky',
  },
  {
    title: 'Queued Tasks',
    value: '4',
    delta: '1 blocked',
    tone: 'rust',
  },
]

export const sessionRows = [
  {
    id: 's_067a97de74',
    title: 'News Research Workflow',
    updatedAt: '2026-04-29 10:24',
    status: 'running',
    summary: 'Collecting today\'s news, exporting to xlsx, validating output.',
  },
  {
    id: 's_d6cd1fa948',
    title: 'Excel Export Trial',
    updatedAt: '2026-04-28 20:31',
    status: 'completed',
    summary: 'Generated workbook artifact and promoted reusable task pattern.',
  },
  {
    id: 's_2bf7ea006c',
    title: 'Runtime Sandbox',
    updatedAt: '2026-04-28 10:24',
    status: 'idle',
    summary: 'Smoke-tested output routing and execution environment.',
  },
]

export const skillRows = [
  {
    id: 'research',
    name: 'Research',
    type: 'system',
    triggers: ['新闻', '百度', 'search'],
    status: 'loaded',
    description: 'Collects fresh external information and normalizes structured findings.',
  },
  {
    id: 'data_export',
    name: 'Data Export',
    type: 'system',
    triggers: ['excel', 'xlsx', 'csv'],
    status: 'loaded',
    description: 'Writes structured results into exportable artifacts.',
  },
  {
    id: 'learned__generated_script',
    name: 'Generated Script',
    type: 'learned',
    triggers: ['新闻', 'excel'],
    status: 'pending review',
    description: 'Candidate learned from a successful session. Awaiting promotion confirmation.',
  },
]

export const recentEvents = [
  '[session] start session=s_067a97de74',
  '[task_dir] output/s_067a97de74/20260429_101800',
  '[workflow] research -> codegen -> export -> execute',
  '[tool] s4 write_text ok path=generated_script.py',
  '[run] generated_script.py exit_code=0',
]

export const queueItems = [
  {
    title: 'Today\'s news to Excel',
    owner: 'research skill',
    step: 'execute',
    state: 'hot',
  },
  {
    title: 'Promote reusable exporter',
    owner: 'data_export skill',
    step: 'approval',
    state: 'cool',
  },
]
