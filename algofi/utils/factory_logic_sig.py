"""Logic sig to register an algofi pool with the manager"""

from pyteal import *


class AlgofiPoolFactoryLogicSig:
    def __init__(
        self, manager_app_id, asset_1_id, asset_2_id, pool_validator_index
    ):
        self.manager_app_id = Int(manager_app_id)
        self.asset_1_id = Int(asset_1_id)
        self.asset_2_id = Int(asset_2_id)
        self.pool_validator_index = Int(pool_validator_index)

    """
    Verify that the only transaction permitted from this logic sig address is
    an opt in call to the designated manager with the expected application args
    and no rekey
    """

    def approval_program(self):
        return Seq(
            [
                Assert(self.asset_1_id < self.asset_2_id),
                Assert(Txn.type_enum() == TxnType.ApplicationCall),
                Assert(Txn.on_completion() == OnComplete.OptIn),
                Assert(Txn.application_id() == self.manager_app_id),
                Assert(Btoi(Txn.application_args[0]) == self.asset_1_id),
                Assert(Btoi(Txn.application_args[1]) == self.asset_2_id),
                Assert(
                    Btoi(Txn.application_args[2]) == self.pool_validator_index
                ),
                Assert(Txn.rekey_to() == Global.zero_address()),
                Int(1),
            ]
        )
