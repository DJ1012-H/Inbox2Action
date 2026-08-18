from __future__ import annotations

from inbox2action.gmail import GmailMessage
from inbox2action.stage3.contracts import EmailEnvelope


def gmail_message_to_envelope(
    message: GmailMessage,
    *,
    account_id: str,
) -> EmailEnvelope:
    """Map bounded Gmail content to the existing provider-neutral envelope."""

    return EmailEnvelope(
        account_id=account_id,
        message_id=message.message_id,
        provider_thread_id=message.thread_id or None,
        from_address=message.from_address or None,
        reply_to=message.reply_to or None,
        subject=message.subject,
        body=message.body,
        html=message.html,
        received_at=message.date or None,
    )
