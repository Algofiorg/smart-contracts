"""Constants for the staking contracts"""
from pyteal import *

from contracts.utils.constants import *

# DEV MODE FLAG
DEV_MODE = False


class StakingScratchSlots:
    rewards_program_index = 0
    amount_staked = 1

    rewards_to_issue = 10
    rewards_available = 11
