"""Manager contract for the AlgoFi AMM."""

from pyteal import *

from algofi.amm.constants import (
    DEFAULT_RESERVE_FACTOR,
    FIXED_6_SCALE_FACTOR,
    INIT_FLASH_LOAN_FEE,
    INIT_MAX_FLASH_LOAN_RATIO,
    MAX_VALIDATOR_COUNT,
    N_FUND_LOGIC_SIG_TXN,
    N_FUND_MANAGER_TXN,
    N_INITIALIZE_POOL_TXN,
    N_OPT_IN_LOGIC_SIG_TXN,
)
from algofi.amm.contract_strings import *
from algofi.amm.subroutines import send_algo_to_receiver
from algofi.utils.wrapped_var import *


class AlgofiAMMPoolManagerRegistrant:
    """A helper class to represent the global state of a pool manager registrant."""

    def __init__(self):
        self.registered_pool_id = WrappedVar(
            AlgofiAMMManagerStrings.registered_pool_id, LOCAL_VAR, Int(0)
        )
        self.registered_asset_1_id = WrappedVar(
            AlgofiAMMManagerStrings.registered_asset_1_id, LOCAL_VAR, Int(0)
        )
        self.registered_asset_2_id = WrappedVar(
            AlgofiAMMManagerStrings.registered_asset_2_id, LOCAL_VAR, Int(0)
        )
        self.validator_index = WrappedVar(
            AlgofiAMMManagerStrings.validator_index, LOCAL_VAR, Int(0)
        )


class AlgofiAMMPoolManagerPool:
    """A helper class to access the represent the global state of a pool manager."""

    def __init__(self, pool_application_id):
        self.admin = WrappedVar(
            AlgofiAMMPoolStrings.admin,
            GLOBAL_EX_VAR,
            pool_application_id.load(),
        ).get()
        self.asset_1_id = WrappedVar(
            AlgofiAMMPoolStrings.asset1_id,
            GLOBAL_EX_VAR,
            pool_application_id.load(),
        ).get()
        self.asset_2_id = WrappedVar(
            AlgofiAMMPoolStrings.asset2_id,
            GLOBAL_EX_VAR,
            pool_application_id.load(),
        ).get()
        self.validator_index = WrappedVar(
            AlgofiAMMPoolStrings.validator_index,
            GLOBAL_EX_VAR,
            pool_application_id.load(),
        ).get()


class AlgofiAMMPoolManagerPoolValidator:
    """A helper class to access the represent the global state of a pool validator."""

    def __init__(self, validator_index):
        self.pool_hash = WrappedVar(
            Concat(
                Bytes(AlgofiAMMManagerStrings.pool_hash_prefix),
                Itob(validator_index.load()),
            ),
            GLOBAL_VAR,
            name_to_bytes=False,
        )


class AlgofiAMMPoolManager:
    """A class to represent the AlgoFi AMM Manager contract."""

    def __init__(self):
        # SCRATCH VARS
        self.pool_validator_index_store = ScratchVar(TealType.uint64, 0)
        self.pool_application_id_store = ScratchVar(TealType.uint64, 1)

        # STATE VARS
        self.admin = WrappedVar(AlgofiAMMManagerStrings.admin, GLOBAL_VAR)
        self.reserve_factor = WrappedVar(
            AlgofiAMMManagerStrings.reserve_factor, GLOBAL_VAR
        )
        self.flash_loan_fee = WrappedVar(
            AlgofiAMMManagerStrings.flash_loan_fee, GLOBAL_VAR
        )
        self.max_flash_loan_ratio = WrappedVar(
            AlgofiAMMManagerStrings.max_flash_loan_ratio, GLOBAL_VAR
        )

        # HELPER CLASSES
        self.registrant = AlgofiAMMPoolManagerRegistrant()
        self.pool = AlgofiAMMPoolManagerPool(self.pool_application_id_store)
        self.validator = AlgofiAMMPoolManagerPoolValidator(
            self.pool_validator_index_store
        )

    def on_creation(self):
        """A method called at smart contract creation."""
        return Seq(
            [
                self.admin.put(Global.creator_address()),
                self.reserve_factor.put(DEFAULT_RESERVE_FACTOR),
                self.flash_loan_fee.put(INIT_FLASH_LOAN_FEE),
                self.max_flash_loan_ratio.put(INIT_MAX_FLASH_LOAN_RATIO),
                Int(1),
            ]
        )

    # ADMIN FUNCTIONS

    def on_set_reserve_factor(self):
        """A method called by the admin to set the reserve factor."""

        new_reserve_factor = Btoi(Txn.application_args[1])
        sender_is_admin = Txn.sender() == self.admin.get()

        return Seq(
            [
                Assert(sender_is_admin),
                # check that we are increasing the min_scheduled_param_update_delay
                Assert(new_reserve_factor <= FIXED_6_SCALE_FACTOR),
                # update min_scheduled_param_update_delay
                self.reserve_factor.put(new_reserve_factor),
                Int(1),
            ]
        )

    def on_set_flash_loan_fee(self):
        """A method called by the admin to set the flash loan fee."""

        flash_loan_fee = Btoi(Txn.application_args[1])
        sender_is_admin = Txn.sender() == self.admin.get()

        return Seq(
            [
                Assert(sender_is_admin),
                # check that we are increasing the min_scheduled_param_update_delay
                Assert(flash_loan_fee <= FIXED_6_SCALE_FACTOR),
                # update min_scheduled_param_update_delay
                self.flash_loan_fee.put(flash_loan_fee),
                Int(1),
            ]
        )

    def on_set_max_flash_loan_ratio(self):
        """A method called by the admin to set the max flash loan ratio."""

        max_flash_loan_ratio = Btoi(Txn.application_args[1])
        sender_is_admin = Txn.sender() == self.admin.get()

        return Seq(
            [
                Assert(sender_is_admin),
                # check that we are increasing the min_scheduled_param_update_delay
                Assert(max_flash_loan_ratio <= FIXED_6_SCALE_FACTOR),
                # update min_scheduled_param_update_delay
                self.max_flash_loan_ratio.put(max_flash_loan_ratio),
                Int(1),
            ]
        )

    def on_set_validator(self):
        """A method called by the admin to set the validator for a pool."""

        validator_index = Btoi(Txn.application_args[1])
        approval_program_hash = Txn.application_args[2]
        sender_is_admin = Txn.sender() == self.admin.get()

        return Seq(
            [
                Assert(sender_is_admin),
                Assert(validator_index < MAX_VALIDATOR_COUNT),
                self.pool_validator_index_store.store(validator_index),
                self.validator.pool_hash.put(approval_program_hash),
                Int(1),
            ]
        )

    # LOGIC SIG OPTIN

    def on_user_opt_in(self):
        """

        A method called during the user opt in process.

        This method is responsible for validating the group transaction structure
        and the transaction parameters.
        """

        asset_1_id = Btoi(Txn.application_args[0])
        asset_2_id = Btoi(Txn.application_args[1])
        validator_index = Btoi(Txn.application_args[2])

        pool_application_id = Gtxn[N_INITIALIZE_POOL_TXN].application_id()
        pool_approval_program = AppParam.approvalProgram(pool_application_id)
        pool_approval_program_hash = Sha256(pool_approval_program.value())
        pool_clear_state_program = AppParam.clearStateProgram(
            pool_application_id
        )

        manager_clear_state_program = AppParam.clearStateProgram(
            Global.current_application_id()
        )

        def validate_group_structure():
            """A method to verify the group transaction structure."""
            return Seq(
                [
                    Assert(Global.group_size() == Int(4)),
                    Assert(Txn.group_index() == Int(N_OPT_IN_LOGIC_SIG_TXN)),
                ]
            )

        def validate_fund_manager_txn():
            """A method to verify the funding transaction."""
            return Seq(
                [
                    Assert(
                        Gtxn[N_FUND_MANAGER_TXN].receiver()
                        == Global.current_application_address()
                    ),
                    Assert(
                        Gtxn[N_FUND_MANAGER_TXN].type_enum() == TxnType.Payment
                    ),
                    Assert(Gtxn[N_FUND_MANAGER_TXN].amount() == Int(400000)),
                ]
            )

        def validate_fund_logic_sig_txn():
            """A method to verify the logic signature transaction."""
            return Seq(
                [
                    Assert(
                        Gtxn[N_FUND_LOGIC_SIG_TXN].receiver() == Txn.sender()
                    ),
                    Assert(
                        Gtxn[N_FUND_LOGIC_SIG_TXN].type_enum()
                        == TxnType.Payment
                    ),
                    Assert(Gtxn[N_FUND_LOGIC_SIG_TXN].amount() == Int(450000)),
                ]
            )

        def validate_pool_initialization_txn():
            """A method to verify the pool initialization transaction."""
            return Seq(
                [
                    Assert(
                        Gtxn[N_INITIALIZE_POOL_TXN].type_enum()
                        == TxnType.ApplicationCall
                    ),
                    Assert(
                        Gtxn[N_INITIALIZE_POOL_TXN].on_completion()
                        == OnComplete.NoOp
                    ),
                    Assert(
                        Gtxn[N_INITIALIZE_POOL_TXN].application_args[0]
                        == Bytes(AlgofiAMMPoolStrings.initialize_pool)
                    ),
                ]
            )

        def validate_pool_state():
            """A method to verify the pool state."""
            return Seq(
                [
                    Assert(asset_1_id < asset_2_id),
                    self.pool_application_id_store.store(pool_application_id),
                    self.pool.admin,
                    Assert(self.pool.admin.hasValue()),
                    self.pool.asset_1_id,
                    Assert(self.pool.asset_1_id.hasValue()),
                    self.pool.asset_2_id,
                    Assert(self.pool.asset_2_id.hasValue()),
                    self.pool.validator_index,
                    Assert(self.pool.validator_index.hasValue()),
                    Assert(self.pool.admin.value() == self.admin.get()),
                    Assert(self.pool.asset_1_id.value() == asset_1_id),
                    Assert(self.pool.asset_2_id.value() == asset_2_id),
                    Assert(
                        self.pool.validator_index.value() == validator_index
                    ),
                ]
            )

        def validate_pool_program():
            """A method to verify the pool program."""
            return Seq(
                [
                    self.pool_validator_index_store.store(validator_index),
                    pool_approval_program,
                    Assert(pool_approval_program.hasValue()),
                    Assert(
                        self.validator.pool_hash.get()
                        == pool_approval_program_hash
                    ),
                    pool_clear_state_program,
                    Assert(pool_clear_state_program.hasValue()),
                    manager_clear_state_program,
                    Assert(manager_clear_state_program.hasValue()),
                    Assert(
                        pool_clear_state_program.value()
                        == manager_clear_state_program.value()
                    ),
                ]
            )

        def fund_pool():
            """A method to fund the pool with initial algos."""
            return Seq(
                [
                    # TODO will need to find a better way to do this in AVM 1.1 but this works for now
                    send_algo_to_receiver(Int(400000), Txn.accounts[1])
                ]
            )

        def set_registrant_local_state():
            """A method to set the registrant's local state."""
            return Seq(
                [
                    self.registrant.registered_pool_id.put(
                        pool_application_id
                    ),
                    self.registrant.registered_asset_1_id.put(asset_1_id),
                    self.registrant.registered_asset_2_id.put(asset_2_id),
                    self.registrant.validator_index.put(validator_index),
                ]
            )

        return Seq(
            [
                # validate group transaction composition
                validate_group_structure(),
                validate_fund_manager_txn(),
                validate_fund_logic_sig_txn(),
                validate_pool_initialization_txn(),
                # validate target pool approval program and state
                validate_pool_program(),
                validate_pool_state(),
                # fund target pool algos so it can create its LP token on initialization
                fund_pool(),
                # register pool info in this logic sig's local state
                set_registrant_local_state(),
                Int(1),
            ]
        )

    def approval_program(self):
        """
        The approval program logic for the AlgoFi AMM Manager contract.

        A conditional over the transaction type and parameters is used
        to route the transaction to the appropriate method.
        """

        sender_is_admin = Txn.sender() == self.admin.get()
        is_no_op_appl_call = And(
            Txn.on_completion() == OnComplete.NoOp,
            Txn.type_enum() == TxnType.ApplicationCall,
        )

        return Cond(
            [Txn.application_id() == Int(0), self.on_creation()],
            [Txn.on_completion() == OnComplete.DeleteApplication, Int(0)],
            [
                Txn.on_completion() == OnComplete.OptIn,
                self.on_user_opt_in(),
            ],  # opt in pool
            [Txn.on_completion() == OnComplete.CloseOut, Int(0)],
            # admin calls
            [
                sender_is_admin,
                Cond(
                    [
                        is_no_op_appl_call,
                        Cond(
                            [
                                Txn.application_args[0]
                                == Bytes(
                                    AlgofiAMMManagerStrings.set_validator
                                ),
                                self.on_set_validator(),
                            ],
                            [
                                Txn.application_args[0]
                                == Bytes(
                                    AlgofiAMMManagerStrings.set_reserve_factor
                                ),
                                self.on_set_reserve_factor(),
                            ],
                            [
                                Txn.application_args[0]
                                == Bytes(
                                    AlgofiAMMManagerStrings.set_flash_loan_fee
                                ),
                                self.on_set_flash_loan_fee(),
                            ],
                            [
                                Txn.application_args[0]
                                == Bytes(
                                    AlgofiAMMManagerStrings.set_max_flash_loan_ratio
                                ),
                                self.on_set_max_flash_loan_ratio(),
                            ],
                        ),
                    ],
                ),
            ],
            [
                And(
                    Txn.on_completion() == OnComplete.NoOp,
                    Txn.application_args[0]
                    == Bytes(AlgofiAMMManagerStrings.farm_ops),
                ),
                Int(1),
            ],
        )
