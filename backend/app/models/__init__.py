"""Model exports for SQLAlchemy/SQLModel metadata discovery."""

from app.models.activity_events import ActivityEvent
from app.models.agents import Agent
from app.models.approval_task_links import ApprovalTaskLink
from app.models.approvals import Approval
from app.models.board_group_memory import BoardGroupMemory
from app.models.board_groups import BoardGroup
from app.models.board_memory import BoardMemory
from app.models.board_onboarding import BoardOnboardingSession
from app.models.board_webhook_payloads import BoardWebhookPayload
from app.models.board_webhooks import BoardWebhook
from app.models.boards import Board
from app.models.bookkeeping import (
    BkClient,
    BkExpense,
    BkInvoice,
    BkInvoiceLine,
    BkJob,
    BkPlacement,
    BkTimesheet,
    BkTransaction,
    BkWorker,
)
from app.models.budget import BudgetConfig, DailyAgentSpend
from app.models.crypto_positions import CryptoPosition
from app.models.crypto_trade_proposals import CryptoTradeProposal
from app.models.email_accounts import EmailAccount
from app.models.email_attachments import EmailAttachment
from app.models.email_messages import EmailMessage
from app.models.exchange_accounts import ExchangeAccount
from app.models.gateways import Gateway
from app.models.generated_documents import GeneratedDocument
from app.models.org_config import OrgConfigData, OrgOnboardingStep
from app.models.org_contacts import OrgContact
from app.models.organization_board_access import OrganizationBoardAccess
from app.models.organization_domains import OrganizationDomain
from app.models.organization_invite_board_access import OrganizationInviteBoardAccess
from app.models.organization_invites import OrganizationInvite
from app.models.organization_members import OrganizationMember
from app.models.organizations import Organization
from app.models.paper_bets import PaperBet
from app.models.paper_trading import PaperPortfolio, PaperPosition, PaperTrade
from app.models.pentest_scans import PentestScanRecord
from app.models.polymarket_positions import PolymarketPosition
from app.models.polymarket_risk_config import PolymarketRiskConfig
from app.models.polymarket_wallets import PolymarketWallet
from app.models.skills import GatewayInstalledSkill, MarketplaceSkill, SkillPack
from app.models.tag_assignments import TagAssignment
from app.models.tags import Tag
from app.models.task_custom_fields import (
    BoardTaskCustomField,
    TaskCustomFieldDefinition,
    TaskCustomFieldValue,
)
from app.models.task_dependencies import TaskDependency
from app.models.task_fingerprints import TaskFingerprint
from app.models.tasks import Task
from app.models.trade_history import TradeHistory
from app.models.trade_proposals import TradeProposal
from app.models.tx_audit_records import TxAuditRecord
from app.models.users import User
from app.models.vector_memory import VectorMemory
from app.models.watchlist import WatchlistItem

__all__ = [
    "ActivityEvent",
    "Agent",
    "ApprovalTaskLink",
    "Approval",
    "BoardGroupMemory",
    "BoardWebhook",
    "BoardWebhookPayload",
    "BoardMemory",
    "BoardOnboardingSession",
    "BoardGroup",
    "Board",
    "BudgetConfig",
    "DailyAgentSpend",
    "CryptoPosition",
    "CryptoTradeProposal",
    "EmailAccount",
    "ExchangeAccount",
    "EmailAttachment",
    "EmailMessage",
    "GeneratedDocument",
    "Gateway",
    "PolymarketPosition",
    "PolymarketRiskConfig",
    "PolymarketWallet",
    "TradeHistory",
    "TradeProposal",
    "GatewayInstalledSkill",
    "MarketplaceSkill",
    "SkillPack",
    "Organization",
    "BoardTaskCustomField",
    "TaskCustomFieldDefinition",
    "TaskCustomFieldValue",
    "OrganizationDomain",
    "OrganizationMember",
    "OrganizationBoardAccess",
    "OrganizationInvite",
    "OrganizationInviteBoardAccess",
    "TaskDependency",
    "Task",
    "TaskFingerprint",
    "Tag",
    "TagAssignment",
    "User",
    "PaperBet",
    "PentestScanRecord",
    "TxAuditRecord",
    "PaperPortfolio",
    "PaperPosition",
    "PaperTrade",
    "WatchlistItem",
    "BkClient",
    "BkExpense",
    "BkInvoice",
    "BkInvoiceLine",
    "BkJob",
    "BkPlacement",
    "BkTimesheet",
    "BkTransaction",
    "BkWorker",
    "OrgConfigData",
    "OrgContact",
    "OrgOnboardingStep",
    "VectorMemory",
]
