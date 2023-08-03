from inspect import currentframe

from pyteal import *

from algofi.v2_staking.constants import DEV_MODE


def increment(var, amount):
    if type(var) == ScratchVar:
        return var.store(var.load() + amount)
    else:
        return var.put(var.get() + amount)


def decrement(var, amount):
    if type(var) == ScratchVar:
        return var.store(var.load() - amount)
    else:
        return var.put(var.get() - amount)


def maximum(var1, var2):
    return If(var1 > var2).Then(var1).Else(var2)


def minimum(var1, var2):
    return If(var1 < var2).Then(var1).Else(var2)


def MagicAssert(a):
    if DEV_MODE:
        return Assert(And(a, Int(currentframe().f_back.f_lineno)))
    else:
        return Assert(a)


# VALIDATION HELPER FUNCTIONS
def verify_txn_is_named_application_call(idx, name):
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
    return Seq(
        [
            MagicAssert(Gtxn[idx].type_enum() == TxnType.Payment),
            MagicAssert(Gtxn[idx].receiver() == receiver),
            MagicAssert(Gtxn[idx].amount() > Int(0)),
        ]
    )


@Subroutine(TealType.none)
def verify_txn_is_asset_transfer(idx: Expr, receiver: Expr, asset_id: Expr):
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
    return Seq(
        [
            MagicAssert(Gtxn[idx].type_enum() == TxnType.ApplicationCall),
            MagicAssert(Gtxn[idx].on_completion() == OnComplete.NoOp),
            MagicAssert(Gtxn[idx].application_id() == application_id),
            MagicAssert(Gtxn[idx].application_args[0] == Bytes(name)),
        ]
    )


def verify_txn_account(txn_idx, account_idx, expected_account):
    return MagicAssert(Gtxn[txn_idx].accounts[account_idx] == expected_account)


# INNER TXN HELPERS


@Subroutine(TealType.none)
def send_asa(asset_id: Expr, amount: Expr, receiver: Expr) -> Expr:
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
    return send_asa(id, Int(0), Global.current_application_address())
