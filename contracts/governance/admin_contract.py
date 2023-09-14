"""Defines the admin contract for the governance system."""

from pyteal import *

from contracts.governance.constants import *
from contracts.governance.contract_strings import (
    AdminContractStrings,
    ProposalStrings,
    VotingEscrowStrings,
)
from contracts.governance.subroutines import *
from contracts.utils.wrapped_var import *

# SUBROUTINES


@Subroutine(TealType.none)
def vote_on_proposal_contract(
    voter_storage_account,
    proposal_contract_app_id,
    for_or_against,
    voting_amount,
):
    """Creates a subroutine for voting on a proposal contract."""
    return Seq(
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.sender: voter_storage_account,
                TxnField.application_id: proposal_contract_app_id,
                TxnField.on_completion: OnComplete.OptIn,
                TxnField.application_args: [
                    Bytes(ProposalStrings.user_vote),
                    Itob(for_or_against),
                    Itob(voting_amount),
                ],
                TxnField.fee: ZERO_FEE,
            }
        ),
        InnerTxnBuilder.Submit(),
    )


@Subroutine(TealType.none)
def close_out_storage_account_from_proposal(storage_account, proposal_id):
    """Creates a subroutine for closing out a storage account from a proposal."""
    return Seq(
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                # rekeyed to admin so this should be sent from admin
                TxnField.sender: storage_account,
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.on_completion: OnComplete.CloseOut,
                TxnField.application_args: [
                    Bytes(ProposalStrings.user_close_out)
                ],
                TxnField.application_id: proposal_id,
                TxnField.fee: ZERO_FEE,
            }
        ),
        InnerTxnBuilder.Submit(),
    )


class User:
    """Defines a user of the governance system."""

    def __init__(self, user_account, voting_escrow_app_id):
        self.voting_escrow_app_id = voting_escrow_app_id

        # USER STATE
        self.storage_account = WrappedVar(
            AdminContractStrings.storage_account, LOCAL_VAR, user_account
        )

        # USER EX VAR STATE
        self.vebank_external = WrappedVar(
            VotingEscrowStrings.user_amount_vebank,
            LOCAL_EX_VAR,
            user_account,
            voting_escrow_app_id,
        ).get()

        # STORAGE ACCOUNT STATE
        self.user_account = WrappedVar(
            AdminContractStrings.user_account,
            LOCAL_VAR,
            self.storage_account.get(),
        )
        self.open_to_delegation = WrappedVar(
            AdminContractStrings.open_to_delegation,
            LOCAL_VAR,
            self.storage_account.get(),
        )
        self.delegator_count = WrappedVar(
            AdminContractStrings.delegator_count,
            LOCAL_VAR,
            self.storage_account.get(),
        )
        self.delegating_to = WrappedVar(
            AdminContractStrings.delegating_to,
            LOCAL_VAR,
            self.storage_account.get(),
        )
        self.vebank = WrappedVar(
            AdminContractStrings.vebank,
            LOCAL_VAR,
            self.storage_account.get(),
        )
        self.num_proposals_opted_into = WrappedVar(
            AdminContractStrings.num_proposals_opted_into,
            LOCAL_VAR,
            self.storage_account.get(),
        )
        self.last_proposal_creation_time = WrappedVar(
            AdminContractStrings.last_proposal_creation_time,
            LOCAL_VAR,
            self.storage_account.get(),
        )

    def update_vebank(self):
        """Updates the user's vebank value."""
        return Seq(
            [
                # verify voting escrow app id is set
                MagicAssert(self.voting_escrow_app_id != UNSET),
                # send update vebank txn for user
                send_update_vebank_txn(
                    self.user_account.get(), self.voting_escrow_app_id
                ),
                # load and cache vebank value
                self.vebank_external,
                MagicAssert(self.vebank_external.hasValue()),
                self.vebank.put(self.vebank_external.value()),
            ]
        )


class Delegatee:
    """Defines a delegatee of the governance system."""

    def __init__(self, proposal_app_id):
        # SCRATCH VARS
        self.storage_address_store = ScratchVar(
            TealType.bytes,
            AdminContractScratchSlots.delegatee_storage_address,
        )

        # STORAGE ACCOUNT STATE
        self.open_to_delegation = WrappedVar(
            AdminContractStrings.open_to_delegation,
            LOCAL_VAR,
            self.storage_address_store.load(),
        )
        self.delegator_count = WrappedVar(
            AdminContractStrings.delegator_count,
            LOCAL_VAR,
            self.storage_address_store.load(),
        )

        # STORAGE ACCOUNT EX VAR STATE
        self.for_or_against = WrappedVar(
            ProposalStrings.for_or_against,
            LOCAL_EX_VAR,
            self.storage_address_store.load(),
            proposal_app_id,
        ).get()

    def load_delegatee(self, storage_address):
        """Loads the delegatee's storage account."""
        return self.storage_address_store.store(storage_address)

    def load_proposal_vote(self):
        """Loads the delegatee's vote on a proposal."""
        return Seq(
            [self.for_or_against, MagicAssert(self.for_or_against.hasValue())]
        )

    def get_proposal_vote(self):
        """Gets the delegatee's vote on a proposal."""
        return self.for_or_against.value()


class CloseOutUser:
    """A class for closing out a user's storage account."""

    def __init__(self):
        # SCRATCH VARS
        self.storage_address_store = ScratchVar(
            TealType.bytes,
            AdminContractScratchSlots.closeout_user_address,
        )

        # STORAGE ACCOUNT STATE
        self.num_proposals_opted_into = WrappedVar(
            AdminContractStrings.num_proposals_opted_into,
            LOCAL_VAR,
            self.storage_address_store.load(),
        )

    def load_user(self, storage_address):
        return self.storage_address_store.store(storage_address)


class StorageAccount:
    """A class for invariably storing the state of a user account."""

    def __init__(self, storage_account):
        # USER STATE
        self.user_account = WrappedVar(
            AdminContractStrings.user_account, LOCAL_VAR, storage_account
        )
        self.num_proposals_opted_into = WrappedVar(
            AdminContractStrings.num_proposals_opted_into,
            LOCAL_VAR,
            storage_account,
        )


class Proposal:
    """A class for storing the state of a proposal."""

    def __init__(self, quorum_value, super_majority):
        self.quorum_value = quorum_value
        self.super_majority = super_majority

        # SCRATCH VARS
        self.proposal_app_id_store = ScratchVar(
            TealType.uint64, AdminContractScratchSlots.proposal_app_id
        )

        # DERIVED STATE
        self.proposal_account_address = AppParam.address(
            self.proposal_app_id_store.load()
        )
        self.creator = AppParam.creator(self.proposal_app_id_store.load())

        # PROPOSAL STATE
        self.app_id = WrappedVar(
            AdminContractStrings.proposal_app_id,
            LOCAL_VAR,
            self.proposal_account_address.value(),
        )
        self.votes_for = WrappedVar(
            AdminContractStrings.votes_for,
            LOCAL_VAR,
            self.proposal_account_address.value(),
        )
        self.votes_against = WrappedVar(
            AdminContractStrings.votes_against,
            LOCAL_VAR,
            self.proposal_account_address.value(),
        )
        self.vote_close_time = WrappedVar(
            AdminContractStrings.vote_close_time,
            LOCAL_VAR,
            self.proposal_account_address.value(),
        )
        self.rejected = WrappedVar(
            AdminContractStrings.proposal_rejected,
            LOCAL_VAR,
            self.proposal_account_address.value(),
        )
        self.execution_time = WrappedVar(
            AdminContractStrings.execution_time,
            LOCAL_VAR,
            self.proposal_account_address.value(),
        )
        self.executed = WrappedVar(
            AdminContractStrings.executed,
            LOCAL_VAR,
            self.proposal_account_address.value(),
        )
        self.canceled_by_emergency_dao = WrappedVar(
            AdminContractStrings.canceled_by_emergency_dao,
            LOCAL_VAR,
            self.proposal_account_address.value(),
        )

    def load_proposal(self, proposal_app_id):
        """A method for loading a proposal."""
        return Seq(
            [
                # cache proposal app id
                self.proposal_app_id_store.store(proposal_app_id),
                # load proposal account address
                self.proposal_account_address,
                MagicAssert(self.proposal_account_address.hasValue()),
            ]
        )

    def load_proposal_creator(self):
        """A method for loading the proposal creator."""
        return Seq([self.creator, MagicAssert(self.creator.hasValue())])

    def is_open_for_voting(self):
        """A method for checking if a proposal is open for voting."""
        return Global.latest_timestamp() < self.vote_close_time.get()

    def vote_passed(self):
        """A method for checking if a proposal passed."""
        total_votes = self.votes_for.get() + self.votes_against.get()
        percent_approved = WideRatio(
            [self.votes_for.get(), FIXED_6_SCALE_FACTOR], [total_votes]
        )

        return And(
            # voting is closed
            Not(self.is_open_for_voting()),
            # execution time is unset
            self.canceled_by_emergency_dao.get() == FALSE,
            # total votes is greater than quorum
            total_votes >= self.quorum_value,
            # approval percentage is greater than super_majority
            percent_approved >= self.super_majority,
        )

    def is_executable(self):
        """A method for checking if a proposal is executable."""
        return And(
            self.execution_time.get() != UNSET,
            self.execution_time.get() <= Global.latest_timestamp(),
            self.executed.get() == FALSE,
            self.canceled_by_emergency_dao.get() == FALSE,
        )


class AdminContract:
    """Defines the admin contract for the governance system."""

    def __init__(self):
        # SCRATCH VARS
        self.min_balance_store = ScratchVar(
            TealType.uint64, AdminContractScratchSlots.min_balance
        )

        # GLOBAL VARS
        self.voting_escrow_app_id = WrappedVar(
            AdminContractStrings.voting_escrow_app_id, GLOBAL_VAR
        )
        self.quorum_value = WrappedVar(
            AdminContractStrings.quorum_value, GLOBAL_VAR
        )
        self.super_majority = WrappedVar(
            AdminContractStrings.super_majority, GLOBAL_VAR
        )
        self.proposal_duration = WrappedVar(
            AdminContractStrings.proposal_duration, GLOBAL_VAR
        )
        self.proposal_execution_delay = WrappedVar(
            AdminContractStrings.proposal_execution_delay, GLOBAL_VAR
        )
        self.proposal_creation_delay = WrappedVar(
            AdminContractStrings.proposal_creation_delay, GLOBAL_VAR
        )
        self.proposal_factory_address = WrappedVar(
            AdminContractStrings.proposal_factory_address, GLOBAL_VAR
        )
        self.emergency_dao_address = WrappedVar(
            AdminContractStrings.emergency_dao_address, GLOBAL_VAR
        )

        # USER ACCOUNT
        self.user = User(Txn.accounts[0], self.voting_escrow_app_id.get())
        self.target_user = User(
            Txn.accounts[1], self.voting_escrow_app_id.get()
        )

        # PROPOSAL ACCOUNTS
        self.proposal = Proposal(
            self.quorum_value.get(), self.super_majority.get()
        )

        # DELEGATEE
        self.delegatee = Delegatee(self.proposal.proposal_app_id_store.load())

        # CLOSE OUT PROPOSAL
        self.close_out_user = CloseOutUser()

        # CLOSE OUT STORAGE ACCOUNT
        self.storage_account = StorageAccount(Txn.accounts[0])

    # HELPER FUNCTIONS

    def user_owns_storage_account(self, user_account, storage_account):
        """A helper function for checking if a user owns a storage account."""
        storage_account_for_primary = App.localGet(
            user_account, Bytes(AdminContractStrings.storage_account)
        )
        user_account_for_storage = App.localGet(
            storage_account, Bytes(AdminContractStrings.user_account)
        )

        return Seq(
            MagicAssert(storage_account_for_primary == storage_account),
            MagicAssert(user_account_for_storage == user_account),
        )

    def verify_txn_is_opt_in_call(self, idx, app_id, sender=None, name=None):
        """A helper function for verifying a txn is an opt in call."""
        if name:
            return Seq(
                MagicAssert(Gtxn[idx].type_enum() == TxnType.ApplicationCall),
                MagicAssert(Gtxn[idx].on_completion() == OnComplete.OptIn),
                MagicAssert(Gtxn[idx].application_id() == app_id),
                MagicAssert(Gtxn[idx].application_args[0] == Bytes(name)),
            )
        elif sender:
            return Seq(
                MagicAssert(Gtxn[idx].type_enum() == TxnType.ApplicationCall),
                MagicAssert(Gtxn[idx].on_completion() == OnComplete.OptIn),
                MagicAssert(Gtxn[idx].application_id() == app_id),
                MagicAssert(Gtxn[idx].sender() == sender),
            )

    def verify_txn_is_close_out_call(self, idx, app_id, sender, name):
        """A helper function for verifying a txn is a close out call."""
        return Seq(
            MagicAssert(Gtxn[idx].type_enum() == TxnType.ApplicationCall),
            MagicAssert(Gtxn[idx].on_completion() == OnComplete.CloseOut),
            MagicAssert(Gtxn[idx].application_id() == app_id),
            MagicAssert(Gtxn[idx].application_args[0] == Bytes(name)),
            MagicAssert(Gtxn[idx].sender() == sender),
        )

    def verify_update_user_vebank_txn(self, idx, account):
        """A helper function for verifying an update_user_vebank txn."""
        return Seq(
            [
                # verify application call
                verify_txn_is_named_application_call(
                    idx, AdminContractStrings.update_user_vebank
                ),
                # verify account (update_user_vebank target account is in index 1)
                verify_txn_account(idx, 1, account),
            ]
        )

    # CREATION

    def on_creation(self):
        """Creates the admin contract."""
        quorum_value = Btoi(Txn.application_args[0])
        super_majority = Btoi(Txn.application_args[1])
        proposal_duration = Btoi(Txn.application_args[2])
        proposal_execution_delay = Btoi(Txn.application_args[3])
        emergency_dao_address = Txn.accounts[1]

        return Seq(
            # set emergency dao address
            self.emergency_dao_address.put(emergency_dao_address),
            # set control fields
            self.quorum_value.put(quorum_value),
            self.super_majority.put(super_majority),
            self.proposal_duration.put(proposal_duration),
            self.proposal_execution_delay.put(proposal_execution_delay),
            self.proposal_creation_delay.put(PROPOSAL_CREATION_DELAY),
            # initialize app/address fields to unset state
            self.voting_escrow_app_id.put(UNSET),
            self.proposal_factory_address.put(Global.zero_address()),
            Approve(),
        )

    # ADMIN

    def on_set_proposal_factory_address(self):
        """Sets the proposal factory address."""
        factory_address = Txn.accounts[1]

        return Seq(
            # set the proposal factory address
            self.proposal_factory_address.put(factory_address),
            Approve(),
        )

    def on_set_voting_escrow_app_id(self):
        """Sets the voting escrow app id."""
        escrow_app_id = Txn.applications[1]

        return Seq(
            # set the voting escrow app id
            self.voting_escrow_app_id.put(escrow_app_id),
            Approve(),
        )

    def on_cancel_proposal(self):
        """Cancels a proposal."""
        proposal_app_id = Txn.applications[1]

        return Seq(
            # load proposal
            self.proposal.load_proposal(proposal_app_id),
            # verify it has not been executed
            MagicAssert(self.proposal.executed.get() == FALSE),
            # set canceled by emergency dao
            self.proposal.canceled_by_emergency_dao.put(TRUE),
            # close voting
            self.proposal.vote_close_time.put(Global.latest_timestamp()),
            # unset execution time
            self.proposal.execution_time.put(UNSET),
            Approve(),
        )

    def on_fast_track_proposal(self):
        """A method for fast tracking a proposal."""
        proposal_app_id = Txn.applications[1]

        return Seq(
            # load proposal
            self.proposal.load_proposal(proposal_app_id),
            # verify proposal either has not yet expired or has passed (should not be able to fast_track a rejected, expired proposal)
            MagicAssert(
                Or(
                    self.proposal.is_open_for_voting(),
                    self.proposal.execution_time.get() != UNSET,
                )
            ),
            # set execution time
            self.proposal.execution_time.put(Global.latest_timestamp()),
            # close voting
            self.proposal.vote_close_time.put(Global.latest_timestamp()),
            Approve(),
        )

    def on_set_executed(self):
        """A method for setting a proposal as executed."""
        proposal_app_id = Txn.applications[1]

        return Seq(
            # load proposal
            self.proposal.load_proposal(proposal_app_id),
            # verify proposal is executable
            MagicAssert(self.proposal.is_executable()),
            # executed as true
            self.proposal.executed.put(TRUE),
            Approve(),
        )

    def on_set_quorum_value(self):
        """A method for setting the quorum value."""
        quorum_value = Btoi(Txn.application_args[1])

        return Seq(self.quorum_value.put(quorum_value), Approve())

    def on_set_super_majority(self):
        """A method for setting the super majority."""
        super_majority = Btoi(Txn.application_args[1])

        return Seq(self.super_majority.put(super_majority), Approve())

    def on_set_proposal_duration(self):
        """A method for setting the proposal duration."""
        proposal_duration = Btoi(Txn.application_args[1])

        return Seq(self.proposal_duration.put(proposal_duration), Approve())

    def on_set_proposal_execution_delay(self):
        """A method for setting the proposal execution delay."""
        proposal_execution_delay = Btoi(Txn.application_args[1])

        return Seq(
            self.proposal_execution_delay.put(proposal_execution_delay),
            Approve(),
        )

    def on_set_proposal_creation_delay(self):
        """A method for setting the proposal creation delay."""
        proposal_creation_delay = Btoi(Txn.application_args[1])

        return Seq(
            [
                self.proposal_creation_delay.put(proposal_creation_delay),
                Approve(),
            ]
        )

    # OPT IN / CLOSE OUT

    def on_storage_account_opt_in(self):
        """A method for opting in a storage account."""
        return Seq(
            # verify that the subsequent transaction is a user opt in
            self.verify_txn_is_opt_in_call(
                NEXT_TRANSACTION,
                Global.current_application_id(),
                name=AdminContractStrings.user_opt_in,
            ),
            # verify this transaction is rekeying to the current application
            MagicAssert(
                Txn.rekey_to() == Global.current_application_address()
            ),
            Approve(),
        )

    def on_user_opt_in(self):
        """A method for opting in a user."""
        user_account = Txn.sender()
        storage_account = Gtxn[PREVIOUS_TRANSACTION].sender()

        return Seq(
            # verify that the previous transaction was a storage account opt in
            self.verify_txn_is_opt_in_call(
                PREVIOUS_TRANSACTION,
                Global.current_application_id(),
                name=AdminContractStrings.storage_account_opt_in,
            ),
            # verify that the next transaction is an opt in into the voting escrow with the sender of this transaction being the same person opting in
            self.verify_txn_is_opt_in_call(
                NEXT_TRANSACTION,
                self.voting_escrow_app_id.get(),
                sender=user_account,
            ),
            # set storage account on user local state
            self.user.storage_account.put(storage_account),
            # set user account on storage account local state
            self.user.user_account.put(user_account),
            # set not open to delegation
            self.user.open_to_delegation.put(FALSE),
            # set delegator count to 0
            self.user.delegator_count.put(UNSET),
            # set num proposals opted into to 0
            self.user.num_proposals_opted_into.put(UNSET),
            # set delegating_to to zero address
            self.user.delegating_to.put(Global.zero_address()),
            Approve(),
        )

    def on_proposal_contract_opt_in(self):
        """A method for opting in a proposal contract."""
        proposal_app_id = Global.caller_app_id()
        current_time = Global.latest_timestamp()

        return Seq(
            # verify current_time > last_proposal_time + proposal_creation_delay
            MagicAssert(
                current_time
                > self.proposal_creation_delay.get()
                + self.target_user.last_proposal_creation_time.get()
            ),
            # load proposal
            self.proposal.load_proposal(proposal_app_id),
            # verify sender
            MagicAssert(
                Txn.sender() == self.proposal.proposal_account_address.value()
            ),
            # verify creator is proposal factory
            self.proposal.load_proposal_creator(),
            MagicAssert(
                self.proposal.creator.value()
                == self.proposal_factory_address.get()
            ),
            # initialize proposal state
            self.proposal.app_id.put(proposal_app_id),
            self.proposal.votes_for.put(ZERO_AMOUNT),
            self.proposal.votes_against.put(ZERO_AMOUNT),
            self.proposal.vote_close_time.put(
                current_time + self.proposal_duration.get()
            ),
            self.proposal.rejected.put(FALSE),
            self.proposal.execution_time.put(UNSET),
            self.proposal.executed.put(FALSE),
            self.proposal.canceled_by_emergency_dao.put(FALSE),
            self.target_user.last_proposal_creation_time.put(current_time),
            Approve(),
        )

    def on_user_close_out(self):
        """A method for closing out a user's storage account."""
        return Seq(
            [
                # ensure storage account has closed out of all proposal
                MagicAssert(
                    self.user.num_proposals_opted_into.get() == ZERO_AMOUNT
                ),
                # verify storage account is close out as well
                self.verify_txn_is_close_out_call(
                    NEXT_TRANSACTION,
                    Global.current_application_id(),
                    sender=self.user.storage_account.get(),
                    name=AdminContractStrings.storage_account_close_out,
                ),
                # rekey storage account to user
                send_payment_with_rekey_txn(
                    self.user.storage_account.get(),
                    self.user.storage_account.get(),
                    Int(0),
                    self.user.user_account.get(),
                ),
                Approve(),
            ]
        )

    def on_storage_account_close_out(self):
        """A method for closing out a storage account."""
        return Seq(
            [
                # verify storage account is close out as well
                self.verify_txn_is_close_out_call(
                    PREVIOUS_TRANSACTION,
                    Global.current_application_id(),
                    sender=self.storage_account.user_account.get(),
                    name=AdminContractStrings.user_close_out,
                ),
                Approve(),
            ]
        )

    # USER HELPERS

    def vote(self, user, proposal_app_id, for_or_against):
        """A method for voting on a proposal."""
        # min balance information
        storage_account_min_balance = MinBalance(user.storage_account.get())
        storage_account_min_balance_delta = (
            storage_account_min_balance - self.min_balance_store.load()
        )

        return Seq(
            [
                # load proposal
                self.proposal.load_proposal(proposal_app_id),
                # verify vote is valid (0 or 1)
                MagicAssert(for_or_against <= Int(1)),
                # cache storage account min balance
                self.min_balance_store.store(storage_account_min_balance),
                # validate proposal is open for voting
                MagicAssert(self.proposal.is_open_for_voting()),
                # verify ve bank was updated
                self.verify_update_user_vebank_txn(
                    PREVIOUS_TRANSACTION, user.user_account.get()
                ),
                # verify user ve bank is non zero
                MagicAssert(user.vebank.get() > ZERO_AMOUNT),
                # vote on proposal
                vote_on_proposal_contract(
                    user.storage_account.get(),
                    self.proposal.proposal_app_id_store.load(),
                    for_or_against,
                    user.vebank.get(),
                ),
                # update num proposals opted into
                increment(user.num_proposals_opted_into, Int(1)),
                # update vote totals
                If(for_or_against)
                .Then(increment(self.proposal.votes_for, user.vebank.get()))
                .Else(
                    increment(self.proposal.votes_against, user.vebank.get())
                ),
                # fund storage account proposal min balance
                send_payment_txn(
                    Global.current_application_address(),
                    user.storage_account.get(),
                    storage_account_min_balance_delta,
                ),
            ]
        )

    # USER FUNCTIONS

    def on_update_user_vebank(self):
        """A method for updating a user's vebank."""
        return Seq(
            [
                # update target user vebank
                self.target_user.update_vebank(),
                Approve(),
            ]
        )

    def on_vote(self):
        """A method for voting on a proposal."""
        for_or_against = Btoi(Txn.application_args[1])
        proposal_app_id = Txn.applications[1]

        return Seq(
            [self.vote(self.user, proposal_app_id, for_or_against), Approve()]
        )

    def on_delegated_vote(self):
        """A method for voting on a proposal as a delegatee."""
        proposal_app_id = Txn.applications[1]

        return Seq(
            [
                # load proposal
                self.proposal.load_proposal(proposal_app_id),
                # verify user has delegated
                MagicAssert(
                    self.target_user.delegating_to.get()
                    != Global.zero_address()
                ),
                # load delegatee
                self.delegatee.load_delegatee(
                    self.target_user.delegating_to.get()
                ),
                # verify delegatee is open to delegation
                MagicAssert(self.delegatee.open_to_delegation.get()),
                # load delegatee vote
                self.delegatee.load_proposal_vote(),
                # vote
                self.vote(
                    self.target_user,
                    self.proposal.proposal_app_id_store.load(),
                    self.delegatee.get_proposal_vote(),
                ),
                Approve(),
            ]
        )

    def on_set_open_to_delegation(self):
        """A method for setting a user open to delegation."""
        return Seq(
            # verify user is not currently delegating
            MagicAssert(
                self.user.delegating_to.get() == Global.zero_address()
            ),
            # set user open to delegation
            self.user.open_to_delegation.put(TRUE),
            Approve(),
        )

    def on_set_not_open_to_delegation(self):
        """A method for setting a user not open to delegation."""
        return Seq(
            # set user not open to delegation
            self.user.open_to_delegation.put(FALSE),
            Approve(),
        )

    def on_delegate(self):
        """A method for delegating to a delegatee."""
        delegatee_storage_address = Txn.accounts[2]

        return Seq(
            # verify user has not delegated
            MagicAssert(
                self.user.delegating_to.get() == Global.zero_address()
            ),
            # verify user is not open to delegation
            MagicAssert(self.user.open_to_delegation.get() == FALSE),
            # verify user is not trying to delegate to themselves
            MagicAssert(
                delegatee_storage_address != self.user.storage_account.get()
            ),
            # load delegatee
            self.delegatee.load_delegatee(delegatee_storage_address),
            # verify delegatee is open to delegation
            MagicAssert(self.delegatee.open_to_delegation.get() == TRUE),
            # increment delegatee total
            increment(self.delegatee.delegator_count, Int(1)),
            # set user delegating_to to new delegatee storage address
            self.user.delegating_to.put(delegatee_storage_address),
            Approve(),
        )

    def on_undelegate(self):
        """A method for undelegating from a delegatee."""
        return Seq(
            # verify user has delegated
            MagicAssert(
                self.user.delegating_to.get() != Global.zero_address()
            ),
            # load delegatee
            self.delegatee.load_delegatee(self.user.delegating_to.get()),
            # decrement delegatee total
            decrement(self.delegatee.delegator_count, Int(1)),
            # set user delegating_to to zero address
            self.user.delegating_to.put(Global.zero_address()),
            Approve(),
        )

    def on_validate(self):
        """A method for validating a user's vote."""
        proposal_app_id = Txn.applications[1]

        return Seq(
            [
                # load proposal
                self.proposal.load_proposal(proposal_app_id),
                # verify voting is closed
                MagicAssert(Not(self.proposal.is_open_for_voting())),
                # verify proposal has not already been rejected
                MagicAssert(Not(self.proposal.rejected.get())),
                # verify proposal has not already been accepted
                MagicAssert(self.proposal.execution_time.get() == UNSET),
                # check if vote passed
                If(self.proposal.vote_passed())
                .Then(
                    self.proposal.execution_time.put(
                        Global.latest_timestamp()
                        + self.proposal_execution_delay.get()
                    )
                )  # vote passed
                .Else(self.proposal.rejected.put(TRUE)),  # vote rejected
                Approve(),
            ]
        )

    def on_close_out_from_proposal(self):
        """A method for closing out a user from a proposal."""
        target_storage_account = Txn.accounts[2]
        proposal_app_id = Txn.applications[1]

        # min balance information
        storage_account_min_balance = MinBalance(target_storage_account)
        storage_account_min_balance_delta = (
            self.min_balance_store.load() - storage_account_min_balance
        )

        return Seq(
            [
                # load close out user
                self.close_out_user.load_user(target_storage_account),
                # load proposal
                self.proposal.load_proposal(proposal_app_id),
                # verify proposal is no longer open to voting
                MagicAssert(Not(self.proposal.is_open_for_voting())),
                # cache storage account min balance
                self.min_balance_store.store(storage_account_min_balance),
                # close storage account out of proposal
                close_out_storage_account_from_proposal(
                    target_storage_account,
                    self.proposal.proposal_app_id_store.load(),
                ),
                # decrement num of proposals for user
                decrement(
                    self.close_out_user.num_proposals_opted_into, Int(1)
                ),
                # send the assets back to the admin
                send_payment_txn(
                    target_storage_account,
                    Global.current_application_address(),
                    storage_account_min_balance_delta,
                ),
                Approve(),
            ]
        )

    # APPROVAL PROGRAM

    def approval_program(self):
        """A method for defining the approval program."""
        # sender checks
        sender_is_emergency_dao = (
            Txn.sender() == self.emergency_dao_address.get()
        )
        # check on complete
        is_delete_application = (
            Txn.on_completion() == OnComplete.DeleteApplication
        )
        is_no_op = Txn.on_completion() == OnComplete.NoOp
        is_opt_in = Txn.on_completion() == OnComplete.OptIn
        is_close_out = Txn.on_completion() == OnComplete.CloseOut
        # type of call
        type_of_call = Txn.application_args[0]

        program = Cond(
            [Txn.application_id() == Int(0), self.on_creation()],
            [is_delete_application, Reject()],
            # emergency dao functions
            [
                sender_is_emergency_dao,
                Seq(
                    [
                        MagicAssert(is_no_op),
                        Cond(
                            [
                                type_of_call
                                == Bytes(
                                    AdminContractStrings.set_executed
                                ),
                                self.on_set_executed(),
                            ],
                            [
                                type_of_call
                                == Bytes(
                                    AdminContractStrings.cancel_proposal
                                ),
                                self.on_cancel_proposal(),
                            ],
                            [
                                type_of_call
                                == Bytes(
                                    AdminContractStrings.set_quorum_value
                                ),
                                self.on_set_quorum_value(),
                            ],
                            [
                                type_of_call
                                == Bytes(
                                    AdminContractStrings.set_super_majority
                                ),
                                self.on_set_super_majority(),
                            ],
                            [
                                type_of_call
                                == Bytes(
                                    AdminContractStrings.fast_track_proposal
                                ),
                                self.on_fast_track_proposal(),
                            ],
                            [
                                type_of_call
                                == Bytes(
                                    AdminContractStrings.set_voting_escrow_app_id
                                ),
                                self.on_set_voting_escrow_app_id(),
                            ],
                            [
                                type_of_call
                                == Bytes(
                                    AdminContractStrings.set_proposal_duration
                                ),
                                self.on_set_proposal_duration(),
                            ],
                            [
                                type_of_call
                                == Bytes(
                                    AdminContractStrings.set_proposal_factory_address
                                ),
                                self.on_set_proposal_factory_address(),
                            ],
                            [
                                type_of_call
                                == Bytes(
                                    AdminContractStrings.set_proposal_execution_delay
                                ),
                                self.on_set_proposal_execution_delay(),
                            ],
                            [
                                type_of_call
                                == Bytes(
                                    AdminContractStrings.set_proposal_creation_delay
                                ),
                                self.on_set_proposal_creation_delay(),
                            ],
                        ),
                    ]
                ),
            ],
            # optin functions
            [
                is_opt_in,
                Cond(
                    [
                        type_of_call
                        == Bytes(AdminContractStrings.user_opt_in),
                        self.on_user_opt_in(),
                    ],
                    [
                        type_of_call
                        == Bytes(
                            AdminContractStrings.proposal_contract_opt_in
                        ),
                        self.on_proposal_contract_opt_in(),
                    ],
                    [
                        type_of_call
                        == Bytes(
                            AdminContractStrings.storage_account_opt_in
                        ),
                        self.on_storage_account_opt_in(),
                    ],
                ),
            ],
            # close out function
            [
                is_close_out,
                Cond(
                    [
                        type_of_call
                        == Bytes(AdminContractStrings.user_close_out),
                        self.on_user_close_out(),
                    ],
                    [
                        type_of_call
                        == Bytes(
                            AdminContractStrings.storage_account_close_out
                        ),
                        self.on_storage_account_close_out(),
                    ],
                ),
            ],
            # user functions
            [
                is_no_op,
                Cond(
                    [
                        type_of_call
                        == Bytes(
                            AdminContractStrings.update_user_vebank
                        ),
                        self.on_update_user_vebank(),
                    ],
                    [
                        type_of_call == Bytes(AdminContractStrings.vote),
                        self.on_vote(),
                    ],
                    [
                        type_of_call
                        == Bytes(AdminContractStrings.delegate),
                        self.on_delegate(),
                    ],
                    [
                        type_of_call
                        == Bytes(AdminContractStrings.validate),
                        self.on_validate(),
                    ],
                    [
                        type_of_call
                        == Bytes(AdminContractStrings.undelegate),
                        self.on_undelegate(),
                    ],
                    [
                        type_of_call
                        == Bytes(AdminContractStrings.delegated_vote),
                        self.on_delegated_vote(),
                    ],
                    [
                        type_of_call
                        == Bytes(
                            AdminContractStrings.close_out_from_proposal
                        ),
                        self.on_close_out_from_proposal(),
                    ],
                    [
                        type_of_call
                        == Bytes(
                            AdminContractStrings.set_open_to_delegation
                        ),
                        self.on_set_open_to_delegation(),
                    ],
                    [
                        type_of_call
                        == Bytes(
                            AdminContractStrings.set_not_open_to_delegation
                        ),
                        self.on_set_not_open_to_delegation(),
                    ],
                ),
            ],
        )

        return program

    def clear_state_program(self):
        return Approve()
