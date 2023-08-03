# README.md

## Overview

The code excerpt is part of an Automated Market Maker (AMM) pool system built on the Algorand blockchain. It employs Algorand Smart Contracts (ASC1) expressed in PyTeal, a Python language binding for ASC1.

This document offers a thorough analysis of the `approval_program` function, with a focus on non-administrative operations.

## AMM Implementation

The `approval_program` method orchestrates the logic for approving transactions and updates to the AMM pool. It returns a program that represents a conditional statement, inspecting the pool's state and the operation being performed, and consequently invoking the appropriate function for that operation.

Here's an in-depth look into the non-administrative operations handled by AMM:

### Pool Operations

- `pool`: This operation manages general functionality related to the AMM pool, handled by the `on_pool` method.
- `redeem_pool_asset1_residual`: This operation is responsible for redeeming residuals for a specific asset (asset1) in the pool, governed by the `on_redeem_pool_asset1_residual` method.
- `redeem_pool_asset2_residual`: This operation is analogous to the previous one but for a different asset (asset2), as implemented by the `on_redeem_pool_asset2_residual` method.

### Burn Operations

- `burn_asset1_out`: This operation destroys or "burns" a quantity of asset1, as governed by the `on_burn_asset1_out` method.
- `burn_asset2_out`: This operation burns a quantity of asset2, as implemented by the `on_burn_asset2_out` method.

### Swap Operations

- `swap_for_exact`: This operation swaps one asset for an exact quantity of another, handled by the `on_swap` method.
- `swap_exact_for`: This operation swaps an exact quantity of one asset for another, as executed by the `on_swap` method.
- `redeem_swap_residual`: This operation handles the redemption of residuals from a swap operation, as implemented by the `on_redeem_swap_residual` method.

### Flash Loan Operations

- `flash_loan`: This operation manages flash loan transactions, where a loan is issued and repaid within the same transaction block. The specific implementation is handled by the `on_flash_loan` method.


## StableSwap Modifications

In a StableSwap scenario, the calculations for operations in the pool are modified to maintain the stability of asset values. This is achieved using a different price calculation formula and an amplification factor that can be adjusted over time. 

These modifications are implemented in three key mathematical methods:

- `compute_D`: This method calculates the StableSwap invariant `D` using an iterative calculation that converges to a solution. The StableSwap invariant `D` is a measure of the total liquidity available in the pool.
- `compute_other_asset_output_stable_swap`: This method calculates the amount of the other asset that will be received in a swap operation. This calculation uses a quadratic equation that is solved iteratively.
- `interpolate_amplification_factor`: This method calculates the current amplification factor based on the initial and future amplification factors and their respective timestamps. The amplification factor influences the price curve of the swap operation.

## Further Information

For more details on AMM, Algorand Smart Contracts, and PyTeal, please refer to the following resources:

- [Automated Market Makers](https://www.investopedia.com/terms/a/automated-market-maker-amm.asp)
- [Introducing NanoSwap](https://blog.algofi.org/introducing-nanoswap-632ce7ae942b)
- [Algorand Smart Contracts](https://developer.algorand.org/docs/features/asc1/)
- [PyTeal Documentation](https://pyteal.readthedocs.io/en/latest/)