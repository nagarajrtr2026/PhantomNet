'use client'

import { useMemo } from 'react'
import { Activity, AlertTriangle, FileText, Radio, Terminal, Wifi, WifiOff } from 'lucide-react'
import { useWebSocket } from '@/hooks/useWebSocket'
import type { TelemetryEvent } from '@/types/events'
import { HackerMonitor } from '@/components/hacker-monitor/hacker-monitor'
import { LlmMonitor } from '@/components/llm-monitor/llm-monitor'
import { TelemetryPanel } from '@/components/telemetry/telemetry-panel'
import { SecurityStatus } from '@/components/security-status/security-status'

function StatusChip({ connected, configured }: { connected: boolean; configured: boolean }) {
  const label = !configured ? 'Not configured' : connected ? 'Live connection' : 'Connection lost'
  return <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium ${connected ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border-amber-500/30 bg-amber-500/10 text-amber-300'}`}><span className={`size-1.5 rounded-full ${connected ? 'bg-emerald-400' : 'bg-amber-400'}`} />{label}</div>
}

function Metric({ icon: Icon, label, value, detail }: { icon: typeof Activity; label: string; value: string; detail: string }) {
  return <div className="rounded-xl border border-white/[0.09] bg-white/[0.055] p-4 shadow-[0_16px_40px_rgb(0_0_0_/_0.18)] backdrop-blur-xl"><div className="flex items-center justify-between text-zinc-400"><span className="text-[11px] font-medium uppercase tracking-[0.16em]">{label}</span><Icon className="size-4 text-purple-300" /></div><div className="mt-3 text-2xl font-semibold tracking-tight text-white">{value}</div><p className="mt-1 text-xs text-zinc-500">{detail}</p></div>
}

export function Dashboard() {
  const { status, events, isConfigured } = useWebSocket()
  const connected = status === 'open'
  const sessions = useMemo(() => new Set(events.filter((event) => event.sessionId).map((event) => event.sessionId)).size, [events])
  const eventCounts = useMemo(() => ({ commands: events.filter((e) => e.type === 'hacker_command').length, files: events.filter((e) => e.type === 'file_access').length, queries: events.filter((e) => e.type === 'sql_query').length, network: events.filter((e) => e.type === 'network_event').length }), [events])

  return <div className="min-h-screen bg-transparent text-zinc-100 selection:bg-purple-400/20">
    <header className="border-b border-white/[0.08] bg-black/20 backdrop-blur-xl"><div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-5 py-4 lg:px-8"><div className="flex items-center gap-3"><div><div className="flex items-center gap-2"><h1 className="text-sm font-semibold tracking-wide text-zinc-100">PHANTOM<span className="text-cyan-700">NET</span></h1><span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[9px] text-zinc-400">SOC / P1</span></div><p className="mt-0.5 text-[11px] text-zinc-400">Generative cyber-deception control plane</p></div></div><div className="flex items-center gap-3"><div className="hidden items-center gap-2 text-xs text-zinc-400 sm:flex"><span className="font-mono">UTC</span><span className="text-slate-700">stream time</span></div><StatusChip connected={connected} configured={isConfigured} /></div></div></header>
    <main className="mx-auto max-w-[1600px] px-5 py-7 lg:px-8">
      <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><div className="mb-2 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.18em] text-purple-300"><Radio className="size-3.5" /> Operations view</div><h2 className="text-2xl font-semibold tracking-tight text-zinc-100">Security overview</h2><p className="mt-1 text-sm text-zinc-400">Monitor deception surfaces and attacker behavior as it arrives.</p></div><div className="flex items-center gap-2 text-xs text-zinc-400"><span className={`size-2 rounded-full ${connected ? 'bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,.8)]' : 'bg-zinc-600'}`} />{connected ? 'Receiving telemetry' : isConfigured ? 'Waiting for telemetry' : 'Telemetry endpoint not configured'}</div></div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric icon={Activity} label="Active sessions" value={String(sessions).padStart(2, '0')} detail="Observed in current stream" /><Metric icon={Terminal} label="Commands" value={String(eventCounts.commands).padStart(2, '0')} detail="Since this view opened" /><Metric icon={FileText} label="File access" value={String(eventCounts.files).padStart(2, '0')} detail="Read / write activity" /><Metric icon={Wifi} label="Network events" value={String(eventCounts.network).padStart(2, '0')} detail={`${eventCounts.queries} SQL queries observed`} /></div>
      {!isConfigured && <div className="mt-5 flex items-start gap-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-4 py-3 text-sm text-amber-200"><AlertTriangle className="mt-0.5 size-4 shrink-0" /><div><p className="font-medium">Telemetry connection is not configured</p><p className="mt-0.5 text-xs text-amber-200/60">Set NEXT_PUBLIC_WS_URL to connect this dashboard to the PhantomNet WebSocket service. No events are simulated in this view.</p></div></div>}
      {status === 'error' || status === 'closed' && isConfigured ? <div className="mt-5 flex items-center gap-2 rounded-xl border border-red-400/20 bg-red-400/[0.06] px-4 py-3 text-xs text-red-200"><WifiOff className="size-4" /> Connection unavailable. Automatic reconnect is active.</div> : null}
      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,.65fr)]"><HackerMonitor events={events} /><LlmMonitor events={events} /></div>
      <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,.65fr)]"><TelemetryPanel events={events} /><SecurityStatus events={events} /></div>
    </main>
    <footer className="mx-auto flex max-w-[1600px] items-center justify-between border-t border-white/[0.06] px-5 py-5 text-[11px] text-zinc-600 lg:px-8"><span>PHANTOMNET / FRONTEND PHASE 1</span><span className="font-mono">API: {process.env.NEXT_PUBLIC_API_URL ? 'configured' : 'not configured'}</span></footer>
  </div>
}
