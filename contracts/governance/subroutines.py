"""Global subroutines for governance contract."""

from inspect import currentframe

from pyteal import *

from contracts.governance.constants import DEV_MODE
from contracts.governance.contract_strings import VotingEscrowStrings


def MagicAssert(a):
    """Checks if a condition is true. If DEV_MODE is true, also returns the line number."""
    if DEV_MODE:
        return Assert(And(a, Int(currentframe().f_back.f_lineno)))
    else:
        return Assert(a)


@Subroutine(TealType.none)
def verify_txn_is_payment_and_amount(idx, receiver, amount):
    """Verifies that a transaction is a payment transaction with a certain amount."""
    return Seq(
        [
            MagicAssert(Gtxn[idx].type_enum() == TxnType.Payment),
            MagicAssert(Gtxn[idx].receiver() == receiver),
            MagicAssert(Gtxn[idx].amount() >= amount),
        ]
    )


@Subroutine(TealType.none)
def send_update_vebank_txn(target_account, ve_app_id):
    """Sends a transaction to update the vebank data."""
    return Seq(
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.sender: Global.current_application_address(),
                TxnField.application_id: ve_app_id,
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.on_completion: OnComplete.NoOp,
                # txn.sender is the person creating the proposal
                TxnField.accounts: [target_account],
                TxnField.application_args: [
                    Bytes(VotingEscrowStrings.update_vebank_data)
                ],
                TxnField.fee: Int(0),
            }
        ),
        InnerTxnBuilder.Submit(),
    )


@Subroutine(TealType.none)
def send_payment_txn(sender, receiver, amount):
    """Sends a payment transaction."""
    return Seq(
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.Payment,
                TxnField.sender: sender,
                TxnField.amount: amount,
                TxnField.receiver: receiver,
                TxnField.fee: Int(0),
            }
        ),
        InnerTxnBuilder.Submit(),
    )


@Subroutine(TealType.none)
def send_payment_with_rekey_txn(sender, receiver, amount, rekey_address):
    """Sends a payment transaction with a rekey address."""
    return Seq(
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.Payment,
                TxnField.sender: sender,
                TxnField.amount: amount,
                TxnField.receiver: receiver,
                TxnField.fee: Int(0),
                TxnField.rekey_to: rekey_address,
            }
        ),
        InnerTxnBuilder.Submit(),
    )


def increment(var, amount):
    """Increments a variable by a certain amount."""
    if type(var) == ScratchVar:
        return var.store(var.load() + amount)
    else:
        return var.put(var.get() + amount)


def decrement(var, amount):
    """Decrements a variable by a certain amount."""
    if type(var) == ScratchVar:
        return var.store(var.load() - amount)
    else:
        return var.put(var.get() - amount)


def maximum(var1, var2):
    """Computes the maximum of two variables."""
    return If(var1 > var2).Then(var1).Else(var2)


def minimum(var1, var2):
    """Computes the minimum of two variables."""
    return If(var1 < var2).Then(var1).Else(var2)


# VALIDATION HELPER FUNCTIONS
def verify_txn_is_named_application_call(idx, name):
    """Verifies that a transaction is a named application call."""
    return Seq(
        [
            MagicAssert(Gtxn[idx].on_completion() == OnComplete.NoOp),
            MagicAssert(Gtxn[idx].type_enum() == TxnType.ApplicationCall),
            MagicAssert(
                Gtxn[idx].application_id() == Global.current_application_id()
            ),
            MagicAssert(Gtxn[idx].application_args[0] == Bytes(name)),
        ]
    )


def verify_txn_is_sending_asa_to_contract(idx, asset_id):
    """Verifies that a transaction is sending an ASA to the contract."""
    return Seq(
        [
            MagicAssert(Gtxn[idx].type_enum() == TxnType.AssetTransfer),
            MagicAssert(Gtxn[idx].xfer_asset() == asset_id),
            MagicAssert(
                Gtxn[idx].asset_receiver()
                == Global.current_application_address()
            ),
            MagicAssert(Gtxn[idx].asset_amount() > Int(0)),
        ]
    )


@Subroutine(TealType.none)
def verify_txn_is_payment(idx: Expr, receiver: Expr) -> Expr:
    """Verifies that a transaction is a payment transaction."""
    return Seq(
        [
            MagicAssert(Gtxn[idx].type_enum() == TxnType.Payment),
            MagicAssert(Gtxn[idx].receiver() == receiver),
            MagicAssert(Gtxn[idx].amount() > Int(0)),
        ]
    )


@Subroutine(TealType.none)
def verify_txn_is_asset_transfer(idx: Expr, receiver: Expr, asset_id: Expr):
    """verifies that a transaction is an asset transfer."""
    return Seq(
        [
            MagicAssert(Gtxn[idx].type_enum() == TxnType.AssetTransfer),
            MagicAssert(Gtxn[idx].asset_receiver() == receiver),
            MagicAssert(Gtxn[idx].xfer_asset() == asset_id),
            MagicAssert(Gtxn[idx].asset_amount() > Int(0)),
        ]
    )


def verify_txn_is_named_no_op_application_call(
    idx, name, application_id=Global.current_application_id()
):
    """Verifies that a transaction is a named no-op application call."""
    return Seq(
        [
            MagicAssert(Gtxn[idx].type_enum() == TxnType.ApplicationCall),
            MagicAssert(Gtxn[idx].on_completion() == OnComplete.NoOp),
            MagicAssert(Gtxn[idx].application_id() == application_id),
            MagicAssert(Gtxn[idx].application_args[0] == Bytes(name)),
        ]
    )


def verify_txn_account(txn_idx, account_idx, expected_account):
    """Verifies that a transaction has a certain account."""
    return MagicAssert(Gtxn[txn_idx].accounts[account_idx] == expected_account)


# INNER TXN HELPERS


@Subroutine(TealType.none)
def send_asa(asset_id: Expr, amount: Expr, receiver: Expr) -> Expr:
    """Send an ASA."""
    return Seq(
        [
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetField(
                TxnField.type_enum, TxnType.AssetTransfer
            ),
            InnerTxnBuilder.SetField(TxnField.xfer_asset, asset_id),
            InnerTxnBuilder.SetField(TxnField.asset_amount, amount),
            InnerTxnBuilder.SetField(TxnField.asset_receiver, receiver),
            InnerTxnBuilder.SetField(TxnField.fee, Int(0)),
            InnerTxnBuilder.Submit(),
        ]
    )


@Subroutine(TealType.none)
def send_asa_from_address(
    sender: Expr, asset_id: Expr, amount: Expr, receiver: Expr
) -> Expr:
    """Send an ASA from a specified address."""
    return Seq(
        [
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetField(TxnField.sender, sender),
            InnerTxnBuilder.SetField(
                TxnField.type_enum, TxnType.AssetTransfer
            ),
            InnerTxnBuilder.SetField(TxnField.xfer_asset, asset_id),
            InnerTxnBuilder.SetField(TxnField.asset_amount, amount),
            InnerTxnBuilder.SetField(TxnField.asset_receiver, receiver),
            InnerTxnBuilder.SetField(TxnField.fee, Int(0)),
            InnerTxnBuilder.Submit(),
        ]
    )


@Subroutine(TealType.none)
def send_algo(amount: Expr, receiver: Expr) -> Expr:
    """Send Algo."""
    return Seq(
        [
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetField(TxnField.type_enum, TxnType.Payment),
            InnerTxnBuilder.SetField(TxnField.amount, amount),
            InnerTxnBuilder.SetField(TxnField.receiver, receiver),
            InnerTxnBuilder.SetField(TxnField.fee, Int(0)),
            InnerTxnBuilder.Submit(),
        ]
    )


@Subroutine(TealType.none)
def send_algo_from_address(sender: Expr, amount: Expr, receiver: Expr) -> Expr:
    """Send Algo from a specified address."""
    return Seq(
        [
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetField(TxnField.sender, sender),
            InnerTxnBuilder.SetField(TxnField.type_enum, TxnType.Payment),
            InnerTxnBuilder.SetField(TxnField.amount, amount),
            InnerTxnBuilder.SetField(TxnField.receiver, receiver),
            InnerTxnBuilder.SetField(TxnField.fee, Int(0)),
            InnerTxnBuilder.Submit(),
        ]
    )


def send_asa_set_fields(asa_id: Expr, receiver: Expr, amount: Expr):
    """Send an ASA."""
    return InnerTxnBuilder.SetFields(
        {
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: asa_id,
            TxnField.asset_receiver: receiver,
            TxnField.asset_amount: amount,
            TxnField.fee: Int(0),
        }
    )


# TODO can we change this from "into" to "into" globally
@Subroutine(TealType.none)
def opt_into_asa(id: Expr) -> Expr:
    """Opts into an ASA."""
    return send_asa(id, Int(0), Global.current_application_address())
