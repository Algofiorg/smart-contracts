# Algofi Smart Contracts

Algofi is a comprehensive decentralized application ecosystem built on the Algorand blockchain. It leverages Algorand Smart Contracts (ASC1), using PyTeal, a Python language binding for ASC1. The project consists of several key modules, each handling a specific function within the Algofi ecosystem:

## Automated Market Maker (AMM)

The AMM module employs an approval program that approves transactions and updates to the AMM pool. It handles various operations related to pool, burn, swap, and flash loan operations. AMM also includes StableSwap modifications to maintain the stability of asset values within the pool. You can read more about the AMM module in the [documentation](algofi/amm/amm.md).

## Governance

The Governance module is a decentralized protocol for creating, voting on, and executing proposals. It includes a `ProposalFactory` for creating new proposals and a `Proposal` class that represents an individual proposal. The logic within these classes orchestrates the creation and voting process on the proposals, managing the opt-in process, voting, delegation, validation, and close-out processes. Detailed information about the Governance module can be found in the [documentation](algofi/governance/governance.md).

## Staking Protocol

The Staking Protocol module offers a mechanism for users to stake and unstake assets and claim rewards. The `StakingContract` class manages the core staking functions and handles the rewards program for the contract. The logic in this class governs the flow of transactions and updates, based on the state of the contract and the type of operation being performed. More details about the Staking Protocol can be found in the [documentation](algofi/v2_staking/staking.md).