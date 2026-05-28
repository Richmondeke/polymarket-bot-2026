from bot.risk_manager import risk
from bot.client import clob
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

balance = clob.get_usdc_balance()
status = risk.get_status(balance)
print("=== RISK MANAGER STATUS ===")
for k, v in status.items():
    print(f"  {k:20}: {v}")
