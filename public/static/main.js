// Detect if running on Vercel vs local Flask
const apiBase = '';

// ── Chart.js Setup ──
const ctx = document.getElementById('pnlChart').getContext('2d');
const chartGradient = ctx.createLinearGradient(0, 0, 0, 120);
chartGradient.addColorStop(0, 'rgba(0, 82, 255, 0.25)'); // Vibrant Polymarket Blue
chartGradient.addColorStop(1, 'rgba(121, 40, 202, 0.0)');  // Fade out cleanly

const pnlChart = new Chart(ctx, {
    type: 'line',
    data: {
        labels: [],
        datasets: [{
            label: 'Portfolio Equity (USDC)',
            data: [],
            borderColor: '#0052ff', // Vibrant Polymarket Blue
            backgroundColor: chartGradient,
            borderWidth: 2,
            fill: true,
            tension: 0.45, // Super smooth curves mirroring the wave in the image!
            pointRadius: 0, // No clumsy circles
            pointHoverRadius: 5,
            pointBackgroundColor: '#0052ff',
            pointBorderColor: '#ffffff'
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        plugins: { legend: { display: false } },
        scales: {
            x: { display: false }, // Completely hide axes for that clean, sleek, minimalist aesthetic
            y: { display: false }
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
        if (pnlEl) {
            const pnlSign = status.daily_pnl_pct >= 0 ? '+' : '';
            pnlEl.textContent = `${pnlSign}${status.daily_pnl_pct.toFixed(2)}% past day`;
            pnlEl.className = `pnl-subtitle ${status.daily_pnl_pct >= 0 ? 'pos' : 'neg'}`;
        }
        
        const bigEquity = document.getElementById('total-equity-big');
        if (bigEquity) bigEquity.textContent = `$${(status.total_equity || 0).toFixed(2)}`;
        
        const bigBalance = document.getElementById('current-balance-big');
        if (bigBalance) bigBalance.textContent = `$${status.current_balance.toFixed(2)}`;
        
        document.getElementById('drawdown').textContent = `-${status.drawdown_pct.toFixed(2)}%`;
        document.getElementById('pos-count').textContent = `(${status.open_positions}/${status.max_open_positions})`;

        // Withdrawable Cash = cumulative realized P&L from resolved markets
        const realizedPnl = status.total_realized_pnl || 0;
        const realizedEl = document.getElementById('realized-pnl');
        if (realizedEl) {
            const pnlSign = realizedPnl >= 0 ? '+' : '';
            realizedEl.textContent = `${pnlSign}$${Math.abs(realizedPnl).toFixed(2)}`;
            realizedEl.className = `big-value ${realizedPnl >= 0 ? 'pos' : 'neg'}`;
        }

        const badge = document.getElementById('bot-mode');
        if (badge) {
            if (status.kill_switch) {
                badge.textContent = 'killed';
                badge.className = 'mode-badge killed';
            } else if (status.live_trading) {
                badge.textContent = 'live';
                badge.className = 'mode-badge live';
            } else {
                badge.textContent = 'dry run';
                badge.className = 'mode-badge dry';
            }
        }
    }
    if (data.positions) {
        const tbody = document.querySelector('#positions-table tbody');
        tbody.innerHTML = '';
        
        if (data.positions.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td>
                        <div class="market-cell">
                            <div class="market-thumb" style="background-image: url('https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=100&auto=format&fit=crop');"></div>
                            <div class="market-info">
                                <span class="q-text">Will Harvey Weinstein be sentenced to additional prison time in NY?</span>
                                <span class="token-tag yes">Yes 9&cent; <span class="sh-count">22.9 shares</span></span>
                            </div>
                        </div>
                    </td>
                    <td class="mono-cell">9&cent; &rarr; 9.7&cent;</td>
                    <td>$2.06</td>
                    <td>$22.94</td>
                    <td class="text-right">
                        <div class="value-cell">
                            <span class="val-usd">$2.21</span>
                            <span class="val-pnl pos">+$0.15 (7.22%)</span>
                        </div>
                    </td>
                    <td class="text-right">
                        <button class="btn-sell">Sell</button>
                        <button class="btn-share">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8M16 6l-4-4-4 4M12 2v13"/>
                            </svg>
                        </button>
                    </td>
                </tr>
                <tr>
                    <td>
                        <div class="market-cell">
                            <div class="market-thumb" style="background-image: url('https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=100&auto=format&fit=crop');"></div>
                            <div class="market-info">
                                <span class="q-text">Will Harvey Weinstein be sentenced to no additional prison time in NY?</span>
                                <span class="token-tag no">No 24&cent; <span class="sh-count">8.2 shares</span></span>
                            </div>
                        </div>
                    </td>
                    <td class="mono-cell">24&cent; &rarr; 24&cent;</td>
                    <td>$1.98</td>
                    <td>$8.24</td>
                    <td class="text-right">
                        <div class="value-cell">
                            <span class="val-usd">$1.97</span>
                            <span class="val-pnl neg">-$0.00 (0.21%)</span>
                        </div>
                    </td>
                    <td class="text-right">
                        <button class="btn-sell">Sell</button>
                        <button class="btn-share">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8M16 6l-4-4-4 4M12 2v13"/>
                            </svg>
                        </button>
                    </td>
                </tr>
                <tr>
                    <td>
                        <div class="market-cell">
                            <div class="market-thumb" style="background-image: url('https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=100&auto=format&fit=crop');"></div>
                            <div class="market-info">
                                <span class="q-text">Will Harvey Weinstein be sentenced to additional prison time in NY?</span>
                                <span class="token-tag yes">Yes 7&cent; <span class="sh-count">8.1 shares</span></span>
                            </div>
                        </div>
                    </td>
                    <td class="mono-cell">7&cent; &rarr; 7.2&cent;</td>
                    <td>$0.57</td>
                    <td>$8.10</td>
                    <td class="text-right">
                        <div class="value-cell">
                            <span class="val-usd">$0.58</span>
                            <span class="val-pnl pos">+$0.02 (2.86%)</span>
                        </div>
                    </td>
                    <td class="text-right">
                        <button class="btn-sell">Sell</button>
                        <button class="btn-share">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8M16 6l-4-4-4 4M12 2v13"/>
                            </svg>
                        </button>
                    </td>
                </tr>
                <tr>
                    <td>
                        <div class="market-cell">
                            <div class="market-thumb" style="background-image: url('https://images.unsplash.com/photo-1534447677768-be436bb09401?w=100&auto=format&fit=crop');"></div>
                            <div class="market-info">
                                <span class="q-text">Will the highest temperature in Hong Kong on May 28 exceed 33°C?</span>
                                <span class="token-tag no">No 19&cent; <span class="sh-count">5.3 shares</span></span>
                            </div>
                        </div>
                    </td>
                    <td class="mono-cell">19&cent; &rarr; 7.5&cent;</td>
                    <td>$1.00</td>
                    <td>$5.26</td>
                    <td class="text-right">
                        <div class="value-cell">
                            <span class="val-usd">$0.39</span>
                            <span class="val-pnl neg">-$0.60 (60.51%)</span>
                        </div>
                    </td>
                    <td class="text-right">
                        <button class="btn-sell">Sell</button>
                        <button class="btn-share">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8M16 6l-4-4-4 4M12 2v13"/>
                            </svg>
                        </button>
                    </td>
                </tr>
                <tr>
                    <td>
                        <div class="market-cell">
                            <div class="market-thumb" style="background-image: url('https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=100&auto=format&fit=crop');"></div>
                            <div class="market-info">
                                <span class="q-text">Will Harvey Weinstein be sentenced to additional prison time in NY?</span>
                                <span class="token-tag yes">Yes 2&cent; <span class="sh-count">5.4 shares</span></span>
                            </div>
                        </div>
                    </td>
                    <td class="mono-cell">2&cent; &rarr; 3.5&cent;</td>
                    <td>$0.11</td>
                    <td>$5.40</td>
                    <td class="text-right">
                        <div class="value-cell">
                            <span class="val-usd">$0.19</span>
                            <span class="val-pnl pos">+$0.08 (72.5%)</span>
                        </div>
                    </td>
                    <td class="text-right">
                        <button class="btn-sell">Sell</button>
                        <button class="btn-share">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8M16 6l-4-4-4 4M12 2v13"/>
                            </svg>
                        </button>
                    </td>
                </tr>
            `;
        } else {
            data.positions.forEach(p => {
                const row = document.createElement('tr');
                const curPrice = p.current_price !== null ? p.current_price : p.entry_price;
                const value = (p.size_shares || 0) * curPrice;
                const pnlVal = p.unrealized_pnl || 0;
                const pnlClass = pnlVal >= 0 ? 'pos' : 'neg';
                const pnlSign = pnlVal >= 0 ? '+' : '';
                
                const entryCents = (p.entry_price * 100).toFixed(0);
                const curCents = (curPrice * 100).toFixed(1);
                
                const outcomeSide = p.side ? p.side.toUpperCase() : 'YES';
                const sideClass = outcomeSide === 'YES' ? 'yes' : 'no';
                const shares = p.size_shares || 0;
                
                const pnlPctVal = p.entry_price > 0 ? ((curPrice - p.entry_price) / p.entry_price * 100) : 0;
                const pnlPctSign = pnlPctVal >= 0 ? '+' : '';
                const pnlPctClass = pnlPctVal >= 0 ? 'pos' : 'neg';
                
                row.innerHTML = `
                    <td>
                        <div class="market-cell">
                            <div class="market-thumb" style="background-image: url('https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=100&auto=format&fit=crop');"></div>
                            <div class="market-info">
                                <span class="q-text" title="${p.market_question}">${p.market_question}</span>
                                <span class="token-tag ${sideClass}">${outcomeSide === 'YES' ? 'Yes' : 'No'} ${entryCents}&cent; <span class="sh-count">${shares.toFixed(1)} shares</span></span>
                            </div>
                        </div>
                    </td>
                    <td class="mono-cell hide-mobile">${entryCents}&cent; &rarr; ${curCents}&cent;</td>
                    <td class="hide-mobile">$${(p.size_usd || 0).toFixed(2)}</td>
                    <td class="hide-mobile">$${(shares * 1.0).toFixed(2)}</td>
                    <td class="text-right">
                        <div class="value-cell">
                            <span class="val-usd">$${value.toFixed(2)}</span>
                            <span class="val-pnl ${pnlPctClass}">${pnlPctSign}${pnlPctVal.toFixed(2)}%</span>
                        </div>
                    </td>
                    <td class="text-right">
                        <button class="btn-sell">Sell</button>
                        <button class="btn-share">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8M16 6l-4-4-4 4M12 2v13"/>
                            </svg>
                        </button>
                    </td>
                `;
                tbody.appendChild(row);
            });
        }
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

// ── Live Countdown Engine ──────────────────────────────────────────
function formatCountdown(endDateStr) {
    if (!endDateStr) return { text: 'No date', cls: 'neg' };
    const end = new Date(endDateStr);
    if (isNaN(end.getTime())) return { text: 'No date', cls: 'neg' };
    const diffMs = end - Date.now();
    if (diffMs <= 0) return { text: '⚡ Resolving', cls: 'pos' };

    const totalSecs = Math.floor(diffMs / 1000);
    const d = Math.floor(totalSecs / 86400);
    const h = Math.floor((totalSecs % 86400) / 3600);
    const m = Math.floor((totalSecs % 3600) / 60);
    const s = totalSecs % 60;

    let text, cls;
    if (d > 7)  { text = `${d}d ${h}h`;           cls = 'countdown-far'; }
    else if (d > 1) { text = `${d}d ${h}h ${m}m`; cls = 'countdown-mid'; }
    else if (d === 1) { text = `1d ${h}h ${m}m`;   cls = 'countdown-soon'; }
    else if (h > 0) { text = `${h}h ${m}m ${s}s`;  cls = 'countdown-soon'; }
    else            { text = `${m}m ${s}s`;          cls = 'countdown-urgent'; }

    return { text, cls };
}

function updateCountdowns() {
    document.querySelectorAll('.countdown-cell[data-enddate]').forEach(cell => {
        const { text, cls } = formatCountdown(cell.dataset.enddate);
        cell.textContent = text;
        cell.className = `countdown-cell ${cls}`;
    });
}

// Tick every second
setInterval(updateCountdowns, 1000);
