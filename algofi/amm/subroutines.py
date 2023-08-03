"""Contains subroutines used in the Algofi AMM."""

from pyteal import *

from algofi.amm.constants import *
from algofi.amm.contract_strings import AlgofiAMMManagerStrings

# WIDELY USED FCNS


@Subroutine(TealType.uint64)
def calculate_integer_wrapped_value(current_value: Expr, addend: Expr) -> Expr:
    """Calculates the new value of a wrapped integer variable."""
    remaining_integer_space = MAX_INT_U64 - current_value
    return If(
        addend > remaining_integer_space,
        Return(addend - remaining_integer_space - Int(1)),
        Return(current_value + addend),
    )


@Subroutine(TealType.none)
def opt_in_to_asa(asset_id: Expr) -> Expr:
    """Opt in to an ASA."""
    return Seq(
        [
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetField(
                TxnField.type_enum, TxnType.AssetTransfer
            ),
            InnerTxnBuilder.SetField(TxnField.xfer_asset, asset_id),
            InnerTxnBuilder.SetField(TxnField.asset_amount, Int(0)),
            InnerTxnBuilder.SetField(
                TxnField.asset_receiver, Global.current_application_address()
            ),
            InnerTxnBuilder.SetField(TxnField.fee, Int(0)),
            InnerTxnBuilder.Submit(),
        ]
    )


@Subroutine(TealType.none)
def send_asa(asset_id: Expr, amount: Expr) -> Expr:
    """Send an ASA."""
    return Seq(
        [
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetField(
                TxnField.type_enum, TxnType.AssetTransfer
            ),
            InnerTxnBuilder.SetField(TxnField.xfer_asset, asset_id),
            InnerTxnBuilder.SetField(TxnField.asset_amount, amount),
            InnerTxnBuilder.SetField(TxnField.asset_receiver, Txn.sender()),
            InnerTxnBuilder.SetField(TxnField.fee, Int(0)),
            InnerTxnBuilder.Submit(),
        ]
    )


@Subroutine(TealType.none)
def send_algo(amount: Expr) -> Expr:
    """Send Algo."""
    return Seq(
        [
            Assert(
                Ge(
                    Balance(Global.current_application_address()),
                    amount + Global.min_balance(),
                )
            ),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetField(TxnField.type_enum, TxnType.Payment),
            InnerTxnBuilder.SetField(TxnField.amount, amount),
            InnerTxnBuilder.SetField(TxnField.receiver, Txn.sender()),
            InnerTxnBuilder.SetField(TxnField.fee, Int(0)),
            InnerTxnBuilder.Submit(),
        ]
    )


@Subroutine(TealType.none)
def send_algo_to_receiver(amount: Expr, receiver: Expr) -> Expr:
    """Send Algo to a receiver."""
    return Seq(
        [
            Assert(
                Ge(
                    Balance(Global.current_application_address()),
                    amount + Global.min_balance(),
                )
            ),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetField(TxnField.type_enum, TxnType.Payment),
            InnerTxnBuilder.SetField(TxnField.amount, amount),
            InnerTxnBuilder.SetField(TxnField.receiver, receiver),
            InnerTxnBuilder.SetField(TxnField.fee, Int(0)),
            InnerTxnBuilder.Submit(),
        ]
    )


@Subroutine(TealType.none)
def op_up(fee: Expr, op_farm_app_id: Expr):
    """Increase the available operations for the group transaction."""
    i = ScratchVar(TealType.uint64)
    n = fee / Int(1000)
    return For(i.store(Int(0)), i.load() < n, i.store(i.load() + Int(1))).Do(
        Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.ApplicationCall,
                    TxnField.application_id: op_farm_app_id,
                    TxnField.application_args: [
                        Bytes(AlgofiAMMManagerStrings.farm_ops)
                    ],
                    TxnField.fee: Int(0),
                }
            ),
            InnerTxnBuilder.Submit(),
        )
    )


def create_lp_asset(
    lp_id, lp_asset_prefix, asset1_id, asset2_id, lp_asset_name_store
):
    """Creates the LP asset."""
    asset1_name = AssetParam.unitName(asset1_id)
    asset2_name = AssetParam.unitName(asset2_id)
    asset_names_concatenated_algo = Concat(
        lp_asset_prefix,
        Concat(Bytes("ALGO"), Concat(Bytes("-"), asset2_name.value())),
    )
    asset_names_concatenated_asa = Concat(
        lp_asset_prefix,
        Concat(asset1_name.value(), Concat(Bytes("-"), asset2_name.value())),
    )
    create_lp_asset_name = Seq(
        [
            If(
                asset1_id == Int(1),
                Seq(
                    [
                        asset2_name,
                        Assert(asset2_name.hasValue()),
                        lp_asset_name_store.store(
                            asset_names_concatenated_algo
                        ),
                    ]
                ),
                Seq(
                    [
                        asset1_name,
                        asset2_name,
                        Assert(asset1_name.hasValue()),
                        Assert(asset2_name.hasValue()),
                        lp_asset_name_store.store(
                            asset_names_concatenated_asa
                        ),
                    ]
                ),
            ),
        ]
    )

    return Seq(
        [
            create_lp_asset_name,
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetField(TxnField.type_enum, TxnType.AssetConfig),
            InnerTxnBuilder.SetField(
                TxnField.config_asset_name, lp_asset_name_store.load()
            ),
            InnerTxnBuilder.SetField(
                TxnField.config_asset_unit_name, Bytes("AF-POOL")
            ),
            InnerTxnBuilder.SetField(
                TxnField.config_asset_total, MAX_CIRCULATION
            ),
            InnerTxnBuilder.SetField(
                TxnField.config_asset_decimals, LP_DECIMALS
            ),
            InnerTxnBuilder.SetField(TxnField.config_asset_url, URL),
            InnerTxnBuilder.SetField(
                TxnField.config_asset_manager,
                Global.current_application_address(),
            ),
            InnerTxnBuilder.SetField(
                TxnField.config_asset_reserve,
                Global.current_application_address(),
            ),
            InnerTxnBuilder.Submit(),
            lp_id.put(InnerTxn.created_asset_id()),
        ]
    )
