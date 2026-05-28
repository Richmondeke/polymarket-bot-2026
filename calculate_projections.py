import sys

# Constants
STARTING_BANKROLL = 13.43
TRADES_PER_DAY = 5
WIN_RATE = 0.58
AVG_GAIN_PCT = 0.15   # 15% gain on wins
AVG_LOSS_PCT = 0.10   # 10% loss on losses
CAPITAL_TURNOVER_DAYS = 2.0  # 48 hours capital recycling

# Average expected return per trade:
# E = (Win_Rate * Gain) - ((1 - Win_Rate) * Loss)
EXPECTED_RETURN_PER_TRADE = (WIN_RATE * AVG_GAIN_PCT) - ((1.0 - WIN_RATE) * AVG_LOSS_PCT)
# E = (0.58 * 0.15) - (0.42 * 0.10) = 0.087 - 0.042 = 0.045 (4.5% per trade)

print(f"Expected Return per Trade: {EXPECTED_RETURN_PER_TRADE * 100:.2f}%")

def project_compounding(days):
    equity = STARTING_BANKROLL
    history = []
    for day in range(1, days + 1):
        # We execute 5 trades per day.
        # But wait! With MAX_RESOLUTION_DAYS=2.0, our positions resolve in <= 48 hours.
        # Therefore, we can compound our capital every 2 days.
        # So we run 5 trades per day for 2 days (10 trades), then compound the returns.
        # Alternatively, if we compound on a trade-by-trade basis assuming fractional sizing:
        for trade in range(TRADES_PER_DAY):
            # Dynamic position size: 8% of total equity (conservative fraction) or minimum $1.05
            pos_size = max(1.05, equity * 0.08)
            # Cap max position size at 15% of equity to protect bankroll
            pos_size = min(pos_size, equity * 0.15)
            
            # Outcome: win (58% probability) or loss (42% probability)
            # Compound the expected outcome value:
            # New Equity = Equity + (Win_Rate * pos_size * AVG_GAIN_PCT) - ((1 - Win_Rate) * pos_size * AVG_LOSS_PCT)
            trade_expected_return = pos_size * EXPECTED_RETURN_PER_TRADE
            equity += trade_expected_return
        
        history.append((day, equity))
    return history

# 1. Hour-by-hour (24h)
hours_history = []
temp_equity = STARTING_BANKROLL
# 5 trades per day means 1 trade every 4.8 hours on average.
for h in range(1, 25):
    # Every 4.8 hours we complete a trade
    if h % 5 == 0 or h == 24:
        pos_size = max(1.05, temp_equity * 0.08)
        pos_size = min(pos_size, temp_equity * 0.15)
        temp_equity += pos_size * EXPECTED_RETURN_PER_TRADE
    hours_history.append((h, temp_equity))

# 2. Daily (30 Days)
daily_history = project_compounding(30)

# 3. Weekly (12 Weeks)
weekly_history = []
for w in range(1, 13):
    weekly_equity = daily_history[min(w * 7 - 1, len(daily_history) - 1)][1] if w * 7 <= 30 else daily_history[-1][1] * (1.166 ** (w - 4)) # extrapolating compound rate beyond 30 days
    weekly_history.append((w, weekly_equity))

# Output tables
print("\n--- HOUR-BY-HOUR (24 HOURS) ---")
print("| Hour | Projected Equity ($) | Net Growth ($) |")
print("|------|----------------------|----------------|")
for h, eq in hours_history[::4]: # Show every 4 hours for brevity
    print(f"| {h:2d}h  | ${eq:20.2f} | ${eq - STARTING_BANKROLL:14.2f} |")

print("\n--- DAILY (30 DAYS) ---")
print("| Day | Projected Equity ($) | Cumulative Return | ROI (%) |")
print("|-----|----------------------|-------------------|---------|")
for day in [1, 2, 3, 5, 7, 10, 14, 21, 30]:
    eq = daily_history[day - 1][1]
    roi = ((eq - STARTING_BANKROLL) / STARTING_BANKROLL) * 100
    print(f"| Day {day:02d} | ${eq:20.2f} | ${eq - STARTING_BANKROLL:17.2f} | {roi:7.1f}% |")

print("\n--- WEEKLY (12 WEEKS) ---")
print("| Week | Projected Equity ($) | Cumulative Return | ROI (%) |")
print("|------|----------------------|-------------------|---------|")
for w in [1, 2, 3, 4, 6, 8, 10, 12]:
    eq = daily_history[w * 7 - 1][1] if w * 7 <= 30 else daily_history[-1][1] * ((1.0 + EXPECTED_RETURN_PER_TRADE * 5 * 7 * 0.11)**(w - 4)) # compound weekly rate for weeks > 4
    roi = ((eq - STARTING_BANKROLL) / STARTING_BANKROLL) * 100
    print(f"| Week {w:02d} | ${eq:20.2f} | ${eq - STARTING_BANKROLL:17.2f} | {roi:7.1f}% |")
