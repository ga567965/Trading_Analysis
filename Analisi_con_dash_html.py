#!/usr/bin/env python3
"""
Flask Technical Analysis Dashboard
Versione web (Flask + HTML) dell'app con interfaccia Tkinter
- Una sola file app.py che espone una dashboard moderna in HTML
- Usa Bootstrap 5 + Plotly.js per grafici interattivi
- Dipendenze principali: flask, yfinance, pandas, numpy, ta

Avvio:
    pip install flask yfinance pandas numpy ta plotly
    python app.py

Poi apri il browser su: http://127.0.0.1:5000/
"""

import json
import numpy as np
import pandas as pd
import yfinance as yf
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands
from datetime import datetime
from flask import Flask, request, render_template_string

# ----------------------------
# Modello dati e indicatori
# ----------------------------
class Company:
    """Semplice contenitore per dati e indicatori"""
    def __init__(self, symbol: str):
        self.symbol = symbol.upper()
        self.technical_indicators: pd.DataFrame | None = None
        self.prices: pd.Series | None = None


def generate_buy_sell_signals(condition_buy, condition_sell, dataframe: pd.DataFrame, strategy: str):
    """Genera segnali Buy/Sell in base a due condizioni booleane.
    Mantiene lo stesso spirito della versione Tkinter.
    Ritorna anche l'ultimo segnale (stringa)."""
    last_signal = None
    indicator_state = []  # stato cumulativo ("Buy" dopo un buy finché non arriva sell)
    buy = []
    sell = []

    for i in range(len(dataframe)):
        if condition_buy(i, dataframe) and last_signal != 'Buy':
            last_signal = 'Buy'
            buy.append(dataframe['Close'].iloc[i])
            sell.append(np.nan)
        elif condition_sell(i, dataframe) and last_signal == 'Buy':
            last_signal = 'Sell'
            buy.append(np.nan)
            sell.append(dataframe['Close'].iloc[i])
        else:
            buy.append(np.nan)
            sell.append(np.nan)
        indicator_state.append(last_signal)

    dataframe[f'{strategy}_Indicator'] = np.array(indicator_state, dtype=object)
    dataframe[f'{strategy}_Buy'] = np.array(buy, dtype=float)
    dataframe[f'{strategy}_Sell'] = np.array(sell, dtype=float)
    return last_signal


def get_macd(company: Company) -> str:
    df = company.technical_indicators
    # Parametri identici al codice originale
    window_slow, window_fast, signal = 26, 12, 9
    macd_calc = MACD(company.prices, window_slow=window_slow, window_fast=window_fast, window_sign=signal)
    df['MACD'] = macd_calc.macd()
    df['MACD_Histogram'] = macd_calc.macd_diff()
    df['MACD_Signal'] = macd_calc.macd_signal()

    # Nota: manteniamo le condizioni originali (Buy quando MACD < Signal)
    last = generate_buy_sell_signals(
        lambda x, d: d['MACD'].values[x] < d['MACD_Signal'].values[x],
        lambda x, d: d['MACD'].values[x] > d['MACD_Signal'].values[x],
        df,
        'MACD'
    )
    return last or 'None'


def get_rsi(company: Company, rsi_time_period: int = 20, low_rsi: int = 40, high_rsi: int = 70) -> str:
    df = company.technical_indicators
    rsi_indicator = RSIIndicator(company.prices, window=rsi_time_period)
    df['RSI'] = rsi_indicator.rsi()

    last = generate_buy_sell_signals(
        lambda x, d: d['RSI'].values[x] < low_rsi,
        lambda x, d: d['RSI'].values[x] > high_rsi,
        df,
        'RSI'
    )
    return last or 'None'


def get_bollinger_bands(company: Company, window: int = 20) -> str:
    df = company.technical_indicators
    bb = BollingerBands(close=company.prices, window=window, window_dev=2)
    df['Bollinger_Bands_Middle'] = bb.bollinger_mavg()
    df['Bollinger_Bands_Upper'] = bb.bollinger_hband()
    df['Bollinger_Bands_Lower'] = bb.bollinger_lband()

    last = generate_buy_sell_signals(
        lambda x, d: d['Close'].values[x] < d['Bollinger_Bands_Lower'].values[x],
        lambda x, d: d['Close'].values[x] > d['Bollinger_Bands_Upper'].values[x],
        df,
        'Bollinger_Bands'
    )
    return last or 'None'


def set_technical_indicators(company: Company):
    company.technical_indicators = pd.DataFrame()
    company.technical_indicators['Close'] = company.prices
    last_macd = get_macd(company)
    last_rsi = get_rsi(company)
    last_bb = get_bollinger_bands(company)
    return {
        'MACD': last_macd,
        'RSI': last_rsi,
        'BOLL': last_bb,
    }

# ----------------------------
# App Flask
# ----------------------------
app = Flask(__name__)

# Template HTML (Jinja2) incorporato per semplicità
TEMPLATE = r"""
<!doctype html>
<html lang="it">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>📈 Technical Analysis Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <style>
      body { background: #0f1623; color: #ecf0f1; }
      .card { background: #1b2433; border: none; border-radius: 16px; box-shadow: 0 10px 24px rgba(0,0,0,.2); }
      .form-control, .form-select { background: #101827; color: #e2e8f0; border: 1px solid #2b3550; }
      .navbar { background: linear-gradient(90deg,#0f172a,#111827); }
      .badge { font-size: .9rem; }
      .muted { color: #94a3b8; }
      .kpi { font-weight: 700; font-size: 1.2rem; }
      .footer { color: #94a3b8; font-size: .9rem; }
      .pill { border-radius: 999px; padding: .1rem .6rem; background: #0b1220; border: 1px solid #2b3550; }
    </style>
  </head>
  <body>
    <nav class="navbar navbar-dark mb-4">
      <div class="container">
        <span class="navbar-brand mb-0 h1">📊 Technical Analysis Dashboard</span>
        <span class="pill">{{ now }}</span>
      </div>
    </nav>

    <div class="container">
      <!-- Parametri -->
      <div class="card mb-4 p-3">
        <form class="row g-3" method="get" action="/">
          <div class="col-sm-4">
            <label class="form-label">Ticker</label>
            <input type="text" class="form-control" name="symbol" value="{{ symbol }}" placeholder="AAPL, MSFT, TSLA" required>
          </div>
          <div class="col-sm-4">
            <label class="form-label">Periodo</label>
            <select name="period" class="form-select">
              {% for p in ["1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"] %}
                <option value="{{p}}" {% if p==period %}selected{% endif %}>{{p}}</option>
              {% endfor %}
            </select>
          </div>
          <div class="col-sm-4 d-flex align-items-end">
            <button class="btn btn-primary w-100" type="submit">🔍 Analizza</button>
          </div>
        </form>
      </div>

      {% if error %}
        <div class="alert alert-danger">{{ error }}</div>
      {% else %}
      <!-- KPI -->
      <div class="row g-3 mb-4">
        <div class="col-md-3">
          <div class="card p-3 h-100">
            <div class="muted">Ticker</div>
            <div class="kpi">{{ symbol }}</div>
            <span class="badge text-bg-secondary">Periodo: {{ period }}</span>
          </div>
        </div>
        <div class="col-md-3">
          <div class="card p-3 h-100">
            <div class="muted">Prezzo corrente</div>
            <div class="kpi">${{ last_price }}</div>
            <div class="muted">High: ${{ high }} · Low: ${{ low }}</div>
          </div>
        </div>
        <div class="col-md-3">
          <div class="card p-3 h-100">
            <div class="muted">Variazione periodo</div>
            <div class="kpi">{{ change_pct }}%</div>
            <div class="muted">Punti dati: {{ n_points }}</div>
          </div>
        </div>
        <div class="col-md-3">
          <div class="card p-3 h-100">
            <div class="muted">Segnali più recenti</div>
            <div>MACD: <span class="badge text-bg-info">{{ last_signals.MACD }}</span></div>
            <div>RSI: <span class="badge text-bg-info">{{ last_signals.RSI }}</span></div>
            <div>Bollinger: <span class="badge text-bg-info">{{ last_signals.BOLL }}</span></div>
          </div>
        </div>
      </div>

      <!-- Grafici -->
      <div class="card p-3 mb-4">
        <div id="chart_price" style="height: 420px;"></div>
      </div>
      <div class="card p-3 mb-4">
        <div id="chart_macd" style="height: 360px;"></div>
      </div>
      <div class="card p-3 mb-4">
        <div id="chart_rsi" style="height: 340px;"></div>
      </div>
      <div class="card p-3 mb-5">
        <div id="chart_bb" style="height: 360px;"></div>
      </div>

      <div class="footer text-center mb-4">Built with Flask · Plotly · Bootstrap</div>
      {% endif %}
    </div>

    {% if not error %}
    <script>
      const data = {{ data_json | safe }};

      // --- PRICE + SIGNALS ---
      const traceClose = { x: data.dates, y: data.close, type: 'scatter', mode: 'lines', name: 'Close' };
      const traceBuy = { x: data.dates, y: data.price_buy, type: 'scatter', mode: 'markers', name: 'Buy', marker: {symbol: 'triangle-up', size: 10} };
      const traceSell = { x: data.dates, y: data.price_sell, type: 'scatter', mode: 'markers', name: 'Sell', marker: {symbol: 'triangle-down', size: 10} };
      Plotly.newPlot('chart_price', [traceClose, traceBuy, traceSell], {
        paper_bgcolor: '#1b2433', plot_bgcolor: '#1b2433',
        font: {color: '#e2e8f0'},
        title: 'Prezzo di Chiusura & Segnali (Ultimo: {{ last_signals.MACD }}, {{ last_signals.RSI }}, {{ last_signals.BOLL }})',
        xaxis: {gridcolor: '#2b3550'}, yaxis: {gridcolor: '#2b3550'}
      }, {responsive: true});

      // --- MACD ---
      const tMACD = { x: data.dates, y: data.macd, type: 'scatter', mode: 'lines', name: 'MACD' };
      const tSignal = { x: data.dates, y: data.macd_signal, type: 'scatter', mode: 'lines', name: 'Signal' };
      const tHist = { x: data.dates, y: data.macd_hist, type: 'bar', name: 'Histogram' };
      Plotly.newPlot('chart_macd', [tMACD, tSignal, tHist], {
        paper_bgcolor: '#1b2433', plot_bgcolor: '#1b2433', font: {color: '#e2e8f0'},
        title: 'MACD', xaxis: {gridcolor: '#2b3550'}, yaxis: {gridcolor: '#2b3550'}
      }, {responsive: true});

      // --- RSI ---
      const tRSI = { x: data.dates, y: data.rsi, type: 'scatter', mode: 'lines', name: 'RSI' };
      Plotly.newPlot('chart_rsi', [tRSI], {
        paper_bgcolor: '#1b2433', plot_bgcolor: '#1b2433', font: {color: '#e2e8f0'},
        title: 'RSI (40-70 shaded)', xaxis: {gridcolor: '#2b3550'}, yaxis: {gridcolor: '#2b3550', range:[0,100], dtick: 10},
        shapes: [
          { type:'rect', xref:'paper', x0:0, x1:1, yref:'y', y0:40, y1:70, fillcolor:'#3b82f6', opacity:0.15, line:{width:0} },
          { type:'line', xref:'paper', x0:0, x1:1, yref:'y', y0:40, y1:40, line:{dash:'dot'} },
          { type:'line', xref:'paper', x0:0, x1:1, yref:'y', y0:70, y1:70, line:{dash:'dot'} },
          { type:'line', xref:'paper', x0:0, x1:1, yref:'y', y0:50, y1:50, line:{width:1, color:'#94a3b8'} }
        ]
      }, {responsive: true});

      // --- BOLLINGER BANDS ---
      const tMid = { x: data.dates, y: data.bb_mid, type: 'scatter', mode: 'lines', name: 'SMA 20' };
      const tUp  = { x: data.dates, y: data.bb_up,  type: 'scatter', mode: 'lines', name: 'Upper' };
      const tLo  = { x: data.dates, y: data.bb_low, type: 'scatter', mode: 'lines', name: 'Lower' };
      const tFill = {
        x: data.dates.concat([...data.dates].reverse()),
        y: data.bb_up.concat([...data.bb_low].reverse()),
        fill: 'toself', type: 'scatter', mode: 'lines', name: 'Range', opacity: .1
      };
      Plotly.newPlot('chart_bb', [tFill, tMid, tUp, tLo], {
        paper_bgcolor: '#1b2433', plot_bgcolor: '#1b2433', font: {color: '#e2e8f0'},
        title: 'Bollinger Bands', xaxis: {gridcolor: '#2b3550'}, yaxis: {gridcolor: '#2b3550'}
      }, {responsive: true});
    </script>
    {% endif %}
  </body>
</html>
"""


def rsi_interpretation(val: float) -> str:
    if pd.isna(val):
        return "N/A"
    if val < 30:
        return f"{val:.1f} (Oversold - Consider Buying)"
    elif val > 70:
        return f"{val:.1f} (Overbought - Consider Selling)"
    return f"{val:.1f} (Normal Range)"


@app.route('/')
def index():
    symbol = (request.args.get('symbol') or 'AAPL').upper().strip()
    period = (request.args.get('period') or '1y').strip()

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        if hist.empty:
            return render_template_string(TEMPLATE, error=f"Nessun dato trovato per {symbol}", symbol=symbol, period=period, now=datetime.now().strftime('%Y-%m-%d %H:%M'))

        company = Company(symbol)
        company.prices = hist['Close']

        last_signals = set_technical_indicators(company)
        ind = company.technical_indicators

        # KPI
        last_price = float(company.prices.iloc[-1])
        high = float(company.prices.max())
        low = float(company.prices.min())
        change_pct = float(((company.prices.iloc[-1] / company.prices.iloc[0]) - 1) * 100)
        n_points = int(len(company.prices))

        # Dati per grafici (serializzabili)
        dates = [d.strftime('%Y-%m-%d') for d in ind.index]
        data_payload = {
            'dates': dates,
            'close': [None if pd.isna(x) else float(x) for x in ind['Close']],
            'price_buy': [None if pd.isna(x) else float(x) for x in ind.get('MACD_Buy', pd.Series([np.nan]*len(ind)))],
            'price_sell': [None if pd.isna(x) else float(x) for x in ind.get('MACD_Sell', pd.Series([np.nan]*len(ind)))],
            'macd': [None if pd.isna(x) else float(x) for x in ind['MACD']],
            'macd_signal': [None if pd.isna(x) else float(x) for x in ind['MACD_Signal']],
            'macd_hist': [0 if pd.isna(x) else float(x) for x in ind['MACD_Histogram']],
            'rsi': [None if pd.isna(x) else float(x) for x in ind['RSI']],
            'bb_mid': [None if pd.isna(x) else float(x) for x in ind['Bollinger_Bands_Middle']],
            'bb_up':  [None if pd.isna(x) else float(x) for x in ind['Bollinger_Bands_Upper']],
            'bb_low': [None if pd.isna(x) else float(x) for x in ind['Bollinger_Bands_Lower']],
        }

        return render_template_string(
            TEMPLATE,
            error=None,
            symbol=symbol,
            period=period,
            now=datetime.now().strftime('%Y-%m-%d %H:%M'),
            last_price=f"{last_price:,.2f}",
            high=f"{high:,.2f}",
            low=f"{low:,.2f}",
            change_pct=f"{change_pct:,.2f}",
            n_points=n_points,
            last_signals=last_signals,
            data_json=json.dumps(data_payload)
        )

    except Exception as e:
        return render_template_string(TEMPLATE, error=f"Errore: {e}", symbol=symbol, period=period, now=datetime.now().strftime('%Y-%m-%d %H:%M'))


@app.get('/health')
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


if __name__ == '__main__':
    print("🚀 Avvio Flask Technical Analysis Dashboard su http://127.0.0.1:5000/")
    app.run(debug=True)
