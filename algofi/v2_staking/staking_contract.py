"""A module containing the staking contract."""
from pyteal import *

from algofi.governance.contract_strings import AlgofiVotingEscrowStrings
from algofi.utils.wrapped_var import *
from algofi.v2_staking.constants import *
from algofi.v2_staking.constants import AlgofiStakingScratchSlots
from algofi.v2_staking.contract_strings import (
    AlgofiStakingStrings as StakingStrings,
)
from algofi.v2_staking.subroutines import *


class StakingUser:
    """A user of the staking contract."""

    def __init__(self, account, rewards_program_index, voting_escrow_app_id):
        self.account = account
        self.voting_escrow_app_id = voting_escrow_app_id

        # CURVE REWARDS CONSTANTS
        self.STAKE_PCT = Int(400)
        self.BOOST_PCT = Int(600)

        # USER STATE

        # staking state
        self.total_staked = WrappedVar(
            StakingStrings.user_total_staked, LOCAL_VAR, self.account
        )
        self.scaled_total_staked = WrappedVar(
            StakingStrings.user_scaled_total_staked, LOCAL_VAR, self.account
        )

        # locking multiplier state
        self.boost_multiplier = WrappedVar(
            StakingStrings.boost_multiplier, LOCAL_VAR, self.account
        )

        # rewards state
        self.rewards_program_counter = WrappedVar(
            Concat(
                Bytes(StakingStrings.user_rewards_program_counter_prefix),
                Itob(rewards_program_index.load()),
            ),
            LOCAL_VAR,
            name_to_bytes=False,
            index=self.account,
        )
        self.rewards_coefficient = WrappedVar(
            Concat(
                Bytes(StakingStrings.user_rewards_coefficient_prefix),
                Itob(rewards_program_index.load()),
            ),
            LOCAL_VAR,
            name_to_bytes=False,
            index=self.account,
        )
        self.unclaimed_rewards = WrappedVar(
            Concat(
                Bytes(StakingStrings.user_unclaimed_rewards_prefix),
                Itob(rewards_program_index.load()),
            ),
            LOCAL_VAR,
            name_to_bytes=False,
            index=self.account,
        )

        # external state
        self.opted_into_voting_escrow = App.optedIn(
            self.account, self.voting_escrow_app_id
        )
        self.external_boost_multiplier = WrappedVar(
            AlgofiVotingEscrowStrings.user_boost_multiplier,
            LOCAL_EX_VAR,
            index=self.account,
            app_id=self.voting_escrow_app_id,
        ).get()

    def update_boost_multiplier(self):
        """Update the boost multiplier."""
        return Seq(
            [
                If(
                    And(
                        self.voting_escrow_app_id != UNSET,
                        self.opted_into_voting_escrow,
                    )
                )
                .Then(
                    Seq(
                        [
                            # update vebank data
                            InnerTxnBuilder.Begin(),
                            InnerTxnBuilder.SetFields(
                                {
                                    TxnField.type_enum: TxnType.ApplicationCall,
                                    TxnField.application_id: self.voting_escrow_app_id,
                                    TxnField.application_args: [
                                        Bytes(
                                            AlgofiVotingEscrowStrings.update_vebank_data
                                        )
                                    ],
                                    TxnField.accounts: [self.account],
                                    TxnField.fee: ZERO_FEE,
                                }
                            ),
                            InnerTxnBuilder.Submit(),
                            # get updated boost multiplier
                            self.external_boost_multiplier,
                            self.boost_multiplier.put(
                                self.external_boost_multiplier.value()
                            ),
                        ]
                    )
                )
                .Else(self.boost_multiplier.put(ZERO_AMOUNT))
            ]
        )

    def update_scaled_total_staked(self, global_total_staked):
        """
        Curve Rewards Formula

        stake_component = user_total_staked * 40%
        boost_component = boost_multiplier * global_total_staked * 60%
        MIN(
            stake_component + boost_component,
            user_total_staked
        )
        If boost_multiplier == 0 --> 40% * user_total_staked
        If boost_multiplier == 1 --> user_total_staked

        As such, the best multiplier a user can get is user_total_staked / 40% * user_total_staked = 2.5x
        """
        stake_component = WideRatio(
            [self.total_staked.get(), self.STAKE_PCT], [FIXED_3_SCALE_FACTOR]
        )
        boost_component = WideRatio(
            [self.boost_multiplier.get(), global_total_staked, self.BOOST_PCT],
            [FIXED_15_SCALE_FACTOR],
        )
        scaled_total_staked = stake_component + boost_component

        return Seq(
            [
                # return max of total staked and scaled total staked
                self.scaled_total_staked.put(
                    minimum(self.total_staked.get(), scaled_total_staked)
                )
            ]
        )


class StakingRewardsProgram:
    """A class for managing staking rewards programs."""

    def __init__(
        self,
        rewards_escrow_account,
        rewards_program_index,
        staking_asset_id,
        scaled_total_staked,
    ):
        # STAKING STATE
        self.rewards_escrow_account = rewards_escrow_account
        self.staking_asset_id = staking_asset_id
        self.scaled_total_staked = scaled_total_staked

        # SCRATCH VARS
        self.rewards_to_issue = ScratchVar(
            TealType.uint64, AlgofiStakingScratchSlots.rewards_to_issue
        )
        self.rewards_available = ScratchVar(
            TealType.uint64, AlgofiStakingScratchSlots.rewards_available
        )

        # REWARDS PROGRAM STATE
        self.program_counter = WrappedVar(
            Concat(
                Bytes(StakingStrings.rewards_program_counter_prefix),
                Itob(rewards_program_index),
            ),
            GLOBAL_VAR,
            name_to_bytes=False,
        )
        self.asset_id = WrappedVar(
            Concat(
                Bytes(StakingStrings.rewards_asset_id_prefix),
                Itob(rewards_program_index),
            ),
            GLOBAL_VAR,
            name_to_bytes=False,
        )
        self.rewards_per_second = WrappedVar(
            Concat(
                Bytes(StakingStrings.rewards_per_second_prefix),
                Itob(rewards_program_index),
            ),
            GLOBAL_VAR,
            name_to_bytes=False,
        )
        self.coefficient = WrappedVar(
            Concat(
                Bytes(StakingStrings.rewards_coefficient_prefix),
                Itob(rewards_program_index),
            ),
            GLOBAL_VAR,
            name_to_bytes=False,
        )
        self.rewards_issued = WrappedVar(
            Concat(
                Bytes(StakingStrings.rewards_issued_prefix),
                Itob(rewards_program_index),
            ),
            GLOBAL_VAR,
            name_to_bytes=False,
        )
        self.rewards_paid = WrappedVar(
            Concat(
                Bytes(StakingStrings.rewards_paid_prefix),
                Itob(rewards_program_index),
            ),
            GLOBAL_VAR,
            name_to_bytes=False,
        )

    def initialize_program(self, asset_id, rewards_per_second):
        """Initialize a rewards program."""

        return Seq(
            [
                # increment program counter
                increment(self.program_counter, Int(1)),
                # init asset_id
                self.asset_id.put(asset_id),
                # init rps
                self.rewards_per_second.put(rewards_per_second),
                # set coefficient to 0
                self.coefficient.put(BytesZero(Int(64))),
                # set rewards issued and payed to 0
                self.rewards_issued.put(ZERO_AMOUNT),
                self.rewards_paid.put(ZERO_AMOUNT),
            ]
        )

    def update_rewards_per_second(self, new_rewards_per_second):
        """Update the rewards per second."""

        return Seq([self.rewards_per_second.put(new_rewards_per_second)])

    def update_coefficient(self, time_delta):
        """Update the coefficient."""

        rewards_to_issue = time_delta * self.rewards_per_second.get()
        latest_coefficient_term = BytesDiv(
            BytesMul(
                Itob(FIXED_18_SCALE_FACTOR), Itob(self.rewards_to_issue.load())
            ),
            Itob(self.scaled_total_staked),
        )

        return Seq(
            [
                If(self.scaled_total_staked > Int(0)).Then(
                    Seq(
                        [
                            # calculate rewards to issue
                            self.rewards_to_issue.store(rewards_to_issue),
                            # increment coefficient
                            self.coefficient.put(
                                BytesAdd(
                                    self.coefficient.get(),
                                    latest_coefficient_term,
                                )
                            ),
                            # increment rewards issued
                            increment(
                                self.rewards_issued,
                                self.rewards_to_issue.load(),
                            ),
                        ]
                    )
                )
            ]
        )

    def update_user_rewards(self, staking_user):
        """Update a user's rewards."""

        latest_user_rewards = Btoi(
            BytesDiv(
                BytesMul(
                    BytesMinus(
                        self.coefficient.get(),
                        staking_user.rewards_coefficient.get(),
                    ),
                    Itob(staking_user.scaled_total_staked.get()),
                ),
                Itob(FIXED_18_SCALE_FACTOR),
            )
        )

        return Seq(
            [
                # reset user rewards program variables if necessary
                If(
                    staking_user.rewards_program_counter.get()
                    != self.program_counter.get()
                ).Then(
                    Seq(
                        [
                            # reset user claimable rewards
                            staking_user.unclaimed_rewards.put(ZERO_AMOUNT),
                            # set user rewards index to 0
                            staking_user.rewards_coefficient.put(BYTES_ZERO),
                            # set user program counter to current program
                            staking_user.rewards_program_counter.put(
                                self.program_counter.get()
                            ),
                        ]
                    )
                ),
                # add latest user rewards to unclaimed rewards
                increment(staking_user.unclaimed_rewards, latest_user_rewards),
                # set user rewards coefficient to latest coefficient
                staking_user.rewards_coefficient.put(self.coefficient.get()),
            ]
        )

    def claim_rewards(self, staking_user):
        """Claims a users' rewards."""
        return Seq(
            [
                # send rewards
                If(self.asset_id.get() == ALGO_ASSET_ID)
                .Then(
                    send_algo_from_address(
                        self.rewards_escrow_account,
                        staking_user.unclaimed_rewards.get(),
                        staking_user.account,
                    )
                )
                .Else(
                    send_asa_from_address(
                        self.rewards_escrow_account,
                        self.asset_id.get(),
                        staking_user.unclaimed_rewards.get(),
                        staking_user.account,
                    )
                ),
                increment(
                    self.rewards_paid, staking_user.unclaimed_rewards.get()
                ),
                # zero users unclaimed rewards
                staking_user.unclaimed_rewards.put(ZERO_AMOUNT),
            ]
        )


class StakingContract:
    """Contract for staking assets."""

    def __init__(self, rewards_program_count, staked_asset_is_algo=False):
        self.raw_rewards_program_count = rewards_program_count
        self.staked_asset_is_algo = staked_asset_is_algo

        # SCRATCH VARS
        self.rewards_program_index = ScratchVar(
            TealType.uint64, AlgofiStakingScratchSlots.rewards_program_index
        )
        self.amount_staked = ScratchVar(
            TealType.uint64, AlgofiStakingScratchSlots.amount_staked
        )

        # ADMIN STATE
        self.dao_address = WrappedVar(StakingStrings.dao_address, GLOBAL_VAR)
        self.emergency_dao_address = WrappedVar(
            StakingStrings.emergency_dao_address, GLOBAL_VAR
        )
        self.rewards_escrow_account = WrappedVar(
            StakingStrings.rewards_escrow_account, GLOBAL_VAR
        )
        self.rewards_program_count = WrappedVar(
            StakingStrings.rewards_program_count, GLOBAL_VAR
        )
        self.voting_escrow_app_id = WrappedVar(
            StakingStrings.voting_escrow_app_id, GLOBAL_VAR
        )

        # IMMUTABLE GLOBAL STATE
        self.asset_id = WrappedVar(StakingStrings.asset_id, GLOBAL_VAR)

        # STAKING STATE
        self.total_staked = WrappedVar(StakingStrings.total_staked, GLOBAL_VAR)
        self.scaled_total_staked = WrappedVar(
            StakingStrings.scaled_total_staked, GLOBAL_VAR
        )

        # REWARDS PROGRAM STATE
        self.latest_time = WrappedVar(StakingStrings.latest_time, GLOBAL_VAR)
        self.rewards_program = StakingRewardsProgram(
            self.rewards_escrow_account.get(),
            self.rewards_program_index.load(),
            self.asset_id.get(),
            self.scaled_total_staked.get(),
        )

        # USER STATE
        self.calling_user = StakingUser(
            Txn.accounts[0],
            self.rewards_program_index,
            self.voting_escrow_app_id.get(),
        )
        self.target_user = StakingUser(
            Txn.accounts[1],
            self.rewards_program_index,
            self.voting_escrow_app_id.get(),
        )

    # HELPERS

    def verify_staked_asset_payment_txn_to_market(self, idx):
        """Verify that the transaction is a payment to the market."""
        if self.staked_asset_is_algo:
            return verify_txn_is_payment(
                idx, Global.current_application_address()
            )
        else:
            return verify_txn_is_asset_transfer(
                idx, Global.current_application_address(), self.asset_id.get()
            )

    def get_staked_asset_received(self, idx):
        """Get the amount of staked asset received in the transaction."""
        if self.staked_asset_is_algo:
            return Gtxn[idx].amount()
        else:
            return Gtxn[idx].asset_amount()

    def send_staked_asset(self, amount):
        """Send the staked asset to the caller."""
        if self.staked_asset_is_algo:
            return send_algo(amount, Txn.sender())
        else:
            return send_asa(self.asset_id.get(), amount, Txn.sender())

    def for_each_rewards_program(self, do):
        """For each rewards program, do something."""
        return For(
            self.rewards_program_index.store(Int(0)),
            self.rewards_program_index.load()
            < self.rewards_program_count.get(),
            self.rewards_program_index.store(
                self.rewards_program_index.load() + Int(1)
            ),
        ).Do(do)

    # CREATION

    def on_creation(self):
        """Initialize the staking contract."""
        asset_id = Txn.assets[0]
        voting_escrow_app_id = Txn.applications[1]

        dao_address = Txn.accounts[1]
        emergency_dao_address = Txn.accounts[2]

        return Seq(
            # check that this staking contract was initialized with the correct boolean
            (
                [MagicAssert(asset_id == ALGO_ASSET_ID)]
                if (self.staked_asset_is_algo)
                else []
            )
            + [
                # SET ADMIN VARIABLES
                self.dao_address.put(dao_address),
                self.emergency_dao_address.put(emergency_dao_address),
                self.rewards_escrow_account.put(Global.zero_address()),
                self.voting_escrow_app_id.put(voting_escrow_app_id),
                self.total_staked.put(ZERO_AMOUNT),
                self.scaled_total_staked.put(ZERO_AMOUNT),
                # SET STAKING PARAMETERS
                self.asset_id.put(asset_id),
                # INITIALIZE REWARDS PROGRAMS
                self.rewards_program_count.put(
                    Int(self.raw_rewards_program_count)
                ),
                self.for_each_rewards_program(
                    self.rewards_program.initialize_program(
                        ALGO_ASSET_ID, ZERO_AMOUNT
                    )
                ),
                self.latest_time.put(Global.latest_timestamp()),
                Approve(),
            ]
        )

    # ADMIN FUNCTIONS

    def on_initialize_rewards_escrow_account(self):
        """Initialize the rewards escrow account."""
        rewards_escrow_account = Txn.accounts[1]

        return Seq(
            [
                # verify rewards escrow is not already set
                MagicAssert(
                    self.rewards_escrow_account.get() == Global.zero_address()
                ),
                # verify account is being rekeyed in the previous transaction
                MagicAssert(
                    Gtxn[PREVIOUS_TRANSACTION].sender()
                    == rewards_escrow_account
                ),
                MagicAssert(
                    Gtxn[PREVIOUS_TRANSACTION].close_remainder_to()
                    == Global.zero_address()
                ),
                MagicAssert(
                    Gtxn[PREVIOUS_TRANSACTION].rekey_to()
                    == Global.current_application_address()
                ),
                # set rewards escrow account
                self.rewards_escrow_account.put(rewards_escrow_account),
                Approve(),
            ]
        )

    def on_set_voting_escrow_app_id(self):
        """Set the voting escrow app id."""

        new_voting_escrow_app_id = Txn.applications[1]

        return Seq(
            [
                # set rps pusher
                self.voting_escrow_app_id.put(new_voting_escrow_app_id),
                Approve(),
            ]
        )

    def on_set_rewards_program(self):
        """Set the rewards program."""

        index = Btoi(Txn.application_args[1])
        asset_id = Txn.assets[0]
        rewards_per_second = Btoi(Txn.application_args[2])

        return Seq(
            [
                # verify index is valid
                MagicAssert(index < self.rewards_program_count.get()),
                # set the rewards program index to update
                self.rewards_program_index.store(index),
                # set the rewards program
                self.rewards_program.initialize_program(
                    asset_id, rewards_per_second
                ),
                # opt rewards escrow account into asset
                If(asset_id != ALGO_ASSET_ID).Then(
                    send_asa_from_address(
                        self.rewards_escrow_account.get(),
                        asset_id,
                        ZERO_AMOUNT,
                        self.rewards_escrow_account.get(),
                    )
                ),
                Approve(),
            ]
        )

    def on_update_rewards_per_second(self):
        """Update the rewards per second."""

        index = Btoi(Txn.application_args[1])
        rewards_per_second = Btoi(Txn.application_args[2])

        return Seq(
            [
                # verify index is valid
                MagicAssert(index < self.rewards_program_count.get()),
                # set the rewards program index to update
                self.rewards_program_index.store(index),
                # set the rewards program
                self.rewards_program.update_rewards_per_second(
                    rewards_per_second
                ),
                Approve(),
            ]
        )

    def on_opt_into_asset(self):
        """Opt into an asset."""

        asset_id = Txn.assets[0]

        return Seq(
            [
                # opt into asa
                send_asa(
                    asset_id, ZERO_AMOUNT, Global.current_application_address()
                ),
                Approve(),
            ]
        )

    def on_reclaim_rewards_assets(self):
        """Reclaim rewards assets."""

        reclaim_asset_id = Btoi(Txn.application_args[1])
        reclaim_amount = Btoi(Txn.application_args[2])

        return Seq(
            [
                If(reclaim_asset_id == ALGO_ASSET_ID)
                .Then(
                    send_algo_from_address(
                        self.rewards_escrow_account.get(),
                        reclaim_amount,
                        Txn.sender(),
                    )
                )
                .Else(
                    send_asa_from_address(
                        self.rewards_escrow_account.get(),
                        reclaim_asset_id,
                        reclaim_amount,
                        Txn.sender(),
                    )
                ),
                Approve(),
            ]
        )

    # OPT IN / CLOSE OUT

    def on_user_opt_in(self):
        """Opt a user into the staking contract."""

        return Seq(
            [
                # initialize user state
                self.calling_user.total_staked.put(ZERO_AMOUNT),
                self.calling_user.scaled_total_staked.put(ZERO_AMOUNT),
                # initialize rewards program states
                self.for_each_rewards_program(
                    Seq(
                        [
                            self.rewards_program.update_user_rewards(
                                self.calling_user
                            ),
                        ]
                    )
                ),
                # set initial boost multiplier to zero
                self.calling_user.boost_multiplier.put(ZERO_AMOUNT),
                Approve(),
            ]
        )

    def on_user_close_out(self):
        """Close out a user from the staking contract."""

        ignore_unclaimed_rewards = Btoi(Txn.application_args[1])

        return Seq(
            [
                # check that user has no stake
                MagicAssert(
                    self.calling_user.total_staked.get() == ZERO_AMOUNT
                ),
                # check that user has no unclaimed rewards
                If(ignore_unclaimed_rewards == FALSE).Then(
                    self.for_each_rewards_program(
                        MagicAssert(
                            self.calling_user.unclaimed_rewards.get()
                            == ZERO_AMOUNT
                        )
                    ),
                ),
                Approve(),
            ]
        )

    # USER FUNCTIONS

    def update_user(self, staking_user):
        """Update a user state."""

        time_delta = Global.latest_timestamp() - self.latest_time.get()

        return Seq(
            [
                # update rewards program states
                self.for_each_rewards_program(
                    Seq(
                        [
                            self.rewards_program.update_coefficient(
                                time_delta
                            ),
                            self.rewards_program.update_user_rewards(
                                staking_user
                            ),
                        ]
                    )
                ),
                self.latest_time.put(Global.latest_timestamp()),
                # update user scaled stake
                # decrement global scaled total staked
                decrement(
                    self.scaled_total_staked,
                    staking_user.scaled_total_staked.get(),
                ),
                # update boost multiplier
                staking_user.update_boost_multiplier(),
                # update user scaled total staked
                staking_user.update_scaled_total_staked(
                    self.total_staked.get()
                ),
                # increment global scaled total staked
                increment(
                    self.scaled_total_staked,
                    staking_user.scaled_total_staked.get(),
                ),
            ]
        )

    def on_stake(self):
        return Seq(
            [
                # verify payment
                self.verify_staked_asset_payment_txn_to_market(
                    PREVIOUS_TRANSACTION
                ),
                # cache amount staked
                self.amount_staked.store(
                    self.get_staked_asset_received(PREVIOUS_TRANSACTION)
                ),
                # decrement user from scaled total staked
                decrement(
                    self.scaled_total_staked,
                    self.calling_user.scaled_total_staked.get(),
                ),
                # increment user total staked
                increment(
                    self.calling_user.total_staked, self.amount_staked.load()
                ),
                # increment global total staked
                increment(self.total_staked, self.amount_staked.load()),
                # update user scaled total staked
                self.calling_user.update_scaled_total_staked(
                    self.total_staked.get()
                ),
                # increment global scaled total staked
                increment(
                    self.scaled_total_staked,
                    self.calling_user.scaled_total_staked.get(),
                ),
                Approve(),
            ]
        )

    def on_unstake(self):
        """Unstake an amount of staked asset."""
        amount = Btoi(Txn.application_args[1])

        return Seq(
            [
                # verify the user has enough staked to unstake this amount
                MagicAssert(self.calling_user.total_staked.get() >= amount),
                # send asset
                self.send_staked_asset(amount),
                # decrement user from scaled total staked
                decrement(
                    self.scaled_total_staked,
                    self.calling_user.scaled_total_staked.get(),
                ),
                # decrement user total staked
                decrement(self.calling_user.total_staked, amount),
                # decrement global total staked
                decrement(self.total_staked, amount),
                # update user scaled total staked
                self.calling_user.update_scaled_total_staked(
                    self.total_staked.get()
                ),
                # increment global scaled total staked
                increment(
                    self.scaled_total_staked,
                    self.calling_user.scaled_total_staked.get(),
                ),
                Approve(),
            ]
        )

    def on_claim_rewards(self):
        """Claim the user rewards."""
        rewards_program_index = Btoi(Txn.application_args[1])

        return Seq(
            [
                # verify index is valid
                MagicAssert(
                    rewards_program_index < self.rewards_program_count.get()
                ),
                # cache target rewards program index
                self.rewards_program_index.store(rewards_program_index),
                # claim rewards
                self.rewards_program.claim_rewards(self.calling_user),
                Approve(),
            ]
        )

    def on_update_target_user(self):
        """Update the target user."""

        return Seq(
            [
                # update rewards
                self.update_user(self.target_user),
                Approve(),
            ]
        )

    def approval_program(self):
        """Staking contract approval program."""
        sender_is_dao = Or(
            Txn.sender() == self.dao_address.get(),
            Txn.sender() == self.emergency_dao_address.get(),
        )
        is_no_op = And(Txn.on_completion() == OnComplete.NoOp)

        return Cond(
            [Txn.application_id() == Int(0), self.on_creation()],
            [Txn.on_completion() == OnComplete.OptIn, self.on_user_opt_in()],
            # admin calls
            [
                sender_is_dao,
                Cond(
                    [
                        is_no_op,
                        Cond(
                            [
                                Txn.application_args[0]
                                == Bytes(
                                    StakingStrings.initialize_rewards_escrow_account
                                ),
                                self.on_initialize_rewards_escrow_account(),
                            ],
                            [
                                Txn.application_args[0]
                                == Bytes(
                                    StakingStrings.set_voting_escrow_app_id
                                ),
                                self.on_set_voting_escrow_app_id(),
                            ],
                            [
                                Txn.application_args[0]
                                == Bytes(StakingStrings.set_rewards_program),
                                self.on_set_rewards_program(),
                            ],
                            [
                                Txn.application_args[0]
                                == Bytes(
                                    StakingStrings.update_rewards_per_second
                                ),
                                self.on_update_rewards_per_second(),
                            ],
                            [
                                Txn.application_args[0]
                                == Bytes(StakingStrings.opt_into_asset),
                                self.on_opt_into_asset(),
                            ],
                            [
                                Txn.application_args[0]
                                == Bytes(
                                    StakingStrings.reclaim_rewards_assets
                                ),
                                self.on_reclaim_rewards_assets(),
                            ],
                        ),
                    ]
                ),
            ],
            # all other application calls
            [
                is_no_op,
                Cond(
                    # unprotected
                    [
                        Txn.application_args[0]
                        == Bytes(StakingStrings.farm_ops),
                        Approve(),
                    ],
                    [
                        Txn.application_args[0]
                        == Bytes(StakingStrings.update_target_user),
                        self.on_update_target_user(),
                    ],
                    [
                        TRUE,
                        Seq(
                            [
                                self.update_user(self.calling_user),
                                Cond(
                                    [
                                        Txn.application_args[0]
                                        == Bytes(StakingStrings.stake),
                                        self.on_stake(),
                                    ],
                                    [
                                        Txn.application_args[0]
                                        == Bytes(StakingStrings.unstake),
                                        self.on_unstake(),
                                    ],
                                    [
                                        Txn.application_args[0]
                                        == Bytes(StakingStrings.claim_rewards),
                                        self.on_claim_rewards(),
                                    ],
                                ),
                            ]
                        ),
                    ],
                ),
            ],
            # opt in / out
            [
                Txn.on_completion() == OnComplete.CloseOut,
                self.on_user_close_out(),
            ],
            # disallowed
            [Txn.on_completion() == OnComplete.DeleteApplication, Reject()],
        )

    def clear_state_program(self):
        return Seq(
            [
                # decrement global total_staked by user's total_staked to reduce rewards dilution
                decrement(
                    self.total_staked, self.calling_user.total_staked.get()
                ),
                # decrement global scaled_total_staked by user's scaled_total_staked to reduce rewards dilution
                decrement(
                    self.scaled_total_staked,
                    self.calling_user.scaled_total_staked.get(),
                ),
                Approve(),
            ]
        )
