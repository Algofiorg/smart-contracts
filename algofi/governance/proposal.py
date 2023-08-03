"""Module containing the logic for proposals."""

from pyteal import *

from algofi.governance.contract_strings import (
    AlgofiAdminContractStrings,
    AlgofiProposalStrings,
)
from algofi.governance.subroutines import *
from algofi.utils.wrapped_var import *


# Subroutines
@Subroutine(TealType.none)
def opt_proposal_contract_into_admin(
    admin_app_id, proposer, proposer_admin_storage_account
):
    """Defines a sub-routine for opting a proposal contract into the admin contract."""
    return Seq(
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.sender: Global.current_application_address(),
                TxnField.application_id: admin_app_id,
                TxnField.on_completion: OnComplete.OptIn,
                TxnField.application_args: [
                    Bytes(AlgofiAdminContractStrings.proposal_contract_opt_in)
                ],
                TxnField.applications: [],
                TxnField.accounts: [proposer, proposer_admin_storage_account],
                TxnField.fee: Int(0),
            }
        ),
        InnerTxnBuilder.Submit(),
    )


class Proposal:
    """Defines the proposal contract."""

    def __init__(self, admin_app_id):
        # ADMIN APP ID
        self.admin_app_id = Int(admin_app_id)

        # GLOBAL BYTES
        self.title = WrappedVar(AlgofiProposalStrings.title, GLOBAL_VAR)
        self.link = WrappedVar(AlgofiProposalStrings.link, GLOBAL_VAR)

        # LOCAL INTS
        self.for_or_against = WrappedVar(
            AlgofiProposalStrings.for_or_against, LOCAL_VAR, Int(0)
        )
        self.voting_amount = WrappedVar(
            AlgofiProposalStrings.voting_amount, LOCAL_VAR, Int(0)
        )

    # CREATE

    def on_creation(self):
        """Creates the proposal contract."""
        title = Txn.application_args[0]
        link = Txn.application_args[1]

        return Seq(self.title.put(title), self.link.put(link), Approve())

    # ADMIN

    def on_opt_into_admin(self):
        """Opts the proposal contract into the admin contract."""
        proposer = Txn.accounts[1]
        proposer_admin_storage_account = Txn.accounts[2]

        return Seq(
            # verify sender is creator
            MagicAssert(Txn.sender() == Global.creator_address()),
            # opt into admin
            opt_proposal_contract_into_admin(
                self.admin_app_id, proposer, proposer_admin_storage_account
            ),
            Approve(),
        )

    # OPT IN / CLOSE OUT

    def on_user_vote(self):
        """Stores the user's vote."""
        for_or_against = Btoi(Txn.application_args[1])
        voting_amount = Btoi(Txn.application_args[2])

        return Seq(
            # verify caller is admin
            MagicAssert(Global.caller_app_id() == self.admin_app_id),
            # store proposal state
            self.for_or_against.put(for_or_against),
            self.voting_amount.put(voting_amount),
            Approve(),
        )

    def on_user_close_out(self):
        """Calls close out."""
        return Seq(
            # verify caller is admin
            MagicAssert(Global.caller_app_id() == self.admin_app_id),
            Approve(),
        )

    # APPROVAL

    def approval_program(self):
        """The approval program for the proposal contract."""
        # check on complete
        is_update_application = (
            Txn.on_completion() == OnComplete.UpdateApplication
        )
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
            [is_update_application, Reject()],
            [
                is_opt_in,
                Cond(
                    [
                        type_of_call == Bytes(AlgofiProposalStrings.user_vote),
                        self.on_user_vote(),
                    ]
                ),
            ],
            [
                is_no_op,
                Cond(
                    [
                        type_of_call
                        == Bytes(AlgofiProposalStrings.opt_into_admin),
                        self.on_opt_into_admin(),
                    ]
                ),
            ],
            [
                is_close_out,
                Cond(
                    [
                        type_of_call
                        == Bytes(AlgofiProposalStrings.user_close_out),
                        self.on_user_close_out(),
                    ]
                ),
            ],
        )

        return program

    def clear_state_program(self):
        return Approve()
