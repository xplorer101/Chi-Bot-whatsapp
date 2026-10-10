"""String constants for enum-like columns.

Plain strings (not Postgres ENUM) so changing the set of allowed values
never requires a schema migration.
"""

BUSINESS_STATUS_ACTIVE: str = "active"
BUSINESS_STATUS_PAUSED: str = "paused"

CONVERSATION_STATUS_ACTIVE: str = "active"
CONVERSATION_STATUS_HUMAN: str = "human"
CONVERSATION_STATUS_CLOSED: str = "closed"

MESSAGE_ROLE_CUSTOMER: str = "customer"
MESSAGE_ROLE_BOT: str = "bot"
MESSAGE_ROLE_OWNER: str = "owner"
MESSAGE_ROLE_SYSTEM: str = "system"

ORDER_STATUS_PENDING: str = "pending"
ORDER_STATUS_CONFIRMED: str = "confirmed"
ORDER_STATUS_PAID: str = "paid"
ORDER_STATUS_DELIVERED: str = "delivered"
ORDER_STATUS_CANCELLED: str = "cancelled"

BOOKING_STATUS_PENDING: str = "pending"
BOOKING_STATUS_CONFIRMED: str = "confirmed"
BOOKING_STATUS_COMPLETED: str = "completed"
BOOKING_STATUS_CANCELLED: str = "cancelled"

HANDOFF_STATUS_OPEN: str = "open"
HANDOFF_STATUS_RESOLVED: str = "resolved"

WEBHOOK_STATUS_RECEIVED: str = "received"
WEBHOOK_STATUS_DONE: str = "done"
WEBHOOK_STATUS_ERROR: str = "error"