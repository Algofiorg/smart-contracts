"""A permissionless sender logic sig."""

from pyteal import *


class PermissionlessSender:
    def approval_program(self):
        return Seq(
            [
                Assert(Txn.type_enum() == TxnType.ApplicationCall),
                Assert(Txn.on_completion() == OnComplete.NoOp),
                Assert(Txn.close_remainder_to() == Global.zero_address()),
                Assert(Txn.rekey_to() == Global.zero_address()),
                Approve(),
            ]
        )
