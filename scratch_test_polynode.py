import os
import sys
from polynode import PolyNode
from bot import config

# Need to set up basic mock to see if PolyNode loads
client = PolyNode(
    host=config.CLOB_HOST,
    chain_id=config.CHAIN_ID,
    key=config.POLYGON_PRIVATE_KEY,
    exchange_version="V2"
)
print("PolyNode client initialized successfully:", client)
