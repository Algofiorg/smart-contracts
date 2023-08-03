"""Contains the mathematical implementation of the Stable Pool variation of the Algofi AMM."""

from pyteal import *

from algofi.amm.constants import FIXED_6_SCALE_FACTOR


@Subroutine(TealType.uint64)
def compute_D(
    asset1_amount: Expr,
    asset2_amount: Expr,
    amplification_param: Expr,
):
    """
    Computes the StableSwap invariant D in non-overflowing integer operations

    This is an iterative calculation which uses the following equation:
        A * sum(x_i) * n**n + D = A * D * n**n + D**(n+1) / (n**n * prod(x_i))

    Which converges to a solution, D, where:
        D[j+1] = (A * n**n * sum(x_i) - D[j]**(n+1) / (n**n prod(x_i))) / (A * n**n - 1)
    """
    n_coins = Int(2)
    S = asset1_amount + asset2_amount

    D_estimate = ScratchVar(TealType.bytes)
    D_prev = ScratchVar(TealType.bytes)
    D_prod_denom = ScratchVar(TealType.bytes)
    D_prod = ScratchVar(TealType.bytes)
    AnnS = ScratchVar(TealType.bytes)
    i = ScratchVar(TealType.uint64)

    D_prod_num_calc = BytesMul(
        D_prev.load(), BytesMul(D_prev.load(), D_prev.load())
    )  # D**(n+1)
    D_prod_denom_calc = BytesMul(
        Itob(Exp(n_coins, n_coins)),
        BytesMul(Itob(asset2_amount), Itob(asset1_amount)),  # nn*(P[x_i])
    )
    D_prod_calc = BytesDiv(D_prod_num_calc, D_prod_denom.load())

    Ann_calc = amplification_param * Exp(n_coins, n_coins)
    AnnS_calc = BytesDiv(
        BytesMul(Itob(Ann_calc), Itob(S)), Itob(FIXED_6_SCALE_FACTOR)
    )

    D_estimate_num_calc = BytesMul(
        BytesAdd(
            AnnS.load(),
            BytesMul(D_prod.load(), Itob(n_coins)),
        ),
        D_prev.load(),
    )
    D_estimate_denom_calc = BytesAdd(
        BytesDiv(
            BytesMul(Itob(Ann_calc - FIXED_6_SCALE_FACTOR), D_prev.load()),
            Itob(FIXED_6_SCALE_FACTOR),
        ),
        BytesMul(D_prod.load(), Itob(n_coins + Int(1))),
    )

    D_estimate_calc = BytesDiv(D_estimate_num_calc, D_estimate_denom_calc)
    calc = Seq(
        If(S == Int(0)).Then(Return(Int(0))),
        # Store expensive calcs that don't need to be recomputed
        AnnS.store(AnnS_calc),
        D_prod_denom.store(D_prod_denom_calc),
        # First guess
        D_estimate.store(Itob(S)),
        For(
            i.store(Int(0)), i.load() < Int(255), i.store(i.load() + Int(1))
        ).Do(
            Seq(
                D_prev.store(D_estimate.load()),
                D_prod.store(D_prod_calc),
                D_estimate.store(D_estimate_calc),
                If(BytesGt(D_estimate.load(), D_prev.load()))
                .Then(
                    If(
                        BytesLe(
                            BytesMinus(D_estimate.load(), D_prev.load()),
                            Itob(Int(1)),
                        )
                    ).Then(Return(Btoi(D_estimate.load())))
                )
                .Else(
                    If(
                        BytesLe(
                            BytesMinus(D_prev.load(), D_estimate.load()),
                            Itob(Int(1)),
                        )
                    ).Then(Return(Btoi(D_estimate.load())))
                ),
            )
        ),
        Assert(i.load() < Int(255)),  # did not converge, throw error
        Return(Int(0)),  # unreachable code
    )

    return calc


@Subroutine(TealType.uint64)
def compute_other_asset_output_stable_swap(
    input_asset_new_total: Expr,
    input_asset_previous_total: Expr,
    previous_output_asset_total: Expr,
    amplification_param: Expr,
):
    """
    Computes the amount of the other asset that will be received in a swap

    The input/output nomenclature is referring to inputs to the equation, not
    the trade itself. In "swap for exact" case the input/output is the asset
    (sent to the pool)/(received from the pool).

    In "swap exact for" case it is the reverse - input/output is
    (received from the pool)/(sent to the pool) since we need to back out the
    amount to send to the pool from the desired received amount.

    Calculate x[j] if one makes x[i] = x. This is done by solving quadratic
    equation iteratively.
    x_1**2 + x_1 * (sum' - (A*n**n - 1) * D / (A * n**n)) = D ** (n + 1) / (n ** (2 * n) * prod' * A)
    x_1**2 + b*x_1 = c
    x_1 = (x_1**2 + c) / (2*x_1 + b)
    """
    n_assets = Int(2)
    D = ScratchVar(TealType.uint64)
    b = ScratchVar(TealType.uint64)
    c = ScratchVar(TealType.bytes)
    new_output_asset_total_estimate = ScratchVar(TealType.uint64)
    new_output_asset_total_estimate_prev = ScratchVar(TealType.uint64)
    i = ScratchVar(TealType.uint64)

    Ann_calc = amplification_param * Exp(n_assets, n_assets)
    S = input_asset_new_total

    b_calc = S + WideRatio([D.load(), FIXED_6_SCALE_FACTOR], [Ann_calc])
    c_calc = BytesDiv(
        BytesMul(
            Itob(D.load()),
            BytesMul(
                Itob(D.load()),
                BytesMul(Itob(D.load()), Itob(FIXED_6_SCALE_FACTOR)),
            ),
        ),
        BytesMul(
            Itob(input_asset_new_total),
            BytesMul(Itob(Ann_calc), Itob(Exp(n_assets, n_assets))),
        ),
    )

    ret_calc = Seq(
        If(
            previous_output_asset_total
            > new_output_asset_total_estimate.load(),
            Return(
                previous_output_asset_total
                - new_output_asset_total_estimate.load()
            ),  # swap for exact
            Return(
                new_output_asset_total_estimate.load()
                - previous_output_asset_total
            ),
        )  # swap exact for
    )

    estimate_num_calc = BytesAdd(
        BytesMul(
            Itob(new_output_asset_total_estimate.load()),
            Itob(new_output_asset_total_estimate.load()),
        ),
        c.load(),
    )

    estimate_denom_calc = Itob(
        Int(2) * new_output_asset_total_estimate.load() + b.load() - D.load()
    )
    estimate_calc = Btoi(BytesDiv(estimate_num_calc, estimate_denom_calc))

    calc = Seq(
        # Store expensive calcs that don't need to be recomputed
        D.store(
            compute_D(
                input_asset_previous_total,
                previous_output_asset_total,
                amplification_param,
            )
        ),
        b.store(b_calc),
        c.store(c_calc),
        # First guess
        new_output_asset_total_estimate.store(D.load()),
        For(
            i.store(Int(0)), i.load() < Int(255), i.store(i.load() + Int(1))
        ).Do(
            Seq(
                new_output_asset_total_estimate_prev.store(
                    new_output_asset_total_estimate.load()
                ),
                new_output_asset_total_estimate.store(estimate_calc),
                If(
                    new_output_asset_total_estimate.load()
                    > new_output_asset_total_estimate_prev.load()
                )
                .Then(
                    If(
                        new_output_asset_total_estimate.load()
                        - new_output_asset_total_estimate_prev.load()
                        <= Int(1)
                    ).Then(ret_calc)
                )
                .Else(
                    If(
                        new_output_asset_total_estimate_prev.load()
                        - new_output_asset_total_estimate.load()
                        <= Int(1)
                    ).Then(ret_calc)
                ),
            )
        ),
        Assert(i.load() < Int(255)),  # did not converge, throw error
        Return(Int(0)),  # unreachable
    )

    return calc


@Subroutine(TealType.uint64)
def interpolate_amplification_factor(
    initial_A: Expr, future_A: Expr, initial_A_time: Expr, future_A_time: Expr
):
    return Seq(
        If(Global.latest_timestamp() < future_A_time)
        .Then(
            If(future_A > initial_A)
            .Then(
                Return(
                    initial_A
                    + (future_A - initial_A)
                    * (Global.latest_timestamp() - initial_A_time)
                    / (future_A_time - initial_A_time)
                )
            )
            .Else(
                Return(
                    initial_A
                    - (initial_A - future_A)
                    * (Global.latest_timestamp() - initial_A_time)
                    / (future_A_time - initial_A_time)
                )
            )
        )
        .Else(Return(future_A))
    )
