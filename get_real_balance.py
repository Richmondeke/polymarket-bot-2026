from bot.client import clob

def get_real():
    try:
        collateral_address = clob.client.get_collateral_address()
        balance_allowance = clob.client.get_balance_allowance(collateral_address)
        print("Balance/Allowance object:", balance_allowance)
        print("Real CTF Proxy Balance:", float(balance_allowance.get("balance", 0)) / 1e6)
    except Exception as e:
        print("Error getting proxy balance:", e)

get_real()
