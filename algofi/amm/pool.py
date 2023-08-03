"""Defines the AlgoFi AMM Pool contract logic."""

from pyteal import *

from algofi.amm.constants import *
from algofi.amm.contract_strings import *
from algofi.amm.subroutines import *
from algofi.utils.wrapped_var import *


# POOL HELPERS
def opt_into_asset(asset_id):
    """Opt into an asset."""
    return If(asset_id > Int(1), opt_in_to_asa(asset_id))


def increment(var, amount):
    """Increment a variable by a given amount."""
    return var.put(var.get() + amount)


def decrement(var, amount):
    """Decrement a variable by a given amount."""
    return var.put(var.get() - amount)


def verify_txn_is_named_application_call(idx, name):
    """
    Verifies that the transaction at the given index is:
        - a NoOp application call
        - to this application
        - with the provided value at arg[0]
    """
    return Seq(
        [
            Assert(Gtxn[idx].on_completion() == OnComplete.NoOp),
            Assert(Gtxn[idx].type_enum() == TxnType.ApplicationCall),
            Assert(
                Gtxn[idx].application_id() == Global.current_application_id()
            ),
            Assert(Gtxn[idx].application_args[0] == Bytes(name)),
        ]
    )


def verify_txn_is_sending_algos_to_pool(idx):
    """
    Verifies that the transaction at the given index is:
        - a Payment transaction
        - to this application's escrow address
        - of non-zero amount
    """
    return Seq(
        [
            Assert(Gtxn[idx].type_enum() == TxnType.Payment),
            Assert(
                Gtxn[idx].receiver() == Global.current_application_address()
            ),
            Assert(Gtxn[idx].amount() > Int(0)),
        ]
    )


def verify_txn_is_sending_asa_to_pool(idx, asset_id):
    """
    Verifies that the transaction at the given index is:
        - an AssetTransfer transaction
        - to this application's escrow address
        - of the provided asset_id
        - of non-zero amount
    """
    return Seq(
        [
            Assert(Gtxn[idx].type_enum() == TxnType.AssetTransfer),
            Assert(Gtxn[idx].xfer_asset() == asset_id),
            Assert(
                Gtxn[idx].asset_receiver()
                == Global.current_application_address()
            ),
            Assert(Gtxn[idx].asset_amount() > Int(0)),
        ]
    )


class AlgofiAMMPool:
    """Contract class for the AlgoFi AMM Pool."""

    def __init__(
        self, manager_app_id, swap_fee_pct_scaled=DEFAULT_SWAP_FEE_PCT_SCALED
    ):
        # CONSTANTS
        self.manager_app_id = Int(manager_app_id)
        # swap fee scaled by 1000000
        self.swap_fee_pct_scaled = swap_fee_pct_scaled

        # SCRATCH VARS
        self.lp_issued_store = ScratchVar(TealType.uint64, 0)
        self.swap_input_amount_store = ScratchVar(TealType.uint64, 1)
        self.swap_output_amount_store = ScratchVar(TealType.uint64, 2)
        self.swap_fee_store = ScratchVar(TealType.uint64, 3)
        self.pool_asset1_amount_store = ScratchVar(TealType.uint64, 4)
        self.pool_asset2_amount_store = ScratchVar(TealType.uint64, 5)
        self.burn_asset1_amount_store = ScratchVar(TealType.uint64, 6)
        self.burn_asset2_amount_store = ScratchVar(TealType.uint64, 7)
        self.swap_input_is_asset1_store = ScratchVar(TealType.uint64, 8)
        self.swap_input_amount_store = ScratchVar(TealType.uint64, 9)
        self.swap_input_amount_less_fees_store = ScratchVar(
            TealType.uint64, 10
        )
        self.exact_amount_to_swap_for_store = ScratchVar(TealType.uint64, 11)
        self.required_swap_input_amount_store = ScratchVar(TealType.uint64, 12)
        self.required_swap_input_amount_plus_fees_store = ScratchVar(
            TealType.uint64, 13
        )
        self.residual_amount_store = ScratchVar(TealType.uint64, 14)
        self.pool_asset_ratio_store = ScratchVar(TealType.uint64, 15)
        self.incoming_asset_ratio_store = ScratchVar(TealType.uint64, 16)
        self.adjusted_pool_asset1_amount_store = ScratchVar(
            TealType.uint64, 17
        )
        self.adjusted_pool_asset2_amount_store = ScratchVar(
            TealType.uint64, 18
        )
        self.pool_asset1_residual_store = ScratchVar(TealType.uint64, 19)
        self.pool_asset2_residual_store = ScratchVar(TealType.uint64, 20)
        self.ratio_slippage_store = ScratchVar(TealType.uint64, 21)
        self.flash_loan_fee_store = ScratchVar(TealType.uint64, 22)
        self.fee_to_reserve_store = ScratchVar(TealType.uint64, 23)
        self.time_delta_store = ScratchVar(TealType.uint64, 24)
        self.asset1_to_asset2_price_store = ScratchVar(TealType.uint64, 25)
        self.asset2_to_asset1_price_store = ScratchVar(TealType.uint64, 26)
        self.lp_asset_name_store = ScratchVar(TealType.bytes, 27)
        self.lp_issued_from_asset1_store = ScratchVar(TealType.uint64, 28)
        self.lp_issued_from_asset2_store = ScratchVar(TealType.uint64, 29)

        # GLOBAL VARS
        self.lp_id = WrappedVar(AlgofiAMMPoolStrings.lp_id, GLOBAL_VAR)
        self.admin = WrappedVar(AlgofiAMMPoolStrings.admin, GLOBAL_VAR)
        self.initialized = WrappedVar(
            AlgofiAMMPoolStrings.initialized, GLOBAL_VAR
        )
        self.asset1_id = WrappedVar(AlgofiAMMPoolStrings.asset1_id, GLOBAL_VAR)
        self.asset2_id = WrappedVar(AlgofiAMMPoolStrings.asset2_id, GLOBAL_VAR)
        self.balance_1 = WrappedVar(AlgofiAMMPoolStrings.balance_1, GLOBAL_VAR)
        self.balance_2 = WrappedVar(AlgofiAMMPoolStrings.balance_2, GLOBAL_VAR)
        self.lp_circulation = WrappedVar(
            AlgofiAMMPoolStrings.lp_circulation, GLOBAL_VAR
        )
        self.reserve_factor = WrappedVar(
            AlgofiAMMPoolStrings.reserve_factor, GLOBAL_VAR
        )
        self.asset1_reserve = WrappedVar(
            AlgofiAMMPoolStrings.asset1_reserve, GLOBAL_VAR
        )
        self.asset2_reserve = WrappedVar(
            AlgofiAMMPoolStrings.asset2_reserve, GLOBAL_VAR
        )
        self.cumsum_time_weighted_asset1_to_asset2_price = WrappedVar(
            AlgofiAMMPoolStrings.cumsum_time_weighted_asset1_to_asset2_price,
            GLOBAL_VAR,
        )
        self.cumsum_time_weighted_asset2_to_asset1_price = WrappedVar(
            AlgofiAMMPoolStrings.cumsum_time_weighted_asset2_to_asset1_price,
            GLOBAL_VAR,
        )
        self.latest_time = WrappedVar(
            AlgofiAMMPoolStrings.latest_time, GLOBAL_VAR
        )
        self.cumsum_volume_asset1 = WrappedVar(
            AlgofiAMMPoolStrings.cumsum_volume_asset1, GLOBAL_VAR
        )
        self.cumsum_volume_asset2 = WrappedVar(
            AlgofiAMMPoolStrings.cumsum_volume_asset2, GLOBAL_VAR
        )
        self.cumsum_volume_weighted_asset1_to_asset2_price = WrappedVar(
            AlgofiAMMPoolStrings.cumsum_volume_weighted_asset1_to_asset2_price,
            GLOBAL_VAR,
        )
        self.cumsum_volume_weighted_asset2_to_asset1_price = WrappedVar(
            AlgofiAMMPoolStrings.cumsum_volume_weighted_asset2_to_asset1_price,
            GLOBAL_VAR,
        )
        self.cumsum_fees_asset1 = WrappedVar(
            AlgofiAMMPoolStrings.cumsum_fees_asset1, GLOBAL_VAR
        )
        self.cumsum_fees_asset2 = WrappedVar(
            AlgofiAMMPoolStrings.cumsum_fees_asset2, GLOBAL_VAR
        )
        self.flash_loan_fee = WrappedVar(
            AlgofiAMMPoolStrings.flash_loan_fee, GLOBAL_VAR
        )
        self.max_flash_loan_ratio = WrappedVar(
            AlgofiAMMPoolStrings.max_flash_loan_ratio, GLOBAL_VAR
        )
        self.validator_index = WrappedVar(
            AlgofiAMMPoolStrings.validator_index, GLOBAL_VAR
        )
        self.manager_app_id_var = WrappedVar(
            AlgofiAMMPoolStrings.manager_app_id_var, GLOBAL_VAR
        )
        self.swap_fee_pct_scaled_var = WrappedVar(
            AlgofiAMMPoolStrings.swap_fee_pct_scaled_var, GLOBAL_VAR
        )

        self.swap_fee_update_time = WrappedVar(
            AlgofiAMMPoolStrings.swap_fee_update_time, GLOBAL_VAR
        )
        self.next_swap_fee_pct_scaled_var = WrappedVar(
            AlgofiAMMPoolStrings.next_swap_fee_pct_scaled, GLOBAL_VAR
        )
        self.param_update_delay = WrappedVar(
            AlgofiAMMPoolStrings.param_update_delay, GLOBAL_VAR
        )

        # GLOBAL EX VARS
        self.manager_admin = WrappedVar(
            AlgofiAMMManagerStrings.admin, GLOBAL_EX_VAR, self.manager_app_id
        ).get()
        self.manager_reserve_factor = WrappedVar(
            AlgofiAMMManagerStrings.reserve_factor,
            GLOBAL_EX_VAR,
            self.manager_app_id,
        ).get()

        self.manager_flash_loan_fee = WrappedVar(
            AlgofiAMMManagerStrings.flash_loan_fee,
            GLOBAL_EX_VAR,
            self.manager_app_id,
        ).get()
        self.manager_max_flash_loan_ratio = WrappedVar(
            AlgofiAMMManagerStrings.max_flash_loan_ratio,
            GLOBAL_EX_VAR,
            self.manager_app_id,
        ).get()
        self.lp_asset_prefix = Bytes("AF-POOL-")

    def convert_asset1_to_lp(self, asset1_amount):
        """Uses a wide ratio to convert asset 1 to an LP amount."""
        return WideRatio(
            [asset1_amount, self.lp_circulation.get()], [self.balance_1.get()]
        )

    def convert_asset2_to_lp(self, asset2_amount):
        """Uses a wide ratio to convert asset 2 to an LP amount."""
        return WideRatio(
            [asset2_amount, self.lp_circulation.get()], [self.balance_2.get()]
        )

    def convert_lp_to_asset1(self, amount_lp):
        """Uses a wide ratio to convert an LP amount to asset1."""
        return WideRatio(
            [amount_lp, self.balance_1.get()], [self.lp_circulation.get()]
        )

    def convert_lp_to_asset2(self, amount_lp):
        """Uses a wide ratio to convert an LP amount to asset2."""
        return WideRatio(
            [amount_lp, self.balance_2.get()], [self.lp_circulation.get()]
        )

    def swap_exact_asset1_for(self, asset1_amount):
        """Swaps an exact amount of asset 1 for a variable amount of asset 2."""
        return WideRatio(
            [self.balance_2.get(), asset1_amount],
            [self.balance_1.get() + asset1_amount],
        )

    def swap_exact_asset2_for(self, asset2_amount):
        """Swap an exact amount of asset 2 for a variable amount of asset 1."""
        return WideRatio(
            [self.balance_1.get(), asset2_amount],
            [self.balance_2.get() + asset2_amount],
        )

    def swap_for_exact_asset1_amount(self, asset1_amount):
        """Swaps a variable amount of asset 2 for an exact amount of asset 1."""
        return WideRatio(
            [self.balance_2.get(), asset1_amount],
            [self.balance_1.get() - asset1_amount],
        ) + Int(1)

    def swap_for_exact_asset2_amount(self, asset2_amount):
        """Swaps a variable amount of asset 1 for an exact amount of asset 2."""
        return WideRatio(
            [self.balance_1.get(), asset2_amount],
            [self.balance_2.get() - asset2_amount],
        ) + Int(1)

    def send_asset1(self, amount):
        """Creates a transaction to send asset 1 to the caller."""
        return If(
            self.asset1_id.get() == Int(1),
            send_algo(amount),
            send_asa(self.asset1_id.get(), amount),
        )

    def send_asset2(self, amount):
        """Creates a transaction to send asset 2 to the caller."""
        return send_asa(self.asset2_id.get(), amount)

    def send_lp(self, amount):
        """Creates a transaction to send LP tokens to the caller."""
        return send_asa(self.lp_id.get(), amount)

    def update_reserve_factor(self):
        """Updates the reserve factor from the manager."""
        return Seq(
            [
                self.manager_reserve_factor,
                Assert(self.manager_reserve_factor.hasValue()),
                Assert(
                    self.manager_reserve_factor.value() <= FIXED_6_SCALE_FACTOR
                ),
                self.reserve_factor.put(self.manager_reserve_factor.value()),
            ]
        )

    def update_flash_loan_fee(self):
        """Updates the flash loan fee from the manager."""
        return Seq(
            [
                self.manager_flash_loan_fee,
                Assert(self.manager_flash_loan_fee.hasValue()),
                Assert(
                    self.manager_flash_loan_fee.value() <= FIXED_6_SCALE_FACTOR
                ),
                self.flash_loan_fee.put(self.manager_flash_loan_fee.value()),
            ]
        )

    def update_max_flash_loan_ratio(self):
        """Updates the max flash loan ratio from the manager."""
        return Seq(
            [
                self.manager_max_flash_loan_ratio,
                Assert(self.manager_max_flash_loan_ratio.hasValue()),
                Assert(
                    self.manager_max_flash_loan_ratio.value()
                    <= FIXED_6_SCALE_FACTOR
                ),
                self.max_flash_loan_ratio.put(
                    self.manager_max_flash_loan_ratio.value()
                ),
            ]
        )

    def update_reserves(self, fee_is_asset1, amount):
        """
        Updates the reserves and cumsum fees.

        Move the provided amount from the balance of the provided asset to the
        reserves and updates the cumsum fees appropriately.
        """
        fee_to_reserve = WideRatio(
            [amount, self.reserve_factor.get()], [FIXED_6_SCALE_FACTOR]
        )
        fees_less_reserve = amount - self.fee_to_reserve_store.load()
        return Seq(
            [
                self.fee_to_reserve_store.store(fee_to_reserve),
                If(
                    fee_is_asset1,
                    Seq(
                        [
                            decrement(
                                self.balance_1,
                                self.fee_to_reserve_store.load(),
                            ),
                            increment(
                                self.asset1_reserve,
                                self.fee_to_reserve_store.load(),
                            ),
                            # update cumsum fees
                            self.cumsum_fees_asset1.put(
                                calculate_integer_wrapped_value(
                                    self.cumsum_fees_asset1.get(),
                                    fees_less_reserve,
                                )
                            ),
                        ]
                    ),
                    Seq(
                        [
                            decrement(
                                self.balance_2,
                                self.fee_to_reserve_store.load(),
                            ),
                            increment(
                                self.asset2_reserve,
                                self.fee_to_reserve_store.load(),
                            ),
                            # update cumsum fees
                            self.cumsum_fees_asset2.put(
                                calculate_integer_wrapped_value(
                                    self.cumsum_fees_asset2.get(),
                                    fees_less_reserve,
                                )
                            ),
                        ]
                    ),
                ),
            ]
        )

    def validate_asset_ratio(self):
        """
        Validates that the asset ratio is within the bounds.
            - assert that the balance_1 / balance_2 ratio is within 1e9:1
            - no transaction which moves the ratio out of the range is allowed
        """
        return Seq(
            [
                Assert(self.balance_1.get() >= MIN_POOL_BALANCE),
                Assert(self.balance_2.get() >= MIN_POOL_BALANCE),
                Assert(
                    self.balance_1.get() / self.balance_2.get()
                    < MAX_ASSET_RATIO
                ),
                Assert(
                    self.balance_2.get() / self.balance_1.get()
                    < MAX_ASSET_RATIO
                ),
            ]
        )

    def on_creation(self):
        """Called at contract creation time to set state."""
        # ADD ASSET CONFIG
        asset1_id = Btoi(Txn.application_args[0])
        asset2_id = Btoi(Txn.application_args[1])
        validator_index = Btoi(Txn.application_args[2])
        asset_ids_not_zero = And(asset1_id != Int(0), asset2_id != Int(0))
        asset_ids_increasing_and_different = asset1_id < asset2_id

        # CHECK THE SCHEMA
        global_bytes_sufficient = (
            Txn.global_num_byte_slices() >= POOL_GLOBAL_NUM_BYTES
        )
        global_uints_sufficient = (
            Txn.global_num_uints() >= POOL_GLOBAL_NUM_UINTS
        )

        return Seq(
            [
                # assert schema
                Assert(global_bytes_sufficient),
                Assert(global_uints_sufficient),
                # set admin to the same admin as the manager
                self.manager_admin,
                Assert(self.manager_admin.hasValue()),
                self.admin.put(self.manager_admin.value()),
                # verify and set assets
                Assert(asset_ids_not_zero),
                Assert(asset_ids_increasing_and_different),
                self.asset1_id.put(asset1_id),
                self.asset2_id.put(asset2_id),
                # save down validator index
                self.validator_index.put(validator_index),
                # default uninitialized
                self.initialized.put(FALSE),
                Int(1),
            ]
        )

    def on_initialize_pool(self):
        """A method to initialize the pool."""

        is_not_initialized = Not(self.initialized.get())
        is_noop_txn = Txn.on_completion() == OnComplete.NoOp
        is_appl_call = Txn.type_enum() == TxnType.ApplicationCall

        return Seq(
            [
                # must be noop appl call
                Assert(is_noop_txn),
                Assert(is_appl_call),
                # must be uninitialized
                Assert(is_not_initialized),
                # opt into assets and create asa
                opt_into_asset(self.asset1_id.get()),
                opt_into_asset(self.asset2_id.get()),
                create_lp_asset(
                    self.lp_id,
                    self.lp_asset_prefix,
                    self.asset1_id.get(),
                    self.asset2_id.get(),
                    self.lp_asset_name_store,
                ),
                # load values from manager
                self.update_reserve_factor(),
                self.update_flash_loan_fee(),
                self.update_max_flash_loan_ratio(),
                # initialize param update params
                self.param_update_delay.put(DEFAULT_PARAM_UPDATE_DELAY),
                # set latest tine to now
                self.latest_time.put(Global.latest_timestamp()),
                # initialize all other global state variables to ensure they have not been tampered with
                self.balance_1.put(UNSET_INT),
                self.balance_2.put(UNSET_INT),
                self.lp_circulation.put(UNSET_INT),
                self.asset1_reserve.put(UNSET_INT),
                self.asset2_reserve.put(UNSET_INT),
                self.cumsum_time_weighted_asset1_to_asset2_price.put(
                    UNSET_INT
                ),
                self.cumsum_time_weighted_asset2_to_asset1_price.put(
                    UNSET_INT
                ),
                self.cumsum_volume_asset1.put(UNSET_INT),
                self.cumsum_volume_asset2.put(UNSET_INT),
                self.cumsum_volume_weighted_asset1_to_asset2_price.put(
                    UNSET_INT
                ),
                self.cumsum_volume_weighted_asset2_to_asset1_price.put(
                    UNSET_INT
                ),
                self.cumsum_fees_asset1.put(UNSET_INT),
                self.cumsum_fees_asset2.put(UNSET_INT),
                # set registration variables
                self.manager_app_id_var.put(self.manager_app_id),
                self.swap_fee_pct_scaled_var.put(self.swap_fee_pct_scaled),
                # set initialized
                self.initialized.put(TRUE),
                Int(1),
            ]
        )

    # ADMIN FUNCTIONS

    def on_update_swap_fee(self):
        """A method to update the pool swap fee."""

        sender_is_admin = Txn.sender() == self.admin.get()
        return Seq(
            Assert(sender_is_admin),
            Assert(self.swap_fee_update_time.get() > Int(0)),
            Assert(
                Global.latest_timestamp() > self.swap_fee_update_time.get()
            ),
            self.swap_fee_pct_scaled_var.put(
                self.next_swap_fee_pct_scaled_var.get()
            ),
            Int(1),
        )

    def on_schedule_swap_fee_update(self):
        """A method to scedule a swap fee update."""

        update_time = Btoi(Txn.application_args[1])
        MAX_FEE = FIXED_6_SCALE_FACTOR
        new_fee = Btoi(Txn.application_args[2])
        sender_is_admin = Txn.sender() == self.admin.get()

        return Seq(
            [
                Assert(sender_is_admin),
                # check for update delay
                Assert(
                    update_time
                    >= Global.latest_timestamp()
                    + self.param_update_delay.get()
                ),
                Assert(new_fee > Int(0)),
                Assert(new_fee < MAX_FEE),
                # set param_update_time after which these new parameters may go into effect
                self.swap_fee_update_time.put(update_time),
                self.next_swap_fee_pct_scaled_var.put(new_fee),
                Int(1),
            ]
        )

    def on_increase_param_delay(self):
        """A method to increase the parameter update delay."""

        new_param_update_delay = Btoi(Txn.application_args[1])
        sender_is_admin = Txn.sender() == self.admin.get()
        return Seq(
            Assert(sender_is_admin),
            Assert(new_param_update_delay > self.param_update_delay.get()),
            self.param_update_delay.put(new_param_update_delay),
            Int(1),
        )

    def on_remove_reserves(self):
        """A method to remove reserves from the pool."""

        sender_is_admin = Txn.sender() == self.admin.get()

        return Seq(
            [
                Assert(sender_is_admin),
                # send reserves to admin
                self.send_asset1(self.asset1_reserve.get()),
                self.send_asset2(self.asset2_reserve.get()),
                # reset reserves to 0
                self.asset1_reserve.put(Int(0)),
                self.asset2_reserve.put(Int(0)),
                Int(1),
            ]
        )

    # HELPER FUNCTIONS

    def calculate_lp_issuance(self, pool_is_empty):
        """
        A helper method to calculate the LP issuance.
            - First time seeding uses sqrt(a1*a2) as the initial lp issuance
        """
        return If(
            pool_is_empty,
            Seq(
                [
                    If(
                        MAX_INT_U64
                        / self.adjusted_pool_asset1_amount_store.load()
                        > self.adjusted_pool_asset2_amount_store.load(),
                        self.lp_issued_store.store(
                            Sqrt(
                                self.adjusted_pool_asset1_amount_store.load()
                                * self.adjusted_pool_asset2_amount_store.load()
                            )
                        ),
                        self.lp_issued_store.store(
                            Sqrt(self.adjusted_pool_asset1_amount_store.load())
                            * Sqrt(
                                self.adjusted_pool_asset2_amount_store.load()
                            )
                        ),
                    )
                ]
            ),
            Seq(
                [
                    self.lp_issued_from_asset1_store.store(
                        self.convert_asset1_to_lp(
                            self.adjusted_pool_asset1_amount_store.load()
                        )
                    ),
                    self.lp_issued_from_asset2_store.store(
                        self.convert_asset2_to_lp(
                            self.adjusted_pool_asset2_amount_store.load()
                        )
                    ),
                    If(
                        self.lp_issued_from_asset1_store.load()
                        > self.lp_issued_from_asset2_store.load(),
                        self.lp_issued_store.store(
                            self.lp_issued_from_asset2_store.load()
                        ),
                        self.lp_issued_store.store(
                            self.lp_issued_from_asset1_store.load()
                        ),
                    ),
                ]
            ),
        )

    def adjust_pool_input_amounts(self, pool_is_empty):
        """Helper method to adjust the pool input amounts based on the pool ratio."""
        pool_slippage_pct_scaled = Btoi(
            Txn.application_args[1]
        )  # scaled by 1000000
        pool_asset_ratio = WideRatio(
            [self.balance_1.get(), FIXED_9_SCALE_FACTOR],
            [self.balance_2.get()],
        )
        incoming_asset_ratio = WideRatio(
            [self.pool_asset1_amount_store.load(), FIXED_9_SCALE_FACTOR],
            [self.pool_asset2_amount_store.load()],
        )
        ratio_slippage = WideRatio(
            [self.pool_asset_ratio_store.load(), FIXED_6_SCALE_FACTOR],
            [self.incoming_asset_ratio_store.load()],
        )
        ratio_slippage_within_tolerance = And(
            self.ratio_slippage_store.load()
            > FIXED_6_SCALE_FACTOR - pool_slippage_pct_scaled,
            self.ratio_slippage_store.load()
            < FIXED_6_SCALE_FACTOR + pool_slippage_pct_scaled,
        )

        # maximum asset1 amount to pool given the full amount of asset2 provided
        adjusted_pool_asset1_amount = WideRatio(
            [self.pool_asset2_amount_store.load(), self.balance_1.get()],
            [self.balance_2.get()],
        ) + Int(1)
        # maximum asset2 amount to pool given the full amount of asset1 provided
        adjusted_pool_asset2_amount = WideRatio(
            [self.pool_asset1_amount_store.load(), self.balance_2.get()],
            [self.balance_1.get()],
        ) + Int(1)

        return If(
            pool_is_empty,
            # empty pools will initialize at the provided ratio
            Seq(
                [
                    self.adjusted_pool_asset1_amount_store.store(
                        self.pool_asset1_amount_store.load()
                    ),
                    self.adjusted_pool_asset2_amount_store.store(
                        self.pool_asset2_amount_store.load()
                    ),
                ]
            ),
            # non-empty pools will pool at the current asset ratio, any remainder will be returned to the sender in the redeem transactions
            Seq(
                [
                    self.pool_asset_ratio_store.store(pool_asset_ratio),
                    self.incoming_asset_ratio_store.store(
                        incoming_asset_ratio
                    ),
                    self.ratio_slippage_store.store(ratio_slippage),
                    Assert(ratio_slippage_within_tolerance),
                    Cond(
                        [
                            self.incoming_asset_ratio_store.load()
                            > self.pool_asset_ratio_store.load(),  # too much asset1
                            Seq(
                                [
                                    self.adjusted_pool_asset1_amount_store.store(
                                        adjusted_pool_asset1_amount
                                    ),
                                    self.adjusted_pool_asset2_amount_store.store(
                                        self.pool_asset2_amount_store.load()
                                    ),
                                    self.pool_asset1_residual_store.store(
                                        self.pool_asset1_amount_store.load()
                                        - self.adjusted_pool_asset1_amount_store.load()
                                    ),
                                    self.pool_asset2_residual_store.store(
                                        Int(0)
                                    ),
                                ]
                            ),
                        ],
                        [
                            self.incoming_asset_ratio_store.load()
                            < self.pool_asset_ratio_store.load(),  # too much asset2
                            Seq(
                                [
                                    self.adjusted_pool_asset1_amount_store.store(
                                        self.pool_asset1_amount_store.load()
                                    ),
                                    self.adjusted_pool_asset2_amount_store.store(
                                        adjusted_pool_asset2_amount
                                    ),
                                    self.pool_asset1_residual_store.store(
                                        Int(0)
                                    ),
                                    self.pool_asset2_residual_store.store(
                                        self.pool_asset2_amount_store.load()
                                        - self.adjusted_pool_asset2_amount_store.load()
                                    ),
                                ]
                            ),
                        ],
                        [
                            self.incoming_asset_ratio_store.load()
                            == self.pool_asset_ratio_store.load(),  # sent asset ratio matches current pool ratio precisely
                            Seq(
                                [
                                    self.adjusted_pool_asset1_amount_store.store(
                                        self.pool_asset1_amount_store.load()
                                    ),
                                    self.adjusted_pool_asset2_amount_store.store(
                                        self.pool_asset2_amount_store.load()
                                    ),
                                    self.pool_asset1_residual_store.store(
                                        Int(0)
                                    ),
                                    self.pool_asset2_residual_store.store(
                                        Int(0)
                                    ),
                                ]
                            ),
                        ],
                    ),
                ]
            ),
        )

    """
    Txn parameters
    @param 0: string in bytes reading "p" passed to pool
    """

    def on_pool(self):
        """
        A method to pool assets into the pool.
            - Updates the reserves
            - Updates the pool balances
            - Updates the LP issuance
            - Sends LP tokens to the caller
        """

        def validate_asset1_payment_txn():
            asset1_is_algo = self.asset1_id.get() == Int(1)

            return Seq(
                [
                    If(
                        asset1_is_algo,
                        Seq(
                            [
                                verify_txn_is_sending_algos_to_pool(
                                    POOL__ASSET1_IN_IDX
                                ),
                                # save down asset amount
                                self.pool_asset1_amount_store.store(
                                    Gtxn[POOL__ASSET1_IN_IDX].amount()
                                ),
                            ]
                        ),
                        Seq(
                            [
                                verify_txn_is_sending_asa_to_pool(
                                    POOL__ASSET1_IN_IDX, self.asset1_id.get()
                                ),
                                # save down asset amount
                                self.pool_asset1_amount_store.store(
                                    Gtxn[POOL__ASSET1_IN_IDX].asset_amount()
                                ),
                            ]
                        ),
                    )
                ]
            )

        def validate_asset2_payment_txn():
            """Validate asset2 payment transaction."""
            return Seq(
                [
                    verify_txn_is_sending_asa_to_pool(
                        POOL__ASSET2_IN_IDX, self.asset2_id.get()
                    ),
                    # save down asset amount
                    self.pool_asset2_amount_store.store(
                        Gtxn[POOL__ASSET2_IN_IDX].asset_amount()
                    ),
                ]
            )

        def validate_pool_txn():
            """Validate pool transaction."""
            return Seq(
                [
                    Assert(Txn.on_completion() == OnComplete.NoOp),
                    Assert(Txn.type_enum() == TxnType.ApplicationCall),
                ]
            )

        def validate_redeem_asset1_residual_txn():
            """Validate redeem asset1 residual transaction."""
            return verify_txn_is_named_application_call(
                POOL__REDEEM_POOL_ASSET1_RESIDUAL_IDX,
                AlgofiAMMPoolStrings.redeem_pool_asset1_residual,
            )

        def validate_redeem_asset2_residual_txn():
            """Validate redeem asset2 residual transaction."""
            return verify_txn_is_named_application_call(
                POOL__REDEEM_POOL_ASSET2_RESIDUAL_IDX,
                AlgofiAMMPoolStrings.redeem_pool_asset2_residual,
            )

        def validate_lp_issuance_nonzero():
            """Validate lp issuance is nonzero."""
            return Seq([Assert(self.lp_issued_store.load() > Int(0))])

        def update_balances():
            """Update balances."""
            return Seq(
                [
                    # initialize latest time if pool is empty
                    If(
                        pool_is_empty,
                        self.latest_time.put(Global.latest_timestamp()),
                    ),
                    increment(
                        self.balance_1,
                        self.adjusted_pool_asset1_amount_store.load(),
                    ),
                    increment(
                        self.balance_2,
                        self.adjusted_pool_asset2_amount_store.load(),
                    ),
                    increment(
                        self.lp_circulation, self.lp_issued_store.load()
                    ),
                ]
            )

        pool_is_empty = (self.balance_1.get() + self.balance_2.get()) == Int(0)
        return Seq(
            [
                # check asset1 payment is valid: txn type, receiver, amount > 0, asset id
                validate_asset1_payment_txn(),
                # check asset2 payment is valid: txn type, receiver, amount > 0, asset id
                validate_asset2_payment_txn(),
                # validate pool txn: application call, noop, args
                validate_pool_txn(),
                # validate redeem asset1 residual txn: application call, noop, args
                validate_redeem_asset1_residual_txn(),
                # validate redeem asset2 residual txn: application call, noop, args
                validate_redeem_asset2_residual_txn(),
                # branch if pool is unseeded with tokens (balance1, balance2 == 0)
                self.adjust_pool_input_amounts(pool_is_empty),
                self.calculate_lp_issuance(pool_is_empty),
                # Assert lp_issued > 0
                validate_lp_issuance_nonzero(),
                update_balances(),
                # send lp tokens to user
                self.send_lp(self.lp_issued_store.load()),
                # validate new ratio is within bounds
                self.validate_asset_ratio(),
                Int(1),
            ]
        )

    def on_burn_asset1_out(self):
        """
        A method to burn LP tokens and receive asset 1.
            - Updates the reserves
            - Updates the pool balances
            - Updates the LP circulation
        """

        # get lp amount to burn
        lp_asset_amount = Gtxn[BURN_ASSET1_OUT__LP_IN_IDX].asset_amount()

        def validate_lp_payment_txn():
            """Validate lp payment transaction."""
            return Seq(
                [
                    verify_txn_is_sending_asa_to_pool(
                        BURN_ASSET1_OUT__LP_IN_IDX, self.lp_id.get()
                    )
                ]
            )

        def validate_burn_asset1_out_txn():
            """Validate burn asset1 out transaction."""
            return Seq(
                [
                    Assert(Txn.on_completion() == OnComplete.NoOp),
                    Assert(Txn.type_enum() == TxnType.ApplicationCall),
                ]
            )

        def validate_burn_asset2_out_txn():
            """Validate burn asset2 out transaction."""
            return verify_txn_is_named_application_call(
                BURN_ASSET1_OUT__BURN_ASSET2_OUT_IDX,
                AlgofiAMMPoolStrings.burn_asset2_out,
            )

        def handle_burn_asset1_out_txn():
            """Calculate asset 1 remit, decrement balance 1, send asset to user."""
            asset1_amount = self.convert_lp_to_asset1(lp_asset_amount)
            burning_remaining_lp_circulation = (
                lp_asset_amount == self.lp_circulation.get()
            )

            return Seq(
                [
                    # if this is the final lp token send full remaining balance
                    If(
                        burning_remaining_lp_circulation,
                        self.burn_asset1_amount_store.store(
                            self.balance_1.get()
                        ),
                        self.burn_asset1_amount_store.store(asset1_amount),
                    ),
                    # do not permit burn which yields 0 asset1
                    Assert(self.burn_asset1_amount_store.load() > Int(0)),
                    Assert(
                        self.burn_asset1_amount_store.load()
                        <= self.balance_1.get()
                    ),
                    # update asset1 balance, lp_circulation will be updated in burn_asset2_out transaction
                    decrement(
                        self.balance_1, self.burn_asset1_amount_store.load()
                    ),
                    self.send_asset1(self.burn_asset1_amount_store.load()),
                ]
            )

        return Seq(
            [
                # check that all transactions are as expected
                validate_lp_payment_txn(),
                validate_burn_asset1_out_txn(),
                validate_burn_asset2_out_txn(),
                # execute burn logic
                handle_burn_asset1_out_txn(),
                Int(1),
            ]
        )

    def on_burn_asset2_out(self):
        """
        A method to burn LP tokens and receive asset 2.
            - Updates the reserves
            - Updates the pool balances
            - Updates the LP circulation
        """

        # get lp amount to burn
        lp_asset_amount = Gtxn[BURN_ASSET2_OUT__LP_IN_IDX].asset_amount()

        def validate_lp_payment_txn():
            """Validate lp payment transaction."""
            return Seq(
                [
                    verify_txn_is_sending_asa_to_pool(
                        BURN_ASSET2_OUT__LP_IN_IDX, self.lp_id.get()
                    )
                ]
            )

        def validate_burn_asset1_out_txn():
            """Validate burn asset1 out transaction."""
            return verify_txn_is_named_application_call(
                BURN_ASSET2_OUT__BURN_ASSET1_OUT_IDX,
                AlgofiAMMPoolStrings.burn_asset1_out,
            )

        def validate_burn_asset2_out_txn():
            """Validate burn asset2 out transaction."""
            return Seq(
                [
                    Assert(Txn.on_completion() == OnComplete.NoOp),
                    Assert(Txn.type_enum() == TxnType.ApplicationCall),
                ]
            )

        # calculate asset 2 remit, decrement balance 2, send asset to user AND decrement LP circulation
        def handle_burn_asset2_out_txn():
            """Handle burn asset2 out transaction."""
            asset2_amount = self.convert_lp_to_asset2(lp_asset_amount)
            burning_remaining_lp_circulation = (
                lp_asset_amount == self.lp_circulation.get()
            )

            return Seq(
                [
                    If(
                        burning_remaining_lp_circulation,
                        self.burn_asset2_amount_store.store(
                            self.balance_2.get()
                        ),
                        self.burn_asset2_amount_store.store(asset2_amount),
                    ),
                    # do not permit burn which yields 0 asset2
                    Assert(self.burn_asset2_amount_store.load() > Int(0)),
                    Assert(
                        self.burn_asset2_amount_store.load()
                        <= self.balance_2.get()
                    ),
                    # update asset2 balance and lp_circulation
                    decrement(
                        self.balance_2, self.burn_asset2_amount_store.load()
                    ),
                    decrement(self.lp_circulation, lp_asset_amount),
                    self.send_asset2(self.burn_asset2_amount_store.load()),
                ]
            )

        return Seq(
            [
                # check that all transactions are as expected
                validate_lp_payment_txn(),
                validate_burn_asset1_out_txn(),
                validate_burn_asset2_out_txn(),
                # execute burn logic
                handle_burn_asset2_out_txn(),
                Int(1),
            ]
        )

    def on_swap(self):
        """
        A method to swap assets.
            - Updates the reserves
            - Updates the pool balances
            - Updates the LP circulation
            - Sends LP tokens to the caller
        """

        def save_latest_cumsum_time_weighted_price():
            """Save latest cumsum time weighted price."""
            current_time = Global.latest_timestamp()
            asset1_to_asset2_price = WideRatio(
                [self.balance_2.get(), FIXED_9_SCALE_FACTOR],
                [self.balance_1.get()],
            )
            asset2_to_asset1_price = WideRatio(
                [self.balance_1.get(), FIXED_9_SCALE_FACTOR],
                [self.balance_2.get()],
            )
            new_cumsum_time_weighted_asset1_to_asset2_price = (
                calculate_integer_wrapped_value(
                    self.cumsum_time_weighted_asset1_to_asset2_price.get(),
                    self.asset1_to_asset2_price_store.load()
                    * self.time_delta_store.load(),
                )
            )
            new_cumsum_time_weighted_asset2_to_asset1_price = (
                calculate_integer_wrapped_value(
                    self.cumsum_time_weighted_asset2_to_asset1_price.get(),
                    self.asset2_to_asset1_price_store.load()
                    * self.time_delta_store.load(),
                )
            )

            return Seq(
                [
                    self.time_delta_store.store(
                        current_time - self.latest_time.get()
                    ),
                    self.latest_time.put(current_time),
                    self.asset1_to_asset2_price_store.store(
                        asset1_to_asset2_price
                    ),
                    self.asset2_to_asset1_price_store.store(
                        asset2_to_asset1_price
                    ),
                    # only update cumsum_time_weighted_prices if it will not result in an overflow
                    If(
                        MAX_INT_U64 / self.asset1_to_asset2_price_store.load()
                        > self.time_delta_store.load(),
                        self.cumsum_time_weighted_asset1_to_asset2_price.put(
                            new_cumsum_time_weighted_asset1_to_asset2_price
                        ),
                    ),
                    If(
                        MAX_INT_U64 / self.asset2_to_asset1_price_store.load()
                        > self.time_delta_store.load(),
                        self.cumsum_time_weighted_asset2_to_asset1_price.put(
                            new_cumsum_time_weighted_asset2_to_asset1_price
                        ),
                    ),
                ]
            )

        is_swap_for_exact = Txn.application_args[0] == Bytes(
            AlgofiAMMPoolStrings.swap_for_exact
        )

        def validate_asset_payment_txn():
            """Validate asset payment transaction."""
            is_payment_txn = (
                Gtxn[SWAP__SWAP_IN_IDX].type_enum() == TxnType.Payment
            )
            asset1_is_algo = self.asset1_id.get() == Int(1)

            asset_transfered = Gtxn[SWAP__SWAP_IN_IDX].xfer_asset()
            is_valid_asset_to_swap = Or(
                asset_transfered == self.asset1_id.get(),
                asset_transfered == self.asset2_id.get(),
            )
            swap_input_is_asset1 = If(
                asset_transfered == self.asset1_id.get(), TRUE, FALSE
            )

            return Seq(
                [
                    If(
                        is_payment_txn,
                        Seq(
                            [
                                # verify that asset1 is algo, if not then algo is not part of this pool
                                Assert(asset1_is_algo),
                                # verify swap in txn is sending algos to this pool
                                verify_txn_is_sending_algos_to_pool(
                                    SWAP__SWAP_IN_IDX
                                ),
                                # save down data
                                self.swap_input_amount_store.store(
                                    Gtxn[SWAP__SWAP_IN_IDX].amount()
                                ),
                                self.swap_input_is_asset1_store.store(TRUE),
                            ]
                        ),
                        Seq(
                            [
                                # verify that the swap in txn asset is either asset1 or asset2
                                Assert(is_valid_asset_to_swap),
                                # verify that the swap in txn is an asset transfer txn with a valid asset to this pool
                                verify_txn_is_sending_asa_to_pool(
                                    SWAP__SWAP_IN_IDX, asset_transfered
                                ),
                                # save down data
                                self.swap_input_amount_store.store(
                                    Gtxn[SWAP__SWAP_IN_IDX].asset_amount()
                                ),
                                self.swap_input_is_asset1_store.store(
                                    swap_input_is_asset1
                                ),
                            ]
                        ),
                    )
                ]
            )

        def validate_swap_txn():
            """Validate swap transaction."""
            return Seq(
                [
                    Assert(Txn.on_completion() == OnComplete.NoOp),
                    Assert(Txn.type_enum() == TxnType.ApplicationCall),
                ]
            )

        def validate_redeem_residual_txn():
            """Validate redeem residual transaction."""
            return If(
                is_swap_for_exact,
                verify_txn_is_named_application_call(
                    SWAP__REDEEM_SWAP_RESIDUAL_IDX,
                    AlgofiAMMPoolStrings.redeem_swap_residual,
                ),
            )

        @Subroutine(TealType.none)
        def save_latest_cumsum_volume(
            asset1_volume: Expr, asset2_volume: Expr
        ) -> Expr:
            """Calculate and save latest cumsum volume."""
            new_cumsum_volume_asset1 = calculate_integer_wrapped_value(
                self.cumsum_volume_asset1.get(), asset1_volume
            )
            new_cumsum_volume_asset2 = calculate_integer_wrapped_value(
                self.cumsum_volume_asset2.get(), asset2_volume
            )
            new_cumsum_volume_weighted_asset1_to_asset2_price = (
                calculate_integer_wrapped_value(
                    self.cumsum_volume_weighted_asset1_to_asset2_price.get(),
                    asset2_volume * self.asset1_to_asset2_price_store.load(),
                )
            )
            new_cumsum_volume_weighted_asset2_to_asset1_price = (
                calculate_integer_wrapped_value(
                    self.cumsum_volume_weighted_asset2_to_asset1_price.get(),
                    asset1_volume * self.asset2_to_asset1_price_store.load(),
                )
            )

            return Seq(
                [
                    self.cumsum_volume_asset1.put(new_cumsum_volume_asset1),
                    self.cumsum_volume_asset2.put(new_cumsum_volume_asset2),
                    # only update cumsum_volume_weighted_prices if it will not result in an overflow
                    If(
                        MAX_INT_U64 / asset2_volume
                        > self.asset1_to_asset2_price_store.load(),
                        self.cumsum_volume_weighted_asset1_to_asset2_price.put(
                            new_cumsum_volume_weighted_asset1_to_asset2_price
                        ),
                    ),
                    If(
                        MAX_INT_U64 / asset1_volume
                        > self.asset2_to_asset1_price_store.load(),
                        self.cumsum_volume_weighted_asset2_to_asset1_price.put(
                            new_cumsum_volume_weighted_asset2_to_asset1_price
                        ),
                    ),
                ]
            )

        def handle_swap_exact_for():
            """Handle swap exact for by calculating the amount of asset1 or asset2 to swap for."""
            min_amount_to_swap_for = Btoi(Txn.application_args[1])

            swap_fee = WideRatio(
                [
                    self.swap_input_amount_store.load(),
                    self.swap_fee_pct_scaled_var.get(),
                ],
                [FIXED_6_SCALE_FACTOR],
            ) + Int(1)

            return Seq(
                [
                    self.swap_fee_store.store(swap_fee),
                    self.swap_input_amount_less_fees_store.store(
                        self.swap_input_amount_store.load()
                        - self.swap_fee_store.load()
                    ),
                    Assert(
                        self.swap_input_amount_less_fees_store.load() > Int(0)
                    ),
                    If(
                        self.swap_input_is_asset1_store.load(),
                        Seq(
                            [
                                self.swap_output_amount_store.store(
                                    self.swap_exact_asset1_for(
                                        self.swap_input_amount_less_fees_store.load()
                                    )
                                ),
                                increment(
                                    self.balance_1,
                                    self.swap_input_amount_store.load(),
                                ),
                                decrement(
                                    self.balance_2,
                                    self.swap_output_amount_store.load(),
                                ),
                                self.send_asset2(
                                    self.swap_output_amount_store.load()
                                ),
                                save_latest_cumsum_volume(
                                    self.swap_input_amount_less_fees_store.load(),
                                    self.swap_output_amount_store.load(),
                                ),
                            ]
                        ),
                        Seq(
                            [
                                self.swap_output_amount_store.store(
                                    self.swap_exact_asset2_for(
                                        self.swap_input_amount_less_fees_store.load()
                                    )
                                ),
                                decrement(
                                    self.balance_1,
                                    self.swap_output_amount_store.load(),
                                ),
                                increment(
                                    self.balance_2,
                                    self.swap_input_amount_store.load(),
                                ),
                                self.send_asset1(
                                    self.swap_output_amount_store.load()
                                ),
                                save_latest_cumsum_volume(
                                    self.swap_output_amount_store.load(),
                                    self.swap_input_amount_less_fees_store.load(),
                                ),
                            ]
                        ),
                    ),
                    Assert(self.swap_output_amount_store.load() > Int(0)),
                    Assert(
                        self.swap_output_amount_store.load()
                        >= min_amount_to_swap_for
                    ),
                ]
            )

        def handle_swap_for_exact():
            """Handle swap for exact by calculating the amount of asset1 or asset2 to swap for."""
            exact_amount_to_swap_for = Btoi(Txn.application_args[1])

            swap_fee = (
                WideRatio(
                    [
                        self.required_swap_input_amount_store.load(),
                        FIXED_6_SCALE_FACTOR,
                    ],
                    [
                        FIXED_6_SCALE_FACTOR
                        - self.swap_fee_pct_scaled_var.get()
                    ],
                )
                + Int(1)
                - self.required_swap_input_amount_store.load()
            )

            return Seq(
                [
                    self.exact_amount_to_swap_for_store.store(
                        exact_amount_to_swap_for
                    ),
                    Assert(
                        self.exact_amount_to_swap_for_store.load() > Int(0)
                    ),
                    If(
                        self.swap_input_is_asset1_store.load(),
                        self.required_swap_input_amount_store.store(
                            self.swap_for_exact_asset2_amount(
                                self.exact_amount_to_swap_for_store.load()
                            )
                        ),
                        self.required_swap_input_amount_store.store(
                            self.swap_for_exact_asset1_amount(
                                self.exact_amount_to_swap_for_store.load()
                            )
                        ),
                    ),
                    Assert(
                        self.required_swap_input_amount_store.load() > Int(0)
                    ),
                    self.swap_fee_store.store(swap_fee),
                    self.required_swap_input_amount_plus_fees_store.store(
                        self.required_swap_input_amount_store.load()
                        + self.swap_fee_store.load()
                    ),
                    Assert(
                        self.swap_input_amount_store.load()
                        >= self.required_swap_input_amount_plus_fees_store.load()
                    ),
                    If(
                        self.swap_input_is_asset1_store.load(),
                        Seq(
                            [
                                increment(
                                    self.balance_1,
                                    self.required_swap_input_amount_plus_fees_store.load(),
                                ),
                                decrement(
                                    self.balance_2,
                                    self.exact_amount_to_swap_for_store.load(),
                                ),
                                self.send_asset2(
                                    self.exact_amount_to_swap_for_store.load()
                                ),
                                save_latest_cumsum_volume(
                                    self.required_swap_input_amount_store.load(),
                                    self.exact_amount_to_swap_for_store.load(),
                                ),
                            ]
                        ),
                        Seq(
                            [
                                decrement(
                                    self.balance_1,
                                    self.exact_amount_to_swap_for_store.load(),
                                ),
                                increment(
                                    self.balance_2,
                                    self.required_swap_input_amount_plus_fees_store.load(),
                                ),
                                self.send_asset1(
                                    self.exact_amount_to_swap_for_store.load()
                                ),
                                save_latest_cumsum_volume(
                                    self.exact_amount_to_swap_for_store.load(),
                                    self.required_swap_input_amount_store.load(),
                                ),
                            ]
                        ),
                    ),
                    self.residual_amount_store.store(
                        self.swap_input_amount_store.load()
                        - self.required_swap_input_amount_plus_fees_store.load()
                    ),
                ]
            )

        return Seq(
            [
                # update cumulative sum time weighted price
                save_latest_cumsum_time_weighted_price(),
                # check for updated reserve factor
                self.update_reserve_factor(),
                # validate txn type, on compete
                validate_asset_payment_txn(),
                # validate asset: txn type, amount, receiver, asset id
                validate_swap_txn(),
                # validate redeem residual txn
                validate_redeem_residual_txn(),
                # branch to handle swap-for-exact or swap-exact-for
                If(
                    is_swap_for_exact,
                    handle_swap_for_exact(),
                    handle_swap_exact_for(),
                ),
                # move protocol fee to reserves
                self.update_reserves(
                    self.swap_input_is_asset1_store.load(),
                    self.swap_fee_store.load(),
                ),
                # validate new ratio is within bounds
                self.validate_asset_ratio(),
                Int(1),
            ]
        )

    def redeem_residual(
        self,
        residual_source_idx,
        residual_source_action,
        residual_is_asset1,
        residual_asset_amount,
    ):
        """Redeem residual asset from pool."""

        def validate_redeem_residual_txn():
            """Validate redeem residual transaction."""
            return Seq(
                [
                    Assert(Txn.on_completion() == OnComplete.NoOp),
                    Assert(Txn.type_enum() == TxnType.ApplicationCall),
                ]
            )

        def validate_residual_source_txn():
            """Validate residual source transaction."""
            return Seq(
                [
                    verify_txn_is_named_application_call(
                        residual_source_idx, residual_source_action
                    )
                ]
            )

        def send_residual():
            """Send residual asset to user."""
            return If(
                residual_asset_amount > Int(0),
                If(
                    residual_is_asset1,
                    self.send_asset1(residual_asset_amount),
                    self.send_asset2(residual_asset_amount),
                ),
            )

        return Seq(
            [
                validate_redeem_residual_txn(),
                validate_residual_source_txn(),
                send_residual(),
                Int(1),
            ]
        )

    def on_redeem_pool_asset1_residual(self):
        """
        A method to redeem asset 1 residuals from the pool.
            - Updates the reserves
            - Updates the pool balances
            - Updates the LP circulation
            - Sends LP tokens to the caller
        """
        residual_is_asset1 = TRUE
        residual_amount = ImportScratchValue(
            REDEEM_POOL_ASSET1_RESIDUAL__POOL_IDX,
            self.pool_asset1_residual_store.slot.id,
        )
        return self.redeem_residual(
            REDEEM_POOL_ASSET1_RESIDUAL__POOL_IDX,
            AlgofiAMMPoolStrings.pool,
            residual_is_asset1,
            residual_amount,
        )

    def on_redeem_pool_asset2_residual(self):
        """
        A method to redeem asset 2 residuals from the pool.
            - Updates the reserves
            - Updates the pool balances
            - Updates the LP circulation
            - Sends LP tokens to the caller
        """
        residual_is_asset1 = FALSE
        residual_amount = ImportScratchValue(
            REDEEM_POOL_ASSET2_RESIDUAL__POOL_IDX,
            self.pool_asset2_residual_store.slot.id,
        )
        return self.redeem_residual(
            REDEEM_POOL_ASSET2_RESIDUAL__POOL_IDX,
            AlgofiAMMPoolStrings.pool,
            residual_is_asset1,
            residual_amount,
        )

    def on_redeem_swap_residual(self):
        """
        A method to redeem swap residuals from the pool.
            - Updates the reserves
            - Updates the pool balances
            - Updates the LP circulation
            - Sends LP tokens to the caller
        """
        residual_is_asset1 = ImportScratchValue(
            REDEEM_SWAP_RESIDUAL__SWAP_IDX,
            self.swap_input_is_asset1_store.slot.id,
        )
        residual_amount = ImportScratchValue(
            REDEEM_SWAP_RESIDUAL__SWAP_IDX, self.residual_amount_store.slot.id
        )
        return self.redeem_residual(
            REDEEM_SWAP_RESIDUAL__SWAP_IDX,
            AlgofiAMMPoolStrings.swap_for_exact,
            residual_is_asset1,
            residual_amount,
        )

    def on_flash_loan(self):
        """
        A method to flash loan assets from the pool.
            - Updates the reserves
            - Updates the pool balances
            - Updates the LP circulation
        """
        flash_loan_asset_id = Btoi(Txn.application_args[1])
        flash_loan_amount = Btoi(Txn.application_args[2])

        flash_loan_is_algo = flash_loan_asset_id == Int(1)
        flash_loan_is_valid_asset = Or(
            flash_loan_asset_id == self.asset1_id.get(),
            flash_loan_asset_id == self.asset2_id.get(),
        )
        flash_loan_is_asset1 = flash_loan_asset_id == self.asset1_id.get()
        flash_loan_amount_is_nonzero = flash_loan_amount > Int(0)
        max_asset1_flash_loan = WideRatio(
            [self.balance_1.get(), self.max_flash_loan_ratio.get()],
            [FIXED_6_SCALE_FACTOR],
        )
        max_asset2_flash_loan = WideRatio(
            [self.balance_2.get(), self.max_flash_loan_ratio.get()],
            [FIXED_6_SCALE_FACTOR],
        )
        flash_loan_fee = WideRatio(
            [flash_loan_amount, self.flash_loan_fee.get()],
            [FIXED_6_SCALE_FACTOR],
        ) + Int(1)

        def load_flash_loan_fee():
            """Load flash loan fee."""
            return Seq(
                [
                    self.flash_loan_fee_store.store(flash_loan_fee),
                ]
            )

        def validate_flash_loan_txn():
            """Validate flash loan transaction."""
            return Seq(
                [
                    Assert(Txn.on_completion() == OnComplete.NoOp),
                    Assert(Txn.type_enum() == TxnType.ApplicationCall),
                    Assert(Txn.group_index() == FLASH_LOAN_IDX),
                    Assert(flash_loan_is_valid_asset),
                    Assert(flash_loan_amount_is_nonzero),
                    If(
                        flash_loan_is_asset1,
                        Assert(flash_loan_amount <= max_asset1_flash_loan),
                        Assert(flash_loan_amount <= max_asset2_flash_loan),
                    ),
                ]
            )

        def validate_flash_loan_repay_txn():
            """Validate flash loan repay transaction."""
            return Seq(
                [
                    If(
                        flash_loan_is_algo,
                        Seq(
                            [
                                verify_txn_is_sending_algos_to_pool(
                                    FLASH_LOAN_REPAY_IDX
                                ),
                                Assert(
                                    Gtxn[FLASH_LOAN_REPAY_IDX].amount()
                                    == flash_loan_amount
                                    + self.flash_loan_fee_store.load()
                                ),
                            ]
                        ),
                        Seq(
                            [
                                verify_txn_is_sending_asa_to_pool(
                                    FLASH_LOAN_REPAY_IDX, flash_loan_asset_id
                                ),
                                Assert(
                                    Gtxn[FLASH_LOAN_REPAY_IDX].asset_amount()
                                    == flash_loan_amount
                                    + self.flash_loan_fee_store.load()
                                ),
                            ]
                        ),
                    )
                ]
            )

        def send_funds():
            """Send funds to borrower."""
            return If(
                flash_loan_is_asset1,
                self.send_asset1(flash_loan_amount),
                self.send_asset2(flash_loan_amount),
            )

        def update_balances():
            """Update pool and reserve asset balances to reflect the fees collected."""
            return Seq(
                [
                    If(
                        flash_loan_is_asset1,
                        increment(
                            self.balance_1, self.flash_loan_fee_store.load()
                        ),
                        increment(
                            self.balance_2, self.flash_loan_fee_store.load()
                        ),
                    ),
                    self.update_reserves(
                        flash_loan_is_asset1, self.flash_loan_fee_store.load()
                    ),
                ]
            )

        return Seq(
            [
                # check for updated reserve factor
                self.update_reserve_factor(),
                self.update_flash_loan_fee(),
                self.update_max_flash_loan_ratio(),
                # store down the calculated flash loan fee
                load_flash_loan_fee(),
                # verify the flash loan txn is properly structured and has valid args
                validate_flash_loan_txn(),
                # verify the final txn of this group is repaying the correct amount and asset
                validate_flash_loan_repay_txn(),
                # send funds to borrower
                send_funds(),
                # update pool and reserve asset balances to reflect the fees collected
                update_balances(),
                # validate new ratio is within bounds
                self.validate_asset_ratio(),
                Int(1),
            ]
        )

    def _admin_fns_list(self):
        """
        List the admin functions.

        Extracting this to a method allows for easier inheritance in different types of pools.
        """
        return [
            [
                Txn.application_args[0]
                == Bytes(AlgofiAMMPoolStrings.remove_reserves),
                self.on_remove_reserves(),
            ],
            [
                Txn.application_args[0]
                == Bytes(AlgofiAMMPoolStrings.update_swap_fee),
                self.on_update_swap_fee(),
            ],
            [
                Txn.application_args[0]
                == Bytes(AlgofiAMMPoolStrings.schedule_swap_fee_update),
                self.on_schedule_swap_fee_update(),
            ],
            [
                Txn.application_args[0]
                == Bytes(AlgofiAMMPoolStrings.increase_param_update_delay),
                self.on_increase_param_delay(),
            ],
        ]

    def approval_program(self):
        """Final approval program logic"""

        sender_is_admin = Txn.sender() == self.admin.get()
        is_no_op_appl_call = And(
            Txn.on_completion() == OnComplete.NoOp,
            Txn.type_enum() == TxnType.ApplicationCall,
        )

        program = Cond(
            [Txn.application_id() == Int(0), self.on_creation()],
            [
                Txn.on_completion() == OnComplete.DeleteApplication,
                Int(0),
            ],  # app can not be deleted
            [Txn.on_completion() == OnComplete.OptIn, Int(0)],  # no opt in
            [
                Txn.on_completion() == OnComplete.CloseOut,
                Int(0),
            ],  # no close out
            [
                self.initialized.get() == TRUE,
                Cond(
                    # admin functions
                    [sender_is_admin, Cond(*self._admin_fns_list())],
                    # only allow no ops for non-admin functions
                    [
                        is_no_op_appl_call,
                        Cond(
                            # pool
                            [
                                Txn.application_args[0]
                                == Bytes(AlgofiAMMPoolStrings.pool),
                                self.on_pool(),
                            ],
                            [
                                Txn.application_args[0]
                                == Bytes(
                                    AlgofiAMMPoolStrings.redeem_pool_asset1_residual
                                ),
                                self.on_redeem_pool_asset1_residual(),
                            ],
                            [
                                Txn.application_args[0]
                                == Bytes(
                                    AlgofiAMMPoolStrings.redeem_pool_asset2_residual
                                ),
                                self.on_redeem_pool_asset2_residual(),
                            ],
                            # burn
                            [
                                Txn.application_args[0]
                                == Bytes(AlgofiAMMPoolStrings.burn_asset1_out),
                                self.on_burn_asset1_out(),
                            ],
                            [
                                Txn.application_args[0]
                                == Bytes(AlgofiAMMPoolStrings.burn_asset2_out),
                                self.on_burn_asset2_out(),
                            ],
                            # swap
                            [
                                Or(
                                    Txn.application_args[0]
                                    == Bytes(
                                        AlgofiAMMPoolStrings.swap_for_exact
                                    ),
                                    Txn.application_args[0]
                                    == Bytes(
                                        AlgofiAMMPoolStrings.swap_exact_for
                                    ),
                                ),
                                self.on_swap(),
                            ],
                            [
                                Txn.application_args[0]
                                == Bytes(
                                    AlgofiAMMPoolStrings.redeem_swap_residual
                                ),
                                self.on_redeem_swap_residual(),
                            ],
                            # flash loan
                            [
                                Txn.application_args[0]
                                == Bytes(AlgofiAMMPoolStrings.flash_loan),
                                self.on_flash_loan(),
                            ],
                        ),
                    ],
                ),
            ],
            # initialization
            [
                Txn.application_args[0]
                == Bytes(AlgofiAMMPoolStrings.initialize_pool),
                self.on_initialize_pool(),
            ],
        )

        return program
