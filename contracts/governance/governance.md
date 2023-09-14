# README.md

## Overview

The provided code is part of a decentralized governance protocol built on the Algorand blockchain. This protocol involves the use of Algorand Smart Contracts (ASC1) written in PyTeal, a Python language binding for ASC1. The governance protocol includes mechanisms for creating, voting on, and executing proposals, which are vital components of decentralized governance.

Decentralized governance refers to the method by which decisions are made within a decentralized network. It involves the use of blockchain technology to allow participants, also known as stakeholders, to manage the protocol. This management typically involves voting on various protocol proposals such as changes to system parameters, feature improvements, or other updates.

There are two main components related to the handling of proposals in this code: the `ProposalFactory` and the `Proposal` classes. The `ProposalFactory` is responsible for creating new proposals, while each instance of the `Proposal` class represents an individual proposal.

## `ProposalFactory` Class

The `ProposalFactory` is responsible for validating user accounts and creating new proposals. It manages the creation of a new proposal when a user triggers the `create_proposal` function. This function checks if the user has enough voting power (vebank) to propose a new proposal, and if they do, it creates a new proposal contract. 

The `ProposalFactory` also sets various parameters in the protocol, such as the proposal template, the voting escrow app ID, the admin app ID, and the minimum vebank required to propose.

## `Proposal` Class

The `Proposal` class represents an individual proposal within the governance protocol. It holds the state of the proposal, including the title, link, and the amount of votes for or against it. 

Each `Proposal` has several key methods:

- `on_creation`: This method is called when a new proposal is created, setting the title and link of the proposal.
- `on_opt_into_admin`: This method is used to opt the proposal into the admin contract.
- `on_user_vote`: This method is used when a user votes on the proposal, storing the vote direction (for or against) and the amount of the vote.
- `on_user_close_out`: This method is used when a user closes out from the proposal.

## Governance Protocol

The Governance Protocol function is the primary function that dictates the logic of the governance protocol. The function returns a program that evaluates a conditional statement, examining the state of the contract and the type of operation being performed. Based on these conditions, it calls the corresponding function for that operation.

Here's an in-depth look into the operations handled in the Governance Protocol:

### Opt-in Functions

The Governance Protocol handles opt-in actions for users, storage accounts, and proposal contracts, enabling them to participate in the governance protocol.

- `user_opt_in`: This function sets the user's storage account, sets the account as not open to delegation, and initializes other parameters related to the user's participation in the governance protocol.
- `storage_account_opt_in`: This function manages the opt-in process for a storage account into the protocol, validating the associated transactions and rekeying to the current application.
- `proposal_contract_opt_in`: This function manages the opt-in process for a proposal contract. It verifies the proposal's creator, initializes the proposal state, and updates the last proposal creation time.

### Close-out Functions

The Governance Protocol also manages the actions related to closing out users and storage accounts:

- `user_close_out`: This function handles the process when a user's storage account is closed out. It ensures the storage account has been closed out of all proposals and rekeys the storage account to the user.
- `storage_account_close_out`: This function manages the process when a storage account is closed out, ensuring that it has been properly closed out.

### User Functions

The Governance Protocol handles a variety of user actions related to the governance protocol:

- `update_user_vebank`: This function updates a user's vebank (voting escrow bank), a representation of their voting power within the protocol.
- `vote`: This function enables users to vote on a proposal, updating vote totals and the number of proposals the user has participated in.
- `delegate`: This function allows a user to delegate their voting power to another user who is open to delegation.
- `validate`: This function validates a user's vote after voting has closed, checking whether the vote passed and setting the proposal's status accordingly.
- `undelegate`: This function allows a user to withdraw their delegation from another user.
- `delegated_vote`: This function enables a user to vote on behalf of another user, assuming that the latter has delegated their voting power to the former.
- `close_out_from_proposal`: This function manages the process of a user closing out from a proposal, decrementing the number of proposals they have participated in.
- `set_open_to_delegation`: This function allows a user to declare themselves open to having other users delegate their voting power to them.
- `set_not_open_to_delegation`: This function allows a user to declare themselves not open to delegation.

## `ProposalFactory` and `Proposal` Logic

The logic in both the `ProposalFactory` and `Proposal` classes also contains significant logic governing the functioning of the protocol. They dictate the conditional flow of transactions and updates, based on the state of the contract and the type of operation being performed.

In the `ProposalFactory`, the logic handles operations such as the setting of various protocol parameters and the creation of new proposals. In the `Proposal` class, it manages operations such as the creation of a proposal, voting on a proposal, and closing out from a proposal.