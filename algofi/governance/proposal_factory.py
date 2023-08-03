"""Contains the ProposalFactory class, which is the contract that users interact with to create proposals."""

from pyteal import *

from algofi.governance.constants import *
from algofi.governance.contract_strings import (
    AlgofiProposalFactoryStrings,
    AlgofiProposalStrings,
    AlgofiVotingEscrowStrings,
)
from algofi.governance.subroutines import *
from algofi.utils.wrapped_var import *


# Subroutines
@Subroutine(TealType.none)
def create_proposal_from_template_and_optin(
    approval_program_proposal,
    clear_state_program_proposal,
    admin_app_id,
    title,
    link,
    proposer,
    proposer_admin_storage_account,
):
    """Creates a proposal from the proposal template and opts it into the admin contract."""
    proposal_app_id_scratch = ScratchVar(TealType.uint64)
    proposal_app_id = Gitxn[0].created_application_id()
    proposal_app_address = AppParam.address(proposal_app_id)

    return Seq(
        # creating the proposal
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.approval_program: approval_program_proposal,
                TxnField.clear_state_program: clear_state_program_proposal,
                TxnField.global_num_byte_slices: GLOBAL_BYTES_PROPOSAL_CONTRACT,
                TxnField.global_num_uints: GLOBAL_INTS_PROPOSAL_CONTRACT,
                TxnField.local_num_byte_slices: LOCAL_BYTES_PROPOSAL_CONTRACT,
                TxnField.local_num_uints: LOCAL_INTS_PROPOSAL_CONTRACT,
                TxnField.application_args: [title, link],
                TxnField.fee: Int(0),
            }
        ),
        InnerTxnBuilder.Submit(),
        # make sure the proposal was created correctly
        MagicAssert(proposal_app_id > Int(0)),
        proposal_app_id_scratch.store(proposal_app_id),
        # getting the address so that we can determine minimum balances
        proposal_app_address,
        MagicAssert(proposal_app_address.hasValue()),
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.Payment,
                TxnField.amount: MIN_BALANCE_PROPOSAL,
                TxnField.receiver: proposal_app_address.value(),
                TxnField.fee: Int(0),
            }
        ),
        InnerTxnBuilder.Next(),
        # opt the proposal contract into the admin
        InnerTxnBuilder.SetFields(
            {
                TxnField.type_enum: TxnType.ApplicationCall,
                TxnField.application_id: proposal_app_id_scratch.load(),
                TxnField.application_args: [
                    Bytes(AlgofiProposalStrings.opt_into_admin)
                ],
                TxnField.applications: [admin_app_id],
                TxnField.accounts: [proposer, proposer_admin_storage_account],
                TxnField.fee: Int(0),
            }
        ),
        InnerTxnBuilder.Submit(),
    )


class User:
    """Defines a user of the proposal factory."""

    def __init__(self, user_account, voting_escrow_app_id):
        self.account = user_account

        # USER STATE
        self.current_ve_bank = WrappedVar(
            AlgofiVotingEscrowStrings.user_amount_vebank,
            LOCAL_EX_VAR,
            user_account,
            voting_escrow_app_id,
        ).get()

    def load_ve_bank(self):
        """Loads the user's ve bank."""
        return Seq(
            [
                self.current_ve_bank,
                MagicAssert(self.current_ve_bank.hasValue()),
            ]
        )


class ProposalFactory:
    """Defines the proposal factory contract."""

    def __init__(self):
        # SCRATCH VARS
        self.min_balance_store = ScratchVar(
            TealType.uint64, AlgofiProposalFactoryScratchSlots.min_balance
        )

        # GLOBAL BYTES
        self.dao_address = WrappedVar(
            AlgofiProposalFactoryStrings.dao_address, GLOBAL_VAR
        )
        self.emergency_dao_address = WrappedVar(
            AlgofiProposalFactoryStrings.emergency_dao_address, GLOBAL_VAR
        )

        # GLOBAL INTS
        self.gov_token = WrappedVar(
            AlgofiProposalFactoryStrings.gov_token, GLOBAL_VAR
        )
        self.voting_escrow_app_id = WrappedVar(
            AlgofiProposalFactoryStrings.voting_escrow_app_id, GLOBAL_VAR
        )
        self.proposal_template = WrappedVar(
            AlgofiProposalFactoryStrings.proposal_template, GLOBAL_VAR
        )
        self.minimum_ve_bank_to_propose = WrappedVar(
            AlgofiProposalFactoryStrings.minimum_ve_bank_to_propose, GLOBAL_VAR
        )
        self.admin_app_id = WrappedVar(
            AlgofiProposalFactoryStrings.admin_app_id, GLOBAL_VAR
        )

        # DERIVED VALUES
        self.proposal_approval_program = AppParam.approvalProgram(
            self.proposal_template.get()
        )
        self.proposal_clear_state_program = AppParam.clearStateProgram(
            self.proposal_template.get()
        )

        # HELPER CLASSES
        self.user = User(
            Txn.accounts[1],
            voting_escrow_app_id=self.voting_escrow_app_id.get(),
        )

    # HELPER FUNCTIONS

    def load_proposal_template(self):
        """Loads the proposal template."""
        return Seq(
            [
                self.proposal_approval_program,
                self.proposal_clear_state_program,
                MagicAssert(self.proposal_approval_program.hasValue()),
                MagicAssert(self.proposal_clear_state_program.hasValue()),
            ]
        )

    # CREATION

    def on_creation(self):
        """Called when the contract is created."""
        minimum_ve_bank_to_propose = Btoi(Txn.application_args[0])
        dao_address = Txn.accounts[1]
        emergency_dao_address = Txn.accounts[2]
        voting_escrow_app_id = Txn.applications[1]
        proposal_template = Txn.applications[2]
        admin_app_id = Txn.applications[3]

        return Seq(
            [
                # setting dao address
                self.dao_address.put(dao_address),
                # setting emergency dao address
                self.emergency_dao_address.put(emergency_dao_address),
                # setting minimum ve bank to propose
                self.minimum_ve_bank_to_propose.put(
                    minimum_ve_bank_to_propose
                ),
                # setting voting escrow app id
                self.voting_escrow_app_id.put(voting_escrow_app_id),
                # setting proposal template
                self.proposal_template.put(proposal_template),
                # setting admin app id
                self.admin_app_id.put(admin_app_id),
                Approve(),
            ]
        )

    # ADMIN

    def on_set_voting_escrow_app_id(self):
        """Sets the voting escrow app id."""
        voting_escrow_app_id = Txn.applications[1]

        return Seq(
            self.voting_escrow_app_id.put(voting_escrow_app_id), Approve()
        )

    def on_set_admin_app_id(self):
        """Sets the admin app id."""
        admin_app_id = Txn.applications[1]

        return Seq(self.admin_app_id.put(admin_app_id), Approve())

    def on_set_proposal_template(self):
        """Sets the proposal template."""
        proposal_template = Txn.applications[1]

        return Seq(self.proposal_template.put(proposal_template), Approve())

    def on_set_minimum_ve_bank_to_propose(self):
        """Sets the minimum ve bank to propose."""
        new_minimum_ve_bank_to_propose = Btoi(Txn.application_args[1])

        return Seq(
            self.minimum_ve_bank_to_propose.put(
                new_minimum_ve_bank_to_propose
            ),
            Approve(),
        )

    # USER FUNCTIONS

    def on_create_proposal(self):
        """Creates a proposal."""
        # application args
        title = Txn.application_args[1]
        link = Txn.application_args[2]

        # user admin storage account
        user_admin_storage_account = Txn.accounts[2]

        # min balance state
        min_balance = MinBalance(Global.current_application_address())
        min_balance_delta = min_balance - self.min_balance_store.load()

        return Seq(
            [
                # check previous transaction was to this app with user for ledger compatibility
                verify_txn_is_named_no_op_application_call(
                    PREVIOUS_TRANSACTION,
                    AlgofiProposalFactoryStrings.validate_user_account,
                ),
                # verify sender of previous txn is the foreign account
                verify_txn_account(PREVIOUS_TRANSACTION, 0, self.user.account),
                # sending the update ve bank transaction
                send_update_vebank_txn(
                    self.user.account, self.voting_escrow_app_id.get()
                ),
                # load user ve bank
                self.user.load_ve_bank(),
                # load proposal template
                self.load_proposal_template(),
                # verify user has sufficient ve bank
                MagicAssert(
                    self.user.current_ve_bank.value()
                    > self.minimum_ve_bank_to_propose.get()
                ),
                # cache min balance
                self.min_balance_store.store(min_balance),
                # creating the proposal
                create_proposal_from_template_and_optin(
                    self.proposal_approval_program.value(),
                    self.proposal_clear_state_program.value(),
                    self.admin_app_id.get(),
                    title,
                    link,
                    self.user.account,
                    user_admin_storage_account,
                ),
                # verify min balance was funded
                verify_txn_is_payment_and_amount(
                    TWO_PREVIOUS_TRANSACTION,
                    Global.current_application_address(),
                    min_balance_delta + MIN_BALANCE_PROPOSAL,
                ),
                Approve(),
            ]
        )

    # APPROVAL

    def approval_program(self):
        """The proposal factory approval program."""

        # sender checks
        sender_is_dao = Or(
            Txn.sender() == self.dao_address.get(),
            Txn.sender() == self.emergency_dao_address.get(),
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
            [is_opt_in, Reject()],
            [is_close_out, Reject()],
            # dao functions
            [
                sender_is_dao,
                Cond(
                    [
                        is_no_op,
                        Cond(
                            [
                                type_of_call
                                == Bytes(
                                    AlgofiProposalFactoryStrings.set_proposal_template
                                ),
                                self.on_set_proposal_template(),
                            ],
                            [
                                type_of_call
                                == Bytes(
                                    AlgofiProposalFactoryStrings.set_voting_escrow_app_id
                                ),
                                self.on_set_voting_escrow_app_id(),
                            ],
                            [
                                type_of_call
                                == Bytes(
                                    AlgofiProposalFactoryStrings.set_admin_app_id
                                ),
                                self.on_set_admin_app_id(),
                            ],
                            [
                                type_of_call
                                == Bytes(
                                    AlgofiProposalFactoryStrings.set_minimum_ve_bank_to_propose
                                ),
                                self.on_set_minimum_ve_bank_to_propose(),
                            ],
                        ),
                    ]
                ),
            ],
            # user functions
            [
                is_no_op,
                Cond(
                    [
                        type_of_call
                        == Bytes(
                            AlgofiProposalFactoryStrings.validate_user_account
                        ),
                        Approve(),
                    ],
                    [
                        type_of_call
                        == Bytes(AlgofiProposalFactoryStrings.create_proposal),
                        self.on_create_proposal(),
                    ],
                ),
            ],
        )

        return program

    def clear_state_program(self):
        return Approve()
