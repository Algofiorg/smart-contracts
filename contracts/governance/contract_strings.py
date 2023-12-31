"""Defines the strings used in the governance contracts."""


class VotingEscrowStrings:
    admin_contract_app_id = "acid"
    asset_id = "ai"
    claim = "c"
    dao_address = "da"
    emergency_dao_address = "eda"
    extend_lock = "el"
    increase_lock_amount = "ila"
    lock = "l"
    set_admin_contract_app_id = "sacai"
    set_gov_token_id = "sgti"
    total_locked = "tl"
    total_vebank = "tv"
    update_vebank_data = "uvb"
    user_amount_locked = "aal"
    user_amount_vebank = "aav"
    user_boost_multiplier = "bm"
    user_last_update_time = "ulut"
    user_lock_duration = "uld"
    user_lock_start_time = "ulst"


class ProposalStrings:
    create_transaction = "ct"
    creator_of_proposal = "cop"
    for_or_against = "foa"
    link = "l"
    opt_into_admin = "oia"
    proposer = "p"
    template_id = "ti"
    title = "t"
    user_close_out = "uco"
    user_vote = "uv"
    voting_amount = "vamt"


class AdminContractStrings:
    admin = "a"
    cancel_proposal = "cp"
    canceled_by_emergency_dao = "cbed"
    close_out_from_proposal = "cofp"
    delegate = "d"
    delegated_vote = "devo"
    delegating_to = "dt"
    delegator_count = "dc"
    emergency_dao_address = "eda"
    emergency_multisig = "em"
    execute = "e"
    executed = "ex"
    execution_time = "ext"
    fast_track_proposal = "ftp"
    last_proposal_creation_time = "lpct"
    num_proposals_opted_into = "npoi"
    open_to_delegation = "otd"
    proposal_app_id = "pai"
    proposal_contract_opt_in = "coi"
    proposal_creation_delay = "pcd"
    proposal_duration = "pd"
    proposal_execution_delay = "ped"
    proposal_factory_address = "pfa"
    proposal_rejected = "pr"
    quorum_value = "qv"
    set_executed = "sex"
    set_not_open_to_delegation = "snotd"
    set_open_to_delegation = "sotd"
    set_proposal_creation_delay = "spcd"
    set_proposal_duration = "spd"
    set_proposal_execution_delay = "sped"
    set_proposal_factory_address = "spfi"
    set_quorum_value = "sqv"
    set_super_majority = "ssm"
    set_voting_escrow_app_id = "sveai"
    storage_account = "sa"
    storage_account_close_out = "saco"
    storage_account_opt_in = "saoi"
    super_majority = "sm"
    undelegate = "ud"
    update_user_vebank = "uuv"
    user_account = "ua"
    user_close_out = "uco"
    user_opt_in = "uoi"
    validate = "va"
    vebank = "vb"
    vote = "vo"
    vote_close_time = "vct"
    votes_against = "va"
    votes_for = "vf"
    voting_escrow_app_id = "veai"


class ProposalFactoryStrings:
    admin = "a"
    admin_app_id = "aai"
    create_proposal = "cp"
    dao_address = "da"
    emergency_dao_address = "eda"
    gov_token = "gt"
    minimum_ve_bank_to_propose = "mvbtp"
    proposal_template = "pt"
    set_admin_app_id = "saai"
    set_minimum_ve_bank_to_propose = "smvbtp"
    set_proposal_template = "spt"
    set_voting_escrow_app_id = "sveai"
    validate_user_account = "vua"
    voting_escrow_app_id = "veai"
