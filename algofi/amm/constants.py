"""Constants for AlgoFi AMM."""

from pyteal import *

from algofi.utils.constants import *

# POOL SCHEMA
POOL_GLOBAL_NUM_BYTES = Int(4)
POOL_GLOBAL_NUM_UINTS = Int(32)

# INTIALIZATION GROUP TXN INDICES
N_FUND_MANAGER_TXN = 0
N_FUND_LOGIC_SIG_TXN = 1
N_OPT_IN_LOGIC_SIG_TXN = 2
N_INITIALIZE_POOL_TXN = 3

# MANAGER PARAMS
MAX_VALIDATOR_COUNT = Int(8)
DEFAULT_RESERVE_FACTOR = Int(175000)

# POOL PARAMS
MAX_ASSET_RATIO = Int(1000000000)
DEFAULT_SWAP_FEE_PCT_SCALED = Int(2500)
MIN_POOL_BALANCE = Int(1000)
DEFAULT_PARAM_UPDATE_DELAY = Int(5)
MAX_AMPLIFICATION_FACTOR = Int(400_000_000)

# STABLE POOL PARAMS
DEFAULT_STABLESWAP_FEE_PCT_SCALED = Int(1000)

# ADMIN PARAMS
INIT_FLASH_LOAN_FEE = Int(1000)
INIT_MAX_FLASH_LOAN_RATIO = Int(100000)


# POOL TRANSACTION INDICES
def relative_index(offset):
    if offset > 0:
        return Txn.group_index() + Int(offset)
    else:
        return Txn.group_index() - Int(abs(offset))


# POOL
# 1 - asset1 in
# 2 - asset2 in
# 3 - pool
# 4 - redeem asset1 residual
# 5 - redeem asset2 residual
POOL__ASSET1_IN_IDX = relative_index(-2)
POOL__ASSET2_IN_IDX = relative_index(-1)
POOL__REDEEM_POOL_ASSET1_RESIDUAL_IDX = relative_index(1)
POOL__REDEEM_POOL_ASSET2_RESIDUAL_IDX = relative_index(2)

# POOL Redeem
REDEEM_POOL_ASSET1_RESIDUAL__POOL_IDX = relative_index(-1)

REDEEM_POOL_ASSET2_RESIDUAL__POOL_IDX = relative_index(-2)

# BURN
# 1 - lp in
# 2 - burn asset 1 out
# 3 - burn asset 2 out
BURN_ASSET1_OUT__LP_IN_IDX = relative_index(-1)
BURN_ASSET1_OUT__BURN_ASSET2_OUT_IDX = relative_index(1)

BURN_ASSET2_OUT__LP_IN_IDX = relative_index(-2)
BURN_ASSET2_OUT__BURN_ASSET1_OUT_IDX = relative_index(-1)

# SWAP
# 1 - asset in
# 2 - swap
# 3 - redeem residual (swap_for_exact only)
SWAP__SWAP_IN_IDX = relative_index(-1)
SWAP__REDEEM_SWAP_RESIDUAL_IDX = relative_index(1)

# SWAP Redeem
REDEEM_SWAP_RESIDUAL__SWAP_IDX = relative_index(-1)

# FLASH LOAN
# 1 - flash loan
# ...
# FINAL - flash loan repay txn
FLASH_LOAN_IDX = Int(0)
FLASH_LOAN_REPAY_IDX = Global.group_size() - Int(1)
