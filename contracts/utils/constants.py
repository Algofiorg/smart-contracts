"""Utility constants"""

from pyteal import *

# CONSTANTS
TRUE = Int(1)
FALSE = Int(0)
SECONDS_PER_YEAR = Int(365 * 24 * 60 * 60)
BYTES_ZERO = BytesZero(Int(64))
ZERO_FEE = Int(0)
ZERO_AMOUNT = Int(0)
MAX_INT_U64 = Int(2**64 - 1)

# SCALE FACTORS
FIXED_18_SCALE_FACTOR = Int(1_000_000_000_000_000_000)
FIXED_15_SCALE_FACTOR = Int(1_000_000_000_000_000)
FIXED_12_SCALE_FACTOR = Int(1_000_000_000_000)
FIXED_9_SCALE_FACTOR = Int(1_000_000_000)
FIXED_6_SCALE_FACTOR = Int(1_000_000)
FIXED_3_SCALE_FACTOR = Int(1_000)

# ASSET PARAMS
ALGO_ASSET_ID = Int(1)
LP_DECIMALS = Int(6)
MAX_CIRCULATION = Int(2**64 - 1)
B_ASSET_DECIMALS = Int(6)
URL = Bytes("")


# TXN INDICES
def relative_index(offset):
    if offset > 0:
        return Txn.group_index() + Int(offset)
    else:
        return Txn.group_index() - Int(abs(offset))


FIRST_TRANSACTION = Int(0)
TWO_PREVIOUS_TRANSACTION = relative_index(-2)
PREVIOUS_TRANSACTION = relative_index(-1)
NEXT_TRANSACTION = relative_index(1)
TWO_SUBSEQUENT_TRANSACTION = relative_index(2)
FINAL_TRANSACTION = Global.group_size() - Int(1)

# TIME CONSTANTS
UNSET_TIME = Int(0)
UNSET_INT = Int(0)
UNSET = Int(0)
UNSET_BYTES = BytesZero(Int(64))
ZERO_FEE = Int(0)
ZERO_AMOUNT = Int(0)
MAX_INT_U64 = Int(2**64 - 1)
