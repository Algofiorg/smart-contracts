"""A contract used modify the stable AMMPool to use a moving ratio."""

from pyteal import *

from contracts.amm.constants import (
    DEFAULT_STABLESWAP_FEE_PCT_SCALED,
    MAX_AMPLIFICATION_FACTOR,
)
from contracts.amm.contract_strings import AMMPoolStrings
from contracts.amm.pool import AMMPool
from contracts.amm.stable_swap_math import (
    compute_D,
    compute_other_asset_output_stable_swap,
    interpolate_amplification_factor,
)
from contracts.amm.subroutines import op_up
from contracts.utils.wrapped_var import *


class AMMStablePool(AMMPool):
    """Stable pool contract."""

    def __init__(self, manager_app_id):
        super().__init__(manager_app_id, DEFAULT_STABLESWAP_FEE_PCT_SCALED)
        self.initial_amplification_factor = WrappedVar(
            AMMPoolStrings.initial_amplification_factor, GLOBAL_VAR
        )
        self.future_amplification_factor = WrappedVar(
            AMMPoolStrings.future_amplification_factor, GLOBAL_VAR
        )
        self.initial_amplification_factor_time = WrappedVar(
            AMMPoolStrings.initial_amplification_factor_time, GLOBAL_VAR
        )
        self.future_amplification_factor_time = WrappedVar(
            AMMPoolStrings.future_amplification_factor_time, GLOBAL_VAR
        )
        self.lp_asset_prefix = Bytes("AF-NANO-POOL-")

    def swap_exact_asset1_for(self, asset1_amount):
        """Swaps an exact amount of asset 1 for a variable amount of asset 2."""

        return Seq(
            op_up(
                Txn.fee() - Int(2) * Global.min_txn_fee(),
                self.manager_app_id_var.get(),
            ),
            compute_other_asset_output_stable_swap(
                self.balance_1.get() + asset1_amount,
                self.balance_1.get(),
                self.balance_2.get(),
                self.get_amplification_factor(),
            )
            - Int(1),
        )

    def swap_exact_asset2_for(self, asset2_amount):
        """Swaps an exact amount of asset 2 for a variable amount of asset 1."""

        return Seq(
            op_up(
                Txn.fee() - Int(2) * Global.min_txn_fee(),
                self.manager_app_id_var.get(),
            ),
            compute_other_asset_output_stable_swap(
                self.balance_2.get() + asset2_amount,
                self.balance_2.get(),
                self.balance_1.get(),
                self.get_amplification_factor(),
            )
            - Int(1),
        )

    def swap_for_exact_asset1_amount(self, asset1_amount):
        """Swaps a variable amount of asset 2 for an exact amount of asset 1."""

        return Seq(
            op_up(
                Txn.fee() - Int(2) * Global.min_txn_fee(),
                self.manager_app_id_var.get(),
            ),
            compute_other_asset_output_stable_swap(
                self.balance_1.get() - asset1_amount,
                self.balance_1.get(),
                self.balance_2.get(),
                self.get_amplification_factor(),
            )
            + Int(1),
        )

    def swap_for_exact_asset2_amount(self, asset2_amount):
        """Swaps a variable amount of asset 1 for an exact amount of asset 2."""

        return Seq(
            op_up(
                Txn.fee() - Int(2) * Global.min_txn_fee(),
                self.manager_app_id_var.get(),
            ),
            compute_other_asset_output_stable_swap(
                self.balance_2.get() - asset2_amount,
                self.balance_2.get(),
                self.balance_1.get(),
                self.get_amplification_factor(),
            )
            + Int(1),
        )

    def calculate_lp_issuance(self, pool_is_empty):
        """Calculates the amount of LP tokens to issue for a given deposit."""

        D0_store = ScratchVar(TealType.uint64)
        D0_calc = compute_D(
            self.balance_1.get(),
            self.balance_2.get(),
            self.get_amplification_factor(),
        )

        D1_calc = compute_D(
            self.balance_1.get()
            + self.adjusted_pool_asset1_amount_store.load(),
            self.balance_2.get()
            + self.adjusted_pool_asset2_amount_store.load(),
            self.get_amplification_factor(),
        )

        lp_issued_calc = WideRatio(
            [self.lp_circulation.get(), D1_calc - D0_store.load()],
            [D0_store.load()],
        )

        return If(
            pool_is_empty,
            self.lp_issued_store.store(D1_calc),
            Seq(
                op_up(
                    Txn.fee() - Int(3) * Global.min_txn_fee(),
                    self.manager_app_id,
                ),
                D0_store.store(D0_calc),
                self.lp_issued_store.store(lp_issued_calc),
            ),
        )

    def get_amplification_factor(self):
        """Gets the current amplification factor."""

        return interpolate_amplification_factor(
            self.initial_amplification_factor.get(),
            self.future_amplification_factor.get(),
            self.initial_amplification_factor_time.get(),
            self.future_amplification_factor_time.get(),
        )

    def _admin_fns_list(self):
        """Gets the list of admin functions."""

        return super()._admin_fns_list() + [
            [
                Txn.application_args[0]
                == Bytes(AMMPoolStrings.ramp_amplification_factor),
                self.on_ramp_amplification_factor(),
            ],
            [
                Txn.application_args[0]
                == Bytes(AMMPoolStrings.update_swap_fee),
                self.on_update_swap_fee(),
            ],
            [
                Txn.application_args[0]
                == Bytes(AMMPoolStrings.schedule_swap_fee_update),
                self.on_schedule_swap_fee_update(),
            ],
            [
                Txn.application_args[0]
                == Bytes(AMMPoolStrings.increase_param_update_delay),
                self.on_increase_param_delay(),
            ],
        ]

    def on_ramp_amplification_factor(self):
        """Ramps the amplification factor."""

        sender_is_admin = Txn.sender() == self.admin.get()
        initial_A = self.get_amplification_factor()
        future_A = Btoi(Txn.application_args[1])
        future_time = Btoi(Txn.application_args[2])

        return Seq(
            Assert(sender_is_admin),
            Assert(
                future_time
                >= Global.latest_timestamp() + self.param_update_delay.get()
            ),
            Assert(future_A > Int(0)),
            Assert(future_A < MAX_AMPLIFICATION_FACTOR),
            self.initial_amplification_factor.put(initial_A),
            self.future_amplification_factor.put(future_A),
            self.initial_amplification_factor_time.put(
                Global.latest_timestamp()
            ),
            self.future_amplification_factor_time.put(future_time),
            Int(1),
        )

    def on_creation(self):
        """Creates the pool."""

        amplification_factor = Btoi(Txn.application_args[2])
        return Seq(
            self.future_amplification_factor.put(amplification_factor),
            super().on_creation(),
        )
