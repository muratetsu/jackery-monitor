"""
Jackery Web Dashboard Server

Raspberry Pi上で実行し、同一WiFiネットワークのスマホ・PCのブラウザから
Jackeryポータブル電源のデータをリアルタイムで確認できるWebサーバー。

使用方法:
    pip install flask
    python jackery_server.py

アクセス方法:
    http://<RaspberryPiのIPアドレス>:5000
    または http://raspberrypi.local:5000
"""

from flask import Flask, jsonify, render_template_string, request
import csv
import re
from pathlib import Path
from datetime import date, timedelta

app = Flask(__name__)
BASE_DIR = Path(__file__).parent


def get_available_dates():
    """利用可能な日付リスト（新しい順）を返す"""
    dates = []
    for f in sorted(BASE_DIR.glob("jackery_log_*.csv"), reverse=True):
        m = re.match(r'jackery_log_(\d{4}-\d{2}-\d{2})\.csv', f.name)
        if m:
            dates.append(m.group(1))
    return dates


def _parse_csv_file(filepath):
    """CSVファイルを読み込んで行リストを返す"""
    try:
        with open(filepath, newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))
    except Exception as e:
        print(f"[_parse_csv_file] Error: {e}")
        return []


def load_data(date_filter=None):
    """
    date_filter: None/'all' → 全期間
                 'today'     → 本日
                 'yesterday' → 昨日
                 'YYYY-MM-DD'→ 指定日
    """
    today = date.today()

    if date_filter in (None, 'all', ''):
        all_files = sorted(BASE_DIR.glob("jackery_log_*.csv"))
        old_file = BASE_DIR / "jackery_log.csv"
        if old_file.exists():
            all_files = [old_file] + list(all_files)
        all_rows = []
        for f in all_files:
            all_rows.extend(_parse_csv_file(f))
    else:
        if date_filter == 'today':
            target_date = today.strftime('%Y-%m-%d')
        elif date_filter == 'yesterday':
            target_date = (today - timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            target_date = date_filter

        target_file = BASE_DIR / f"jackery_log_{target_date}.csv"
        if target_file.exists():
            all_rows = _parse_csv_file(target_file)
        else:
            old_file = BASE_DIR / "jackery_log.csv"
            if old_file.exists():
                all_rows = [r for r in _parse_csv_file(old_file)
                            if r.get('Timestamp', '').startswith(target_date)]
            else:
                all_rows = []

    if not all_rows:
        return None

    try:
        columns = [col for col in all_rows[0].keys() if col != 'Timestamp']
        timestamps = []
        series = {col: [] for col in columns}

        for row in all_rows:
            timestamps.append(row['Timestamp'])
            for col in columns:
                raw = row.get(col, '')
                if col in ('OutputAC', 'OutputDC'):
                    series[col].append(1 if raw.lower() in ('true', '1') else 0)
                else:
                    try:
                        series[col].append(float(raw))
                    except ValueError:
                        series[col].append(None)

        latest = {'Timestamp': timestamps[-1]}
        for col in columns:
            latest[col] = series[col][-1]

        return {
            'timestamps': timestamps,
            'columns': columns,
            'series': series,
            'latest': latest,
            'count': len(timestamps),
        }
    except Exception as e:
        print(f"[load_data] Error: {e}")
        return None


# ============================================================
# HTML テンプレート
# ============================================================

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>Jackery Dashboard</title>
<meta name="description" content="Jackeryポータブル電源のリアルタイム監視ダッシュボード">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
:root {
  --bg:#080c18; --bg2:#0d1225; --card:rgba(255,255,255,0.04);
  --card-h:rgba(255,255,255,0.07); --border:rgba(255,255,255,0.08);
  --border-a:rgba(0,212,255,0.3); --t1:#e4eeff; --t2:#8899bb; --t3:#4a5878;
  --ac:#00d4ff; --ac-d:rgba(0,212,255,0.15); --gr:#00e676;
  --gr-d:rgba(0,230,118,0.15); --or:#ff6d3b; --ye:#ffd740;
  --re:#ff5252; --pu:#b388ff;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--t1);min-height:100vh;
  background-image:radial-gradient(ellipse at 15% 50%,rgba(0,212,255,.05) 0%,transparent 55%),
  radial-gradient(ellipse at 85% 15%,rgba(179,136,255,.05) 0%,transparent 55%);}
header{background:rgba(8,12,24,.9);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);
  padding:14px 24px;position:sticky;top:0;z-index:100;
  display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;}
.hd-left{display:flex;align-items:center;gap:12px;}
.logo{width:36px;height:36px;border-radius:10px;
  background:linear-gradient(135deg,var(--ac),var(--pu));
  display:flex;align-items:center;justify-content:center;font-size:18px;}
h1{font-size:19px;font-weight:700;
  background:linear-gradient(135deg,var(--ac),var(--pu));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
.hd-right{display:flex;align-items:center;gap:14px;flex-wrap:wrap;}
.stat-ind{display:flex;align-items:center;gap:7px;font-size:13px;color:var(--t2);}
.dot{width:8px;height:8px;border-radius:50%;background:var(--gr);animation:pulse 2s infinite;}
.dot.err{background:var(--re);animation:none;}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.cntdn{font-size:13px;color:var(--t2);}
.cntdn span{color:var(--ac);font-weight:600;font-variant-numeric:tabular-nums;}
.rbtn{background:var(--ac-d);border:1px solid var(--border-a);color:var(--ac);
  padding:7px 15px;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;
  transition:all .2s;font-family:inherit;}
.rbtn:hover{background:rgba(0,212,255,.25);transform:translateY(-1px);}
main{max-width:1400px;margin:0 auto;padding:22px 16px;}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));
  gap:12px;margin-bottom:22px;}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;
  padding:18px 15px;transition:all .2s;position:relative;overflow:hidden;}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;border-radius:16px 16px 0 0;}
.card:hover{background:var(--card-h);transform:translateY(-2px);}
.card.ac::before{background:linear-gradient(90deg,var(--ac),var(--pu));}
.card.gr::before{background:var(--gr);}
.card.or::before{background:var(--or);}
.card.ye::before{background:var(--ye);}
.card.re::before{background:var(--re);}
.card.pu::before{background:var(--pu);}
.ci{font-size:22px;margin-bottom:10px;}
.cl{font-size:11px;color:var(--t3);text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px;font-weight:500;}
.cv{font-size:28px;font-weight:700;line-height:1;font-variant-numeric:tabular-nums;}
.cu{font-size:13px;font-weight:400;color:var(--t2);margin-left:2px;}
.card.ac .cv{color:var(--ac);}.card.gr .cv{color:var(--gr);}
.card.or .cv{color:var(--or);}.card.ye .cv{color:var(--ye);}
.card.re .cv{color:var(--re);}.card.pu .cv{color:var(--pu);}
.badge{display:inline-block;padding:4px 12px;border-radius:20px;font-size:13px;font-weight:600;margin-top:4px;}
.badge.on{background:var(--gr-d);color:var(--gr);}
.badge.off{background:rgba(255,255,255,.05);color:var(--t3);}
.csec{background:var(--card);border:1px solid var(--border);border-radius:20px;overflow:hidden;}
.chdr{padding:18px 22px 14px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;}
.ctitle{font-size:16px;font-weight:600;}
.lupd{font-size:13px;color:var(--t3);}
/* --- Date Tabs --- */
.tab-bar{display:flex;flex-wrap:wrap;gap:6px;padding:12px 22px;border-bottom:1px solid var(--border);background:rgba(255,255,255,.01);}
.tab-btn{padding:6px 14px;border-radius:20px;border:1px solid var(--border);
  background:transparent;color:var(--t2);font-size:12px;font-weight:500;
  cursor:pointer;transition:all .2s;font-family:inherit;}
.tab-btn.active{background:var(--ac-d);border-color:var(--border-a);color:var(--ac);}
.tab-btn:hover:not(.active){background:rgba(255,255,255,.06);}
.tab-hint{font-size:11px;color:var(--t3);padding:6px 22px 0;display:flex;align-items:center;gap:6px;}
.tab-hint .icon{font-size:14px;}
/* --- Toggles --- */
.toggles{display:flex;flex-wrap:wrap;gap:7px;padding:14px 22px;border-bottom:1px solid var(--border);}
.tbtn{padding:5px 11px;border-radius:20px;border:1px solid var(--border);
  background:transparent;color:var(--t2);font-size:12px;font-weight:500;
  cursor:pointer;transition:all .2s;font-family:inherit;display:flex;align-items:center;gap:5px;}
.tbtn .dot2{width:8px;height:8px;border-radius:50%;}
.tbtn.active{color:var(--t1);border-color:rgba(255,255,255,.2);background:rgba(255,255,255,.06);}
.tbtn:hover{background:rgba(255,255,255,.08);}
#chart{width:100%;height:420px;}
.loverlay{display:none;position:fixed;inset:0;background:rgba(8,12,24,.7);
  backdrop-filter:blur(4px);z-index:200;align-items:center;justify-content:center;
  font-size:15px;color:var(--t2);}
.loverlay.show{display:flex;}
.spinner{width:30px;height:30px;border:3px solid var(--border);border-top-color:var(--ac);
  border-radius:50%;animation:spin .8s linear infinite;margin-right:12px;}
@keyframes spin{to{transform:rotate(360deg)}}
footer{text-align:center;padding:22px;color:var(--t3);font-size:12px;}
@media(max-width:480px){
  .cards{grid-template-columns:repeat(2,1fr);}
  header{padding:11px 14px;}h1{font-size:16px;}
  #chart{height:300px;}.chdr,.toggles,.tab-bar{padding:13px 14px;}
}
</style>
</head>
<body>
<div class="loverlay" id="loverlay"><div class="spinner"></div>データを更新中...</div>

<header>
  <div class="hd-left">
    <div class="logo">⚡</div>
    <h1>Jackery Dashboard</h1>
  </div>
  <div class="hd-right">
    <div class="stat-ind"><div class="dot" id="sdot"></div><span id="stext">接続中...</span></div>
    <div class="cntdn">次の自動更新: <span id="cntdn">60</span>秒</div>
    <button class="rbtn" onclick="fetchData()">↻ 今すぐ更新</button>
  </div>
</header>

<main>
  <div class="cards" id="cards"></div>
  <div class="csec">
    <div class="chdr">
      <div class="ctitle">📈 履歴グラフ</div>
      <div class="lupd" id="lupd">---</div>
    </div>
    <div class="tab-bar" id="tab-bar">
      <button class="tab-btn active" id="tab-all"       data-tab="all"       onclick="switchTab('all')">📅 全期間</button>
      <button class="tab-btn"        id="tab-today"     data-tab="today"     onclick="switchTab('today')">🌅 本日</button>
      <button class="tab-btn"        id="tab-yesterday" data-tab="yesterday" onclick="switchTab('yesterday')">📆 昨日</button>
    </div>
    <div class="tab-hint" id="tab-hint">
      <span class="icon">🔗</span>
      <span id="hint-text">グラフをズームすると、URLにその範囲が保存されます。リロード後も表示が維持されます。</span>
    </div>
    <div class="toggles" id="toggles"></div>
    <div id="chart"></div>
  </div>
</main>

<footer>Jackery Dashboard — Raspberry Pi Web Server</footer>

<script>
let chartData = null;
let activeSet = new Set(['Battery(%)', 'InputPower(W)', 'OutputPower(W)', 'BatteryTemp(C)']);
let cdInterval = null;
let cdVal = 60;
let currentTab = 'all';
let suppressHashUpdate = false;
let chartEventsAttached = false;
let togglesBuilt = false;

const COLORS = {
  'Battery(%)':'#00d4ff','BatteryTemp(C)':'#ffd740',
  'ACInputPower(W)':'#b388ff','InputPower(W)':'#00e676','InputTime(h)':'#69f0ae',
  'OutputPower(W)':'#ff6d3b','ACOutputVoltage(V)':'#ff9800','OutputTime(h)':'#ff8a65',
  'OutputAC':'#40c4ff','OutputDC':'#80d8ff','LightMode':'#e040fb',
  'ScreenTimeout':'#7c4dff','SuperFastCharge':'#f06292','ChargeSpeed':'#4db6ac',
  'LowPowerSetting':'#81c784','PowerManagement':'#ffb74d','AutoSavingTime':'#a1887f',
};
function getColor(n){ return COLORS[n] || '#aabbcc'; }

const CARD_DEFS = [
  {key:'Battery(%)',      icon:'🔋', label:'バッテリー残量', unit:'%',  cls:'ac', dec:0},
  {key:'BatteryTemp(C)', icon:'🌡️', label:'バッテリー温度', unit:'°C', cls:'ye', dec:1},
  {key:'InputPower(W)',  icon:'⬇️', label:'入力電力',       unit:'W',  cls:'gr', dec:0},
  {key:'OutputPower(W)', icon:'⬆️', label:'出力電力',       unit:'W',  cls:'or', dec:0},
  {key:'InputTime(h)',   icon:'⏱️', label:'充電完了時間',   unit:'h',  cls:'pu', dec:1},
  {key:'OutputTime(h)',  icon:'⌛', label:'放電可能時間',   unit:'h',  cls:'re', dec:1},
  {key:'OutputAC',       icon:'🔌', label:'AC出力',         unit:'',   cls:'gr', toggle:true},
  {key:'OutputDC',       icon:'🔋', label:'DC出力',         unit:'',   cls:'gr', toggle:true},
];

// ===== URL Hash =====
function getHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  return { tab: p.get('tab') || 'all', xr: p.get('xr') || null };
}
function setHash(tab, xr) {
  const p = new URLSearchParams();
  p.set('tab', tab);
  if (xr) p.set('xr', xr);
  history.replaceState(null, '', '#' + p.toString());
}

// ===== Tab switching =====
function switchTab(tab) {
  if (tab === currentTab) return;
  currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  // タブ変更時は範囲をリセット
  setHash(tab, null);
  togglesBuilt = false;
  document.getElementById('toggles').innerHTML = '';
  fetchData();
}

// ===== Data & Render =====
async function fetchData(){
  document.getElementById('loverlay').classList.add('show');
  resetCountdown();
  try {
    const r = await fetch('/api/data?date=' + currentTab);
    if(!r.ok) throw new Error(`HTTP ${r.status}`);
    chartData = await r.json();
    if(chartData.error) throw new Error(chartData.error);
    renderCards(chartData.latest);
    ensureToggles(chartData.columns);
    await renderChart();
    // ハッシュに保存された範囲を復元
    const {xr} = getHash();
    if(xr) {
      const parts = xr.split('|');
      if(parts.length === 2) {
        suppressHashUpdate = true;
        await Plotly.relayout('chart', {'xaxis.range': parts});
        suppressHashUpdate = false;
      }
    }
    setStatus(true, `データ数: ${chartData.timestamps.length}件`);
    document.getElementById('lupd').textContent = '最終更新: ' + new Date().toLocaleString('ja-JP');
  } catch(e){
    setStatus(false, 'エラー: ' + e.message);
    console.error(e);
  } finally {
    document.getElementById('loverlay').classList.remove('show');
  }
}

function setStatus(ok, text){
  document.getElementById('sdot').className = 'dot' + (ok ? '' : ' err');
  document.getElementById('stext').textContent = text;
}

function resetCountdown(){
  clearInterval(cdInterval);
  cdVal = 60;
  document.getElementById('cntdn').textContent = cdVal;
  cdInterval = setInterval(()=>{
    cdVal--;
    document.getElementById('cntdn').textContent = cdVal;
    if(cdVal <= 0) fetchData();
  }, 1000);
}

function renderCards(latest){
  if(!latest) return;
  const grid = document.getElementById('cards');
  grid.innerHTML = '';
  CARD_DEFS.forEach(d => {
    if(!(d.key in latest)) return;
    const v = latest[d.key];
    const card = document.createElement('div');
    card.className = `card ${d.cls}`;
    if(d.toggle){
      const on = v==1||v===true||String(v).toLowerCase()==='true';
      card.innerHTML = `<div class="ci">${d.icon}</div><div class="cl">${d.label}</div>
        <span class="badge ${on?'on':'off'}">${on?'ON':'OFF'}</span>`;
    } else {
      const fv = parseFloat(v).toFixed(d.dec);
      card.innerHTML = `<div class="ci">${d.icon}</div><div class="cl">${d.label}</div>
        <div class="cv">${fv}<span class="cu">${d.unit}</span></div>`;
    }
    grid.appendChild(card);
  });
}

function ensureToggles(columns){
  if(togglesBuilt) return;
  togglesBuilt = true;
  const c = document.getElementById('toggles');
  c.innerHTML = '';
  columns.forEach(col => {
    const btn = document.createElement('button');
    btn.className = 'tbtn' + (activeSet.has(col) ? ' active' : '');
    btn.dataset.s = col;
    btn.innerHTML = `<span class="dot2" style="background:${getColor(col)}"></span>${col}`;
    btn.onclick = () => {
      if(activeSet.has(col)){ activeSet.delete(col); btn.classList.remove('active'); }
      else { activeSet.add(col); btn.classList.add('active'); }
      renderChart();
    };
    c.appendChild(btn);
  });
}

async function renderChart(){
  if(!chartData) return;
  const ts = chartData.timestamps.map(t => new Date(t));
  const traces = chartData.columns
    .filter(col => activeSet.has(col))
    .map(col => ({
      x: ts, y: chartData.series[col],
      type: 'scatter', mode: 'lines', name: col,
      line: { color: getColor(col), width: 2 },
      hovertemplate: `<b>${col}</b>: %{y}<br>%{x|%Y-%m-%d %H:%M}<extra></extra>`
    }));

  const layout = {
    paper_bgcolor:'transparent', plot_bgcolor:'transparent',
    font: {family:'Inter,sans-serif', color:'#8899bb', size:12},
    margin: {t:16, r:20, b:60, l:55},
    xaxis: {
      gridcolor:'rgba(255,255,255,.06)', linecolor:'rgba(255,255,255,.1)',
      tickcolor:'rgba(255,255,255,.1)',
      rangeslider:{bgcolor:'rgba(255,255,255,.03)',bordercolor:'transparent',thickness:0.06},
    },
    yaxis: {
      gridcolor:'rgba(255,255,255,.06)', linecolor:'rgba(255,255,255,.1)',
      tickcolor:'rgba(255,255,255,.1)', zeroline:false,
    },
    legend: {bgcolor:'rgba(255,255,255,.04)',bordercolor:'rgba(255,255,255,.08)',borderwidth:1,font:{size:11}},
    hovermode:'x unified',
    hoverlabel: {bgcolor:'#0d1225',bordercolor:'rgba(0,212,255,.4)',font:{family:'Inter,sans-serif',size:12,color:'#e4eeff'}},
  };

  await Plotly.react('chart', traces, layout, {
    responsive:true, displayModeBar:true, displaylogo:false,
    modeBarButtonsToRemove:['select2d','lasso2d','autoScale2d'],
  });

  // イベントは初回のみ登録
  if(!chartEventsAttached) {
    chartEventsAttached = true;
    document.getElementById('chart').on('plotly_relayout', (ev) => {
      if(suppressHashUpdate) return;
      if(ev['xaxis.range[0]'] !== undefined && ev['xaxis.range[1]'] !== undefined) {
        setHash(currentTab, `${ev['xaxis.range[0]']}|${ev['xaxis.range[1]']}`);
      } else if(ev['xaxis.autorange'] === true) {
        setHash(currentTab, null);
      }
    });
  }
}

// ===== Init =====
(function init(){
  const {tab} = getHash();
  currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  fetchData();
})();
</script>
</body>
</html>"""


# ============================================================
# Routes
# ============================================================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/data')
def get_data():
    date_filter = request.args.get('date', 'all')
    data = load_data(date_filter)
    if data is None:
        label = {'today': '本日', 'yesterday': '昨日'}.get(date_filter, date_filter)
        return jsonify({"error": f"「{label}」のデータがありません。jackery_api.py が実行されているか確認してください。"})
    return jsonify(data)


@app.route('/api/dates')
def get_dates():
    return jsonify(get_available_dates())


if __name__ == '__main__':
    import socket
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = '(IPアドレスを確認してください)'

    print("=" * 55)
    print("  Jackery Dashboard Web Server")
    print("=" * 55)
    print(f"  ローカルIPアドレス: http://{local_ip}:5000")
    print(f"  ホスト名:           http://{hostname}.local:5000")
    print("  停止するには Ctrl+C を押してください")
    print("=" * 55)

    app.run(host='0.0.0.0', port=5000, debug=False)
