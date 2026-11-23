import json
from flask import Flask, jsonify, render_template_string, request
from src.config import CIFailureEvent, PROCESSED_DATA_DIR, settings
from src.pipeline import FlakySentinelPipeline

app = Flask(__name__)
pipeline = FlakySentinelPipeline()

HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Flaky Sentinel — ML + AI Agent CI Console</title>
  <style>
    :root {
      --bg: #0b0f17;
      --panel: #121826;
      --panel-2: #182032;
      --border: #243049;
      --text: #e6edf7;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --good: #22c55e;
      --warn: #f59e0b;
      --bad: #ef4444;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 24px;
    }
    .container { max-width: 1100px; margin: 0 auto; }
    header {
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
      gap: 12px; margin-bottom: 20px;
    }
    h1 { margin: 0; font-size: 1.4rem; }
    .sub { color: var(--muted); font-size: 0.9rem; margin-top: 4px; }
    .controls { display: flex; gap: 10px; }
    button {
      background: var(--panel-2); color: var(--text); border: 1px solid var(--border);
      padding: 9px 14px; border-radius: 8px; cursor: pointer; font-weight: 600;
    }
    button.primary { background: #0284c7; border-color: #38bdf8; color: #fff; }
    button:hover { filter: brightness(1.12); }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
    @media (max-width: 820px) { .grid { grid-template-columns: 1fr; } }
    .card {
      background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px;
    }
    .card h2 { margin: 0 0 12px; font-size: 1rem; color: var(--accent); }
    .metric-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 0.92rem; }
    .badge {
      display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.78rem; font-weight: 700;
      background: var(--panel-2); border: 1px solid var(--border);
    }
    .badge.flake { color: var(--warn); border-color: var(--warn); }
    .badge.reg { color: var(--bad); border-color: var(--bad); }
    ul { margin: 8px 0 0; padding-left: 18px; color: var(--muted); font-size: 0.9rem; }
    li { margin-bottom: 4px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
    th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
    th { color: var(--muted); font-size: 0.8rem; text-transform: uppercase; }
    pre {
      background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px;
      padding: 12px; overflow-x: auto; font-size: 0.82rem; color: #cbd5e1;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Flaky Sentinel</h1>
        <div class="sub">LightGBM Flakiness Predictor + Gemini Triage &amp; Quarantine Agents</div>
      </div>
      <div class="controls">
        <button class="primary" onclick="runScenario('sample')">Run Flake Sample</button>
        <button onclick="runScenario('regression')">Run Regression Sample</button>
        <button onclick="refreshLedger()">Refresh Ledger</button>
      </div>
    </header>

    <div class="grid">
      <div class="card">
        <h2>ML Risk Model (LightGBM)</h2>
        <div class="metric-row"><span>Flakiness Probability</span><strong id="flakeProb">—</strong></div>
        <div class="metric-row"><span>Regression Probability</span><strong id="regProb">—</strong></div>
        <div style="margin-top:10px; color:var(--muted); font-size:0.85rem;">Top Signals</div>
        <ul id="topSignals"><li>Run a scenario to inspect signals</li></ul>
      </div>

      <div class="card">
        <h2>Agent Triage &amp; Quarantine Action</h2>
        <div class="metric-row">
          <span>Category</span>
          <span id="triageCat" class="badge">—</span>
        </div>
        <div class="metric-row">
          <span>Quarantine Action</span>
          <strong id="qAction">—</strong>
        </div>
        <p id="qRationale" style="color:var(--muted); font-size:0.88rem; margin:10px 0 6px;">Select a scenario above to inspect agent reasoning.</p>
        <ul id="qSteps"></ul>
      </div>
    </div>

    <div class="card" style="margin-bottom: 20px;">
      <h2>Quarantine Ledger (<code>data/processed/quarantine_ledger.json</code>)</h2>
      <table>
        <thead>
          <tr>
            <th>Timestamp (UTC)</th>
            <th>Run / SHA</th>
            <th>Job</th>
            <th>Action</th>
            <th>Rationale</th>
          </tr>
        </thead>
        <tbody id="ledgerBody"></tbody>
      </table>
    </div>

    <div class="card">
      <h2>Latest Raw JSON Report</h2>
      <pre id="rawJson">{}</pre>
    </div>
  </div>

  <script>
    function buildEvent(scenario) {
      if (scenario === 'regression') {
        return {
          repo: "{{ repo }}",
          run_id: 9002,
          job_id: 4202,
          job_name: "unit-tests",
          head_sha: "9d4e2c1",
          base_sha: "8f3a1b2",
          duration_seconds: 58.0,
          touched_files: ["src/flask/app.py", "src/flask/ctx.py", "tests/test_appctx.py"],
          log_tail: "FAILED tests/test_appctx.py::test_app_context_teardown - AssertionError: assert teardown_called == [True] where teardown_called = []"
        };
      }
      return {
        repo: "{{ repo }}",
        run_id: 9001,
        job_id: 4201,
        job_name: "integration-tests",
        head_sha: "8f3a1b2",
        base_sha: "7c2d09e",
        duration_seconds: 245.0,
        touched_files: ["README.md", "docs/setup.md"],
        log_tail: "2026-11-23T10:00:01Z ERROR: ConnectionResetError: [Errno 104] Connection reset by peer during webhook callback"
      };
    }

    async function runScenario(scenario) {
      const res = await fetch('/api/triage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildEvent(scenario))
      });
      const data = await res.json();
      renderReport(data);
      await refreshLedger();
    }

    function renderReport(data) {
      document.getElementById('rawJson').textContent = JSON.stringify(data, null, 2);
      const ml = data.ml_prediction || {};
      document.getElementById('flakeProb').textContent = ((ml.flakiness_probability || 0) * 100).toFixed(2) + '%';
      document.getElementById('regProb').textContent = ((ml.regression_probability || 0) * 100).toFixed(2) + '%';

      const sigList = document.getElementById('topSignals');
      sigList.innerHTML = '';
      (ml.top_signals || []).forEach(s => {
        const li = document.createElement('li');
        li.textContent = s;
        sigList.appendChild(li);
      });

      const tr = data.triage || {};
      const badge = document.getElementById('triageCat');
      badge.textContent = tr.category || '—';
      badge.className = 'badge ' + (tr.category === 'real_regression' ? 'reg' : 'flake');

      const qa = data.quarantine_action || {};
      document.getElementById('qAction').textContent = qa.action || '—';
      document.getElementById('qRationale').textContent = qa.rationale || '';

      const stepsList = document.getElementById('qSteps');
      stepsList.innerHTML = '';
      (qa.next_steps || []).forEach(st => {
        const li = document.createElement('li');
        li.textContent = st;
        stepsList.appendChild(li);
      });
    }

    async function refreshLedger() {
      const res = await fetch('/api/ledger');
      const rows = await res.json();
      const tbody = document.getElementById('ledgerBody');
      tbody.innerHTML = '';
      [...rows].reverse().forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${(r.timestamp || '').replace('T', ' ').slice(0, 19)}</td>
          <td>#${r.run_id} <code>${r.head_sha}</code></td>
          <td>${r.target_job}</td>
          <td><code>${r.action}</code></td>
          <td>${r.rationale}</td>
        `;
        tbody.appendChild(tr);
      });
    }

    refreshLedger();
  </script>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(HTML_TEMPLATE, repo=settings.target_repo)


@app.get("/api/ledger")
def api_ledger():
    ledger_path = PROCESSED_DATA_DIR / "quarantine_ledger.json"
    if not ledger_path.exists():
        return jsonify([])
    return jsonify(json.loads(ledger_path.read_text(encoding="utf-8")))


@app.post("/api/triage")
def api_triage():
    payload = request.get_json(force=True)
    event = CIFailureEvent.model_validate(payload)
    report = pipeline.run(event)
    return jsonify(report.model_dump())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)