import React, { useMemo, useState, useEffect, useRef } from 'react';
import {
  ShieldAlert,
  GitCommit,
  RefreshCw,
  Search,
  CheckCircle2,
  Cpu,
  Terminal,
  Copy,
  Check,
  Activity,
  Filter,
  ExternalLink,
  Upload,
  RotateCcw,
} from 'lucide-react';
import rawLedger from '@ledger';

const ACTION_META = {
  bisect_and_block: {
    label: 'Bisect & Block',
    badge: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
    dot: 'bg-rose-400',
  },
  rerun_and_quarantine: {
    label: 'Rerun & Quarantine',
    badge: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    dot: 'bg-amber-400',
  },
  retry_env_runner: {
    label: 'Retry Env Runner',
    badge: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
    dot: 'bg-sky-400',
  },
};

function parseRationale(rationale = '') {
  const isFallback =
    rationale.includes('used deterministic quarantine rule') ||
    rationale.includes('All Gemini models busy/unavailable');

  if (!isFallback) {
    return { engine: 'Gemini Agent', cleanText: rationale };
  }

  return {
    engine: 'ML Deterministic Fallback',
    cleanText:
      'Gemini API rate-limited/unavailable — deterministic LightGBM + rule engine executed quarantine decision.',
  };
}

function formatRationaleText(rationale = '') {
  return rationale.replace(/\\n/g, '\n');
}

function hydrateEntries(list) {
  return [...list].reverse().map((item, idx) => ({
    id: `${item.run_id}-${item.timestamp}-${idx}`,
    ...item,
    parsed: parseRationale(item.rationale),
  }));
}

export default function App() {
  const [entries, setEntries] = useState(() => hydrateEntries(rawLedger));
  const [search, setSearch] = useState('');
  const [actionFilter, setActionFilter] = useState('all');
  const [selected, setSelected] = useState(() => hydrateEntries(rawLedger)[0] || null);
  const [copiedCmd, setCopiedCmd] = useState(false);
  const [ghRuns, setGhRuns] = useState([]);
  const fileInputRef = useRef(null);

  useEffect(() => {
    fetch('https://api.github.com/repos/aryanrath51/flaky-sentinel/actions/runs?per_page=5')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.workflow_runs) setGhRuns(data.workflow_runs);
      })
      .catch(() => {});
  }, []);

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const parsedJson = JSON.parse(event.target.result);
        if (Array.isArray(parsedJson)) {
          const next = hydrateEntries(parsedJson);
          setEntries(next);
          setSelected(next[0] || null);
        }
      } catch {
        alert('Invalid JSON file. Please upload a valid quarantine_ledger.json array.');
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const handleClear = () => {
    setEntries([]);
    setSelected(null);
  };

  const handleRestore = () => {
    const restored = hydrateEntries(rawLedger);
    setEntries(restored);
    setSelected(restored[0] || null);
  };

  const stats = useMemo(() => {
    const total = entries.length;
    const blocked = entries.filter((e) => e.action === 'bisect_and_block').length;
    const flaky = entries.filter((e) => e.action === 'rerun_and_quarantine').length;
    const env = entries.filter((e) => e.action === 'retry_env_runner').length;
    const aiDriven = entries.filter((e) => e.parsed.engine === 'Gemini Agent').length;
    return { total, blocked, flaky, env, aiDriven };
  }, [entries]);

  const filtered = useMemo(() => {
    return entries.filter((item) => {
      const matchesAction = actionFilter === 'all' || item.action === actionFilter;
      const q = search.toLowerCase().trim();
      const matchesSearch =
        !q ||
        item.target_job.toLowerCase().includes(q) ||
        item.head_sha.toLowerCase().includes(q) ||
        String(item.run_id).includes(q) ||
        item.rationale.toLowerCase().includes(q);
      return matchesAction && matchesSearch;
    });
  }, [entries, actionFilter, search]);

  const bisectCommand = selected
    ? `git bisect start ${selected.head_sha} HEAD~10\npytest -k "${selected.target_job}"\ngit bisect reset`
    : '';

  const copyCommand = () => {
    navigator.clipboard.writeText(bisectCommand);
    setCopiedCmd(true);
    setTimeout(() => setCopiedCmd(false), 1800);
  };

  const selectedMeta = selected
    ? ACTION_META[selected.action] || {
        label: selected.action,
        badge: 'bg-slate-800 text-slate-300 border-slate-700',
        dot: 'bg-slate-400',
      }
    : null;

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100">
      {/* Top Bar */}
      <header className="border-b border-slate-800/80 bg-[#0d1322]/90 backdrop-blur sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-6 py-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-indigo-500/15 border border-indigo-500/30 text-indigo-400">
              <ShieldAlert className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-lg font-bold tracking-tight text-white">Flaky Sentinel</h1>
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-medium">
                  LightGBM + Gemini Agent
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Autonomous CI Failure Triage &amp; Quarantine Ledger • aryanrath51/flaky-sentinel
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              onChange={handleFileUpload}
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-lg bg-indigo-500/15 hover:bg-indigo-500/25 border border-indigo-500/30 text-indigo-300 transition cursor-pointer"
            >
              <Upload className="w-3.5 h-3.5" />
              Import Ledger JSON
            </button>

            {entries.length > 0 ? (
              <button
                onClick={handleClear}
                className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-lg bg-slate-800/70 hover:bg-slate-800 border border-slate-700 text-slate-300 transition cursor-pointer"
              >
                Clear View
              </button>
            ) : (
              <button
                onClick={handleRestore}
                className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 transition cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Restore Seed Ledger
              </button>
            )}

            <a
              href="https://github.com/aryanrath51/flaky-sentinel/actions"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 text-xs font-medium px-3.5 py-2 rounded-lg bg-slate-800/80 hover:bg-slate-800 border border-slate-700 text-slate-200 transition"
            >
              <Activity className="w-3.5 h-3.5 text-emerald-400" />
              Live GitHub Actions
              <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
            </a>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-6">
        {/* KPI Cards */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="p-5 rounded-2xl bg-[#0f172a] border border-slate-800">
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>TOTAL TRIAGED EVENTS</span>
              <Cpu className="w-4 h-4 text-indigo-400" />
            </div>
            <div className="mt-3 text-3xl font-bold text-white">{stats.total}</div>
            <p className="mt-1 text-xs text-slate-400">
              {stats.aiDriven} Gemini LLM • {stats.total - stats.aiDriven} ML Fallback
            </p>
          </div>

          <div className="p-5 rounded-2xl bg-[#0f172a] border border-slate-800">
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>REGRESSIONS BLOCKED</span>
              <ShieldAlert className="w-4 h-4 text-rose-400" />
            </div>
            <div className="mt-3 text-3xl font-bold text-rose-400">{stats.blocked}</div>
            <p className="mt-1 text-xs text-slate-400">Action: bisect_and_block</p>
          </div>

          <div className="p-5 rounded-2xl bg-[#0f172a] border border-slate-800">
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>FLAKY QUARANTINED</span>
              <RefreshCw className="w-4 h-4 text-amber-400" />
            </div>
            <div className="mt-3 text-3xl font-bold text-amber-400">{stats.flaky}</div>
            <p className="mt-1 text-xs text-slate-400">Action: rerun_and_quarantine</p>
          </div>

          <div className="p-5 rounded-2xl bg-[#0f172a] border border-slate-800">
            <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
              <span>ENV / INFRA RETRIES</span>
              <CheckCircle2 className="w-4 h-4 text-sky-400" />
            </div>
            <div className="mt-3 text-3xl font-bold text-sky-400">{stats.env}</div>
            <p className="mt-1 text-xs text-slate-400">Action: retry_env_runner</p>
          </div>
        </section>

        {/* Live GitHub Runs Strip */}
        {ghRuns.length > 0 && (
          <section className="p-4 rounded-2xl bg-[#0f172a]/80 border border-slate-800 flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Recent GitHub Workflow Runs:
            </span>
            <div className="flex flex-wrap gap-2">
              {ghRuns.map((run) => (
                <a
                  key={run.id}
                  href={run.html_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700"
                >
                  <span
                    className={`w-2 h-2 rounded-full ${
                      run.conclusion === 'success'
                        ? 'bg-emerald-400'
                        : run.conclusion === 'failure'
                        ? 'bg-rose-400'
                        : 'bg-amber-400'
                    }`}
                  />
                  <span className="text-slate-200 font-medium">{run.name}</span>
                  <span className="text-slate-500">#{run.run_number}</span>
                </a>
              ))}
            </div>
          </section>
        )}

        {/* Filters */}
        <section className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter by job, commit SHA, run ID, or rationale..."
              className="w-full pl-10 pr-4 py-2.5 text-sm rounded-xl bg-[#0f172a] border border-slate-800 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Filter className="w-4 h-4 text-slate-500 mr-1" />
            {[
              { id: 'all', label: 'All Actions' },
              { id: 'bisect_and_block', label: 'Bisect & Block' },
              { id: 'rerun_and_quarantine', label: 'Quarantine' },
              { id: 'retry_env_runner', label: 'Retry Env' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActionFilter(tab.id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition cursor-pointer ${
                  actionFilter === tab.id
                    ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40'
                    : 'bg-[#0f172a] text-slate-400 border-slate-800 hover:text-slate-200'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </section>

        {/* Master-Detail Grid */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Ledger Table */}
          <div className="lg:col-span-7 rounded-2xl bg-[#0f172a] border border-slate-800 overflow-hidden">
            <div className="px-5 py-3.5 border-b border-slate-800 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white">Quarantine Ledger History</h2>
              <span className="text-xs text-slate-400">{filtered.length} entries</span>
            </div>

            <div className="divide-y divide-slate-800/70 max-h-[540px] overflow-y-auto">
              {filtered.length === 0 ? (
                <div className="px-5 py-12 text-center text-xs text-slate-500">
                  No ledger entries in current view. Import a JSON artifact or click Restore Seed Ledger.
                </div>
              ) : (
                filtered.map((item) => {
                  const meta = ACTION_META[item.action] || {
                    label: item.action,
                    badge: 'bg-slate-800 text-slate-300 border-slate-700',
                    dot: 'bg-slate-400',
                  };
                  const isSelected = selected?.id === item.id;

                  return (
                    <button
                      key={item.id}
                      onClick={() => setSelected(item)}
                      className={`w-full text-left px-5 py-4 transition cursor-pointer flex items-start justify-between gap-4 ${
                        isSelected ? 'bg-indigo-500/10' : 'hover:bg-slate-800/40'
                      }`}
                    >
                      <div className="space-y-1.5 min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-sm font-semibold text-white">
                            {item.target_job}
                          </span>
                          <span
                            className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-0.5 rounded-full border font-medium ${meta.badge}`}
                          >
                            <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
                            {meta.label}
                          </span>
                          <span className="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                            {item.parsed.engine}
                          </span>
                        </div>

                        <p className="text-xs text-slate-400 line-clamp-2">{item.parsed.cleanText}</p>

                        <div className="flex items-center gap-3 text-[11px] text-slate-500 font-mono">
                          <span>Run #{item.run_id}</span>
                          <span className="inline-flex items-center gap-1">
                            <GitCommit className="w-3 h-3" />
                            {item.head_sha}
                          </span>
                          <span>{new Date(item.timestamp).toLocaleString()}</span>
                        </div>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {/* Triage Inspector */}
          <div className="lg:col-span-5 rounded-2xl bg-[#0f172a] border border-slate-800 p-5 space-y-5 h-fit">
            {selected && selectedMeta ? (
              <>
                <div className="flex items-start justify-between gap-3 border-b border-slate-800 pb-4">
                  <div>
                    <span className="text-xs uppercase tracking-wider text-indigo-400 font-semibold">
                      Triage Decision Inspector
                    </span>
                    <h3 className="text-lg font-bold font-mono text-white mt-0.5">
                      {selected.target_job}
                    </h3>
                  </div>
                  <div className="flex flex-col items-end gap-1.5">
                    <span className="font-mono text-xs px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-700 text-slate-300">
                      {selected.head_sha}
                    </span>
                    <span
                      className={`inline-flex items-center gap-1.5 text-[11px] px-2 py-0.5 rounded-full border font-medium ${selectedMeta.badge}`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${selectedMeta.dot}`} />
                      {selectedMeta.label}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="p-3 rounded-xl bg-slate-900/90 border border-slate-800">
                    <span className="text-slate-500 block">Workflow Run</span>
                    <span className="font-mono font-semibold text-slate-200 mt-1 block">
                      #{selected.run_id}
                    </span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-900/90 border border-slate-800">
                    <span className="text-slate-500 block">Decision Engine</span>
                    <span className="font-semibold text-slate-200 mt-1 block">
                      {selected.parsed.engine}
                    </span>
                  </div>
                </div>

                <div className="space-y-2">
                  <span className="text-xs font-semibold text-slate-300 block">
                    Agent &amp; ML Triage Rationale
                  </span>
                  <div className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800 text-xs text-slate-300 leading-relaxed max-h-44 overflow-y-auto whitespace-pre-wrap break-words">
                    {formatRationaleText(selected.rationale)}
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-300">
                      <Terminal className="w-3.5 h-3.5 text-indigo-400" />
                      Recommended Remediation CLI
                    </span>
                    <button
                      onClick={copyCommand}
                      className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 cursor-pointer"
                    >
                      {copiedCmd ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                      {copiedCmd ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                  <pre className="p-3.5 rounded-xl bg-[#070b14] border border-slate-800 text-xs font-mono text-emerald-300 overflow-x-auto">
                    {bisectCommand}
                  </pre>
                </div>
              </>
            ) : (
              <p className="text-sm text-slate-400">Select a ledger entry to inspect details.</p>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}