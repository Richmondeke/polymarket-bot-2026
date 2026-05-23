// Detect if running on Vercel vs local Flask
const apiBase = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') 
    ? '' 
    : 'http://localhost:5000';

// ── Chart.js Setup ──
const ctx = document.getElementById('pnlChart').getContext('2d');
const pnlChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: [],
        datasets: [{
            label: 'Portfolio Equity (USDC)',
            data: [],
            borderColor: '#0052ff', // Coinbase Blue
            backgroundColor: 'rgba(0, 82, 255, 0.05)', // Subtle blue fill
            borderWidth: 2,
            fill: true,
            tension: 0.1,
            pointRadius: 1,
            pointBackgroundColor: '#0052ff',
            pointBorderColor: '#ffffff',
            pointHoverRadius: 4
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 200 },
        plugins: { legend: { display: false } },
        scales: {
            x: { grid: { color: 'rgba(91,97,110,0.06)' }, ticks: { color: '#5b616e' } },
            y: { grid: { color: 'rgba(91,97,110,0.06)' }, ticks: { color: '#5b616e' } }
        }
    }
});

// ── Polling & Socket.IO Fallback Setup ──
let usePolling = false;

function updateUI(data) {
    if (data.chart) {
        pnlChart.data.labels = data.chart.labels;
        pnlChart.data.datasets[0].data = data.chart.data;
        pnlChart.update();
    }
    if (data.status) {
        const status = data.status;
        document.getElementById('current-balance').textContent = `$${status.current_balance.toFixed(2)}`;
        
        // Add new header stats
        document.getElementById('escrowed-balance').textContent = `$${(status.escrowed_balance || 0).toFixed(2)}`;
        document.getElementById('positions-value').textContent = `$${(status.positions_value || 0).toFixed(2)}`;
        document.getElementById('total-equity').textContent = `$${(status.total_equity || 0).toFixed(2)}`;
        
        const pnlEl = document.getElementById('daily-pnl');
        pnlEl.textContent = `${status.daily_pnl_pct.toFixed(2)}%`;
        pnlEl.className = `value ${status.daily_pnl_pct >= 0 ? 'pos' : 'neg'}`;
        
        document.getElementById('drawdown').textContent = `-${status.drawdown_pct.toFixed(2)}%`;
        document.getElementById('pos-count').textContent = `(${status.open_positions}/${status.max_open_positions})`;

        const badge = document.getElementById('bot-mode');
        if (status.kill_switch) {
            badge.textContent = 'killed';
            badge.className = 'value mode-badge killed';
        } else if (status.live_trading) {
            badge.textContent = 'live';
            badge.className = 'value mode-badge live';
        } else {
            badge.textContent = 'dry run';
            badge.className = 'value mode-badge dry';
        }
    }
    if (data.positions) {
        const tbody = document.querySelector('#positions-table tbody');
        tbody.innerHTML = '';
        data.positions.forEach(p => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${p.market_question.substring(0, 35)}...</td>
                <td class="${p.side === 'BUY' ? 'pos' : 'neg'}">${p.side}</td>
                <td>$${p.entry_price.toFixed(3)}</td>
                <td>$${p.size_usd.toFixed(2)}</td>
            `;
            tbody.appendChild(row);
        });
    }
    if (data.trades) {
        const tbody = document.querySelector('#trades-table tbody');
        tbody.innerHTML = '';
        data.trades.forEach(t => {
            const row = document.createElement('tr');
            const time = new Date(t.timestamp).toLocaleTimeString();
            row.innerHTML = `
                <td>${time}</td>
                <td>${t.market_question ? t.market_question.substring(0, 25) + '...' : t.market_id}</td>
                <td class="${t.side === 'BUY' ? 'pos' : 'neg'}">${t.side}</td>
                <td>$${t.price.toFixed(3)}</td>
                <td>${t.status}</td>
            `;
            tbody.appendChild(row);
        });
    }
    if (data.whales) {
        const tbody = document.querySelector('#whales-table tbody');
        tbody.innerHTML = '';
        data.whales.forEach(w => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>#${w.rank}</td>
                <td>${w.display_name.substring(0, 15)}</td>
                <td class="pos">${w.win_rate.toFixed(1)}%</td>
                <td>$${Math.round(w.total_volume).toLocaleString()}</td>
            `;
            tbody.appendChild(row);
        });
    }
    if (data.news) {
        const tbody = document.querySelector('#news-table tbody');
        tbody.innerHTML = '';
        data.news.forEach(n => {
            const row = document.createElement('tr');
            let payload = {};
            try {
                payload = JSON.parse(n.data || '{}');
            } catch (e) {}
            
            const q = payload.question || n.message;
            const prob = payload.probability ? `${(payload.probability * 100).toFixed(0)}%` : '50%';
            const sentClass = payload.sentiment === 'positive' ? 'pos' : (payload.sentiment === 'negative' ? 'neg' : '');
            
            row.innerHTML = `
                <td title="${q}">${q.substring(0, 30)}...</td>
                <td>${prob}</td>
                <td class="${sentClass}">${payload.sentiment || 'neutral'}</td>
                <td title="${payload.reasoning || ''}">${(payload.reasoning || '').substring(0, 40)}...</td>
            `;
            tbody.appendChild(row);
        });
    }
    if (data.arbitrage) {
        const tbody = document.querySelector('#arbitrage-table tbody');
        tbody.innerHTML = '';
        data.arbitrage.forEach(a => {
            const row = document.createElement('tr');
            let payload = {};
            try {
                payload = JSON.parse(a.data || '{}');
            } catch (e) {}
            
            const title = payload.event_title || a.message;
            const yesSum = payload.yes_sum ? payload.yes_sum.toFixed(3) : '1.000';
            const margin = payload.estimated_profit_pct ? `${payload.estimated_profit_pct}%` : '0%';
            
            row.innerHTML = `
                <td title="${title}">${title.substring(0, 30)}...</td>
                <td>${yesSum}</td>
                <td>${payload.basket_type || 'NO_BASKET'}</td>
                <td class="pos">${margin}</td>
            `;
            tbody.appendChild(row);
        });
    }
    if (data.logs) {
        const container = document.getElementById('log-container');
        container.innerHTML = '';
        data.logs.slice().reverse().forEach(log => {
            const el = document.createElement('div');
            el.className = `log-entry log-${log.severity}`;
            const time = new Date(log.timestamp).toLocaleTimeString();
            el.innerHTML = `[${time}] ${log.message}`;
            container.appendChild(el);
        });
        container.scrollTop = container.scrollHeight;
    }
}

// Socket IO configuration
let socket = null;
try {
    socket = io(apiBase || undefined, {
        reconnectionAttempts: 2,
        timeout: 3000
    });

    socket.on('connect', () => {
        console.log("Connected to WebSocket");
        usePolling = false;
    });

    socket.on('connect_error', () => {
        console.log("WebSocket failed, switching to HTTP Polling");
        usePolling = true;
        startPolling();
    });

    socket.on('chart_update', (data) => { if (!usePolling) updateUI({ chart: data }); });
    socket.on('status_update', (status) => { if (!usePolling) updateUI({ status: status }); });
    socket.on('positions_update', (positions) => { if (!usePolling) updateUI({ positions: positions }); });
    socket.on('trades_update', (trades) => { if (!usePolling) updateUI({ trades: trades }); });
    socket.on('whales_update', (whales) => { if (!usePolling) updateUI({ whales: whales }); });
    socket.on('news_update', (news) => { if (!usePolling) updateUI({ news: news }); });
    socket.on('arbitrage_update', (arbitrage) => { if (!usePolling) updateUI({ arbitrage: arbitrage }); });
    socket.on('logs_update', (logs) => { if (!usePolling) updateUI({ logs: logs }); });
} catch (e) {
    console.log("SocketIO not available, using HTTP Polling");
    usePolling = true;
    startPolling();
}

// HTTP Polling Fallback
let pollingInterval = null;
function startPolling() {
    if (pollingInterval) return;
    fetchData();
    pollingInterval = setInterval(fetchData, 2000);
}

function fetchData() {
    fetch(apiBase + '/api/data')
        .then(res => res.json())
        .then(data => {
            if (!data.error) {
                updateUI(data);
            }
        })
        .catch(err => console.error("Polling error:", err));
}

// Initial pull for logs if WebSocket hasn't triggered yet
fetch(apiBase + '/api/logs')
    .then(res => res.json())
    .then(logs => {
        if (usePolling) return; // handled by poller
        const container = document.getElementById('log-container');
        container.innerHTML = '';
        logs.reverse().forEach(log => {
            const el = document.createElement('div');
            el.className = `log-entry log-${log.severity}`;
            const time = new Date(log.timestamp).toLocaleTimeString();
            el.innerHTML = `[${time}] ${log.message}`;
            container.appendChild(el);
        });
        container.scrollTop = container.scrollHeight;
    });

// ── UI Interactions ──
const killBtn = document.getElementById('kill-switch');
killBtn.addEventListener('click', () => {
    const isKilled = killBtn.textContent === 'activate bot';
    const action = isKilled ? 'deactivate' : 'activate';
    
    if (!isKilled && !confirm("DANGER: This will cancel all open orders and halt trading immediately. Proceed?")) {
        return;
    }
    
    fetch(apiBase + '/api/kill', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: action })
    }).then(() => {
        if (action === 'activate') {
            killBtn.textContent = 'activate bot';
            killBtn.className = 'btn-success';
        } else {
            killBtn.textContent = 'kill switch';
            killBtn.className = 'btn-danger';
        }
    });
});
