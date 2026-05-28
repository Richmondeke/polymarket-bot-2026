import asyncio
from polynode.trading.onboarding import derive_deposit_wallet_address, detect_wallet_type
from web3 import Web3

eoa = "0x8E1af49c1E18fE0351791d5052c9e76200C63081"
dw_addr = derive_deposit_wallet_address(eoa)
print("EOA Address:        ", eoa)
print("Derived DW Address: ", dw_addr)

async def check():
    wallet_info = await detect_wallet_type(eoa)
    print("Auto-detected wallet type:", wallet_info)

asyncio.run(check())
