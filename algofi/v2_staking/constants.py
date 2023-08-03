"""Constants for the staking contracts"""
from pyteal import *

from algofi.utils.constants import *

# DEV MODE FLAG
DEV_MODE = False


class AlgofiStakingScratchSlots:
    rewards_program_index = 0
    amount_staked = 1

    rewards_to_issue = 10
    rewards_available = 11
