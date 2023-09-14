"""Defines constants used in the governance contracts."""

from pyteal import *

from contracts.utils.constants import *

# DEV MODE FLAG
DEV_MODE = True

# LOCK TIME CONSTANTS
MIN_LOCK_TIME_SECONDS = Int(30 if DEV_MODE else 60 * 60 * 24 * 7)
MAX_LOCK_TIME_SECONDS = Int(600 if DEV_MODE else 60 * 60 * 24 * 365 * 4)

# GOVERNANCE CONSTANTS
MIN_BALANCE_PROPOSAL = Int(606500)
PROPOSAL_CREATION_DELAY = Int(0)

# CONTRACT SCHEMAS
GLOBAL_BYTES_PROPOSAL_CONTRACT = Int(14)
GLOBAL_INTS_PROPOSAL_CONTRACT = Int(14)
LOCAL_BYTES_PROPOSAL_CONTRACT = Int(0)
LOCAL_INTS_PROPOSAL_CONTRACT = Int(2)


# SCRATCH SLOTS
class AdminContractScratchSlots:
    """A class containing scratch slots for the admin contract."""

    delegatee_storage_address = 0
    proposal_app_id = 1
    min_balance = 2
    closeout_user_address = 3


class ProposalFactoryScratchSlots:
    """A class containing scratch slots for the proposal factory contract."""

    min_balance = 0
