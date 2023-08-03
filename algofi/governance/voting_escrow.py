"""Vote Escrow Contract"""

from pyteal import *

from algofi.governance.constants import *
from algofi.governance.contract_strings import AlgofiVotingEscrowStrings
from algofi.governance.subroutines import (
    MagicAssert,
    decrement,
    increment,
    opt_into_asa,
    send_asa,
    verify_txn_is_sending_asa_to_contract,
)
from algofi.utils.wrapped_var import *


class AlgofiVotingEscrowUser:
    """Data structure for user state in the voting escrow contract"""

    def __init__(self, user_index):
        # LOCAL STATE
        self.amount_locked = WrappedVar(
            AlgofiVotingEscrowStrings.user_amount_locked, LOCAL_VAR, user_index
        )
        self.lock_start_time = WrappedVar(
            AlgofiVotingEscrowStrings.user_lock_start_time,
            LOCAL_VAR,
            user_index,
        )
        self.lock_duration = WrappedVar(
            AlgofiVotingEscrowStrings.user_lock_duration, LOCAL_VAR, user_index
        )
        self.amount_vebank = WrappedVar(
            AlgofiVotingEscrowStrings.user_amount_vebank, LOCAL_VAR, user_index
        )
        self.boost_multiplier = WrappedVar(
            AlgofiVotingEscrowStrings.user_boost_multiplier,
            LOCAL_VAR,
            user_index,
        )
        self.update_time = WrappedVar(
            AlgofiVotingEscrowStrings.user_last_update_time,
            LOCAL_VAR,
            user_index,
        )

    def get_lock_end_time(self):
        """Get the time at which the lock expires"""
        return self.lock_start_time.get() + self.lock_duration.get()


class AlgofiVotingEscrow:
    """Vote Escrow Contract"""

    def __init__(self):
        # GLOBAL STATE
        self.dao_address = WrappedVar(
            AlgofiVotingEscrowStrings.dao_address, GLOBAL_VAR
        )
        self.emergency_dao_address = WrappedVar(
            AlgofiVotingEscrowStrings.emergency_dao_address, GLOBAL_VAR
        )
        self.asset_id = WrappedVar(
            AlgofiVotingEscrowStrings.asset_id, GLOBAL_VAR
        )
        self.total_locked = WrappedVar(
            AlgofiVotingEscrowStrings.total_locked, GLOBAL_VAR
        )
        self.total_vebank = WrappedVar(
            AlgofiVotingEscrowStrings.total_vebank, GLOBAL_VAR
        )
        self.admin_contract_app_id = WrappedVar(
            AlgofiVotingEscrowStrings.admin_contract_app_id, GLOBAL_VAR
        )

        # HELPER CLASSES
        self.sending_user = AlgofiVotingEscrowUser(Int(0))
        self.target_user = AlgofiVotingEscrowUser(Int(1))

    # CREATION

    def on_creation(self):
        """Creates the voting escrow contract"""
        dao_address = Txn.accounts[1]
        emergency_dao_address = Txn.accounts[2]

        return Seq(
            # set dao address
            self.dao_address.put(dao_address),
            # set emergency dao address
            self.emergency_dao_address.put(emergency_dao_address),
            self.total_vebank.put(ZERO_AMOUNT),
            self.total_locked.put(ZERO_AMOUNT),
            Approve(),
        )

    # ADMIN

    def on_set_admin_contract_app_id(self):
        """Sets the admin contract app id"""
        admin_contract_app_id = Txn.applications[1]

        return Seq(
            # set new rewards manager app id
            self.admin_contract_app_id.put(admin_contract_app_id),
            Approve(),
        )

    def on_set_gov_token_id(self):
        """Sets the gov token id"""
        return Seq(
            # set gov token id
            self.asset_id.put(Txn.assets[0]),
            # opt into gov asset
            opt_into_asa(self.asset_id.get()),
            Approve(),
        )

    # OPT IN / CLOSE OUT

    def on_opt_in(self):
        """Called on opt in"""
        return Seq(
            MagicAssert(Gtxn[PREVIOUS_TRANSACTION].sender() == Txn.sender()),
            MagicAssert(
                Gtxn[PREVIOUS_TRANSACTION].application_id()
                == self.admin_contract_app_id.get()
            ),
            MagicAssert(
                Gtxn[PREVIOUS_TRANSACTION].on_completion() == OnComplete.OptIn
            ),
            Approve(),
        )

    def on_close_out(self):
        """Called on close out"""
        return Seq(
            # assert user has no locked bank
            MagicAssert(self.sending_user.amount_locked.get() == ZERO_AMOUNT),
            Approve(),
        )

    # HELPER FUNCTIONS

    def calculate_vebank_amount(self, amount_locked, time_remaining):
        """Calculates the amount of veBANK a user has"""
        return WideRatio([amount_locked, time_remaining], [SECONDS_PER_YEAR])

    def update_boost(self, user: AlgofiVotingEscrowUser):
        """Updates the user's boost"""
        return Seq(
            [
                If(self.total_vebank.get() > ZERO_AMOUNT)
                .Then(
                    user.boost_multiplier.put(
                        WideRatio(
                            [user.amount_vebank.get(), FIXED_12_SCALE_FACTOR],
                            [self.total_vebank.get()],
                        )
                    )
                )
                .Else(user.boost_multiplier.put(ZERO_AMOUNT))
            ]
        )

    def update_vebank_data(self, user: AlgofiVotingEscrowUser):
        """Updates a user's veBANK data"""
        current_time = Global.latest_timestamp()
        time_delta = current_time - user.update_time.get()
        lock_end_time = user.get_lock_end_time()
        lock_time_remaining = lock_end_time - current_time

        on_update = Seq(
            # update user state if time_delta is non zero
            If(time_delta > ZERO_AMOUNT).Then(
                Seq(
                    # decrement user vebank from total
                    decrement(self.total_vebank, user.amount_vebank.get()),
                    # recalculate user vebank amount
                    If(current_time > lock_end_time)
                    .Then(
                        user.amount_vebank.put(ZERO_AMOUNT),
                    )
                    .Else(
                        Seq(
                            user.amount_vebank.put(
                                self.calculate_vebank_amount(
                                    user.amount_locked.get(),
                                    lock_time_remaining,
                                )
                            ),
                            # increment new user vebank to total
                            increment(
                                self.total_vebank, user.amount_vebank.get()
                            ),
                        ),
                    ),
                    # recalculate user boost
                    self.update_boost(user),
                    # update user latest update time
                    user.update_time.put(current_time),
                ),
            ),
        )

        return on_update

    # USER FUNCTIONS

    def on_lock(self):
        """
        Locks user's BANK and grants veBANK (stored in local state)
        veBANK = BANK * (lock_duration / 4 years)
        Locking for 4 years grants maximum weight. Min lock duration is 7 days
        """
        gov_token_txn_index = PREVIOUS_TRANSACTION
        current_timestamp = Global.latest_timestamp()

        lock_duration = Btoi(Txn.application_args[1])
        lock_amount = Gtxn[gov_token_txn_index].asset_amount()
        vebank_amount = self.calculate_vebank_amount(
            lock_amount, lock_duration
        )

        return Seq(
            # verify asset being sent to voting escrow contract
            verify_txn_is_sending_asa_to_contract(
                gov_token_txn_index, self.asset_id.get()
            ),
            # verify user has zero existing locked amount
            MagicAssert(self.sending_user.amount_locked.get() == ZERO_AMOUNT),
            # verify lock duration
            MagicAssert(lock_duration >= MIN_LOCK_TIME_SECONDS),
            MagicAssert(lock_duration <= MAX_LOCK_TIME_SECONDS),
            # verify non zero ve bank amount
            MagicAssert(vebank_amount > ZERO_AMOUNT),
            # set amount locked
            self.sending_user.amount_locked.put(lock_amount),
            # set lock start time
            self.sending_user.lock_start_time.put(current_timestamp),
            # set lock duration
            self.sending_user.lock_duration.put(lock_duration),
            # set vebank amount
            self.sending_user.amount_vebank.put(vebank_amount),
            # set update time
            self.sending_user.update_time.put(current_timestamp),
            # update global totals
            increment(self.total_locked, lock_amount),
            increment(self.total_vebank, vebank_amount),
            # recalculate user boost
            self.update_boost(self.sending_user),
            Approve(),
        )

    def on_update_vebank_data(self):
        """
        Update a user's and global veBANK and lock state
        Anyone can call this for any user
        """

        return Seq(
            [
                # update target user vebank data
                self.update_vebank_data(self.target_user),
                Approve(),
            ]
        )

    def on_claim(self):
        """Sends back user's locked BANK after the lock expires"""
        lock_end_time = self.sending_user.get_lock_end_time()
        current_time = Global.latest_timestamp()

        return Seq(
            # verify amount locked is non zero
            MagicAssert(self.sending_user.amount_locked.get() > ZERO_AMOUNT),
            # verify lock has expired
            MagicAssert(current_time > lock_end_time),
            # return asset to user
            send_asa(
                self.asset_id.get(),
                self.sending_user.amount_locked.get(),
                Txn.sender(),
            ),
            # decrement user amount from total
            decrement(
                self.total_locked, self.sending_user.amount_locked.get()
            ),
            # set user amount locked to zero
            self.sending_user.amount_locked.put(ZERO_AMOUNT),
            # reset user lock start time to
            self.sending_user.lock_start_time.put(UNSET),
            # reset user lock duration
            self.sending_user.lock_duration.put(UNSET),
            # reset user update time
            self.sending_user.update_time.put(UNSET),
            Approve(),
        )

    def on_extend_lock(self):
        """Adds time to existing user lock."""
        extend_duration_seconds = Btoi(Txn.application_args[1])
        current_time = Global.latest_timestamp()
        lock_end_time = self.sending_user.get_lock_end_time()
        duration_remaining = (
            If(current_time < lock_end_time)
            .Then(lock_end_time - current_time)
            .Else(Int(0))
        )
        total_new_duration = duration_remaining + extend_duration_seconds
        current_vebank_balance = self.sending_user.amount_vebank.get()
        locked_amount = self.sending_user.amount_locked.get()

        new_vebank_balance = self.calculate_vebank_amount(
            locked_amount, total_new_duration
        )

        return Seq(
            # verify user has non zero locked amount
            MagicAssert(locked_amount > ZERO_AMOUNT),
            # verify extend duration is non zero
            MagicAssert(extend_duration_seconds > ZERO_AMOUNT),
            # validate new total duration
            MagicAssert(total_new_duration >= MIN_LOCK_TIME_SECONDS),
            MagicAssert(total_new_duration <= MAX_LOCK_TIME_SECONDS),
            # update global total vebank
            decrement(self.total_vebank, current_vebank_balance),
            increment(self.total_vebank, new_vebank_balance),
            # set new user vebank amount
            self.sending_user.amount_vebank.put(new_vebank_balance),
            # set new user lock duration
            self.sending_user.lock_duration.put(total_new_duration),
            # set new user lock start time
            self.sending_user.lock_start_time.put(current_time),
            # recalculate user boost
            self.update_boost(self.sending_user),
            Approve(),
        )

    def on_increase_lock_amount(self):
        """Increases the amount of BANK locked, without changing lock duration"""
        gov_token_txn_index = PREVIOUS_TRANSACTION
        current_time = Global.latest_timestamp()
        lock_end_time = self.sending_user.get_lock_end_time()
        lock_duration = lock_end_time - current_time
        additional_amount_to_lock = Gtxn[gov_token_txn_index].asset_amount()
        existing_amount_locked = self.sending_user.amount_locked.get()
        new_vebank = self.calculate_vebank_amount(
            existing_amount_locked + additional_amount_to_lock, lock_duration
        )

        return Seq(
            # verify previous transaction is payment to this contract
            verify_txn_is_sending_asa_to_contract(
                gov_token_txn_index, self.asset_id.get()
            ),
            # verify the users current amount locked is non zero
            MagicAssert(self.sending_user.amount_locked.get() > ZERO_AMOUNT),
            # verify remaining lock duration is greater than minimum
            MagicAssert(lock_duration >= MIN_LOCK_TIME_SECONDS),
            # verify additional amount to lock is non zero
            MagicAssert(additional_amount_to_lock > ZERO_AMOUNT),
            # verify additional vebank amount is non zero
            MagicAssert(new_vebank > self.sending_user.amount_vebank.get()),
            # increment total locked
            increment(self.total_locked, additional_amount_to_lock),
            # increment user locked
            increment(
                self.sending_user.amount_locked, additional_amount_to_lock
            ),
            decrement(
                self.total_vebank, self.sending_user.amount_vebank.get()
            ),
            # increment total vebank
            increment(self.total_vebank, new_vebank),
            # increment user vebank
            self.sending_user.amount_vebank.put(new_vebank),
            # recalculate user boost
            self.update_boost(self.sending_user),
            Approve(),
        )

    def approval_program(self):
        """Voting escrow approval program."""
        # sender checks
        sender_is_dao = Or(
            Txn.sender() == self.dao_address.get(),
            Txn.sender() == self.emergency_dao_address.get(),
        )
        # check on complete
        is_no_op = Txn.on_completion() == OnComplete.NoOp
        is_opt_in = Txn.on_completion() == OnComplete.OptIn
        is_close_out = Txn.on_completion() == OnComplete.CloseOut
        # on call method
        on_call_method = Txn.application_args[0]

        return Cond(
            [Txn.application_id() == Int(0), self.on_creation()],
            [Txn.on_completion() == OnComplete.DeleteApplication, Reject()],
            [is_opt_in, self.on_opt_in()],
            [is_close_out, self.on_close_out()],
            # admin functions
            [
                sender_is_dao,
                Cond(
                    [
                        is_no_op,
                        Cond(
                            [
                                on_call_method
                                == Bytes(
                                    AlgofiVotingEscrowStrings.set_gov_token_id
                                ),
                                self.on_set_gov_token_id(),
                            ],
                            [
                                on_call_method
                                == Bytes(
                                    AlgofiVotingEscrowStrings.set_admin_contract_app_id
                                ),
                                self.on_set_admin_contract_app_id(),
                            ],
                        ),
                    ]
                ),
            ],
            # user functions
            [
                is_no_op,
                Cond(
                    # target user
                    [
                        on_call_method
                        == Bytes(AlgofiVotingEscrowStrings.update_vebank_data),
                        self.on_update_vebank_data(),
                    ],
                    # lock (does not require vebank update)
                    [
                        on_call_method
                        == Bytes(AlgofiVotingEscrowStrings.lock),
                        self.on_lock(),
                    ],
                    # user
                    [
                        TRUE,
                        Seq(
                            self.update_vebank_data(self.sending_user),
                            Cond(
                                [
                                    on_call_method
                                    == Bytes(
                                        AlgofiVotingEscrowStrings.extend_lock
                                    ),
                                    self.on_extend_lock(),
                                ],
                                [
                                    on_call_method
                                    == Bytes(
                                        AlgofiVotingEscrowStrings.increase_lock_amount
                                    ),
                                    self.on_increase_lock_amount(),
                                ],
                                [
                                    on_call_method
                                    == Bytes(AlgofiVotingEscrowStrings.claim),
                                    self.on_claim(),
                                ],
                            ),
                        ),
                    ],
                ),
            ],
        )

    def clear_state_program(self):
        """Clear state program for the voting escrow contract."""
        return Seq(
            # decrement user vebank amount from total
            decrement(
                self.total_vebank, self.sending_user.amount_vebank.get()
            ),
            # decrement user locked amount from total
            decrement(
                self.total_locked, self.sending_user.amount_locked.get()
            ),
            Approve(),
        )
