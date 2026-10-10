"""Talk to the ChiBot AI over the terminal - no WhatsApp needed.

Usage:
  python scripts/chat_cli.py                    # chat as 2348011223344
  python scripts/chat_cli.py --phone 2348099887766
  python scripts/chat_cli.py --reset            # start a fresh conversation
  python scripts/chat_cli.py --business mama-ngozi

Set ANTHROPIC_API_KEY to use the real model, or AI_MOCK=true for the
offline deterministic stand-in.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.ai.agent import maybe_refresh_summary, respond
from app.db import SessionLocal
from app.models import Business, Conversation
from app.models.enums import CONVERSATION_STATUS_ACTIVE


async def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--business", default="mama-ngozi")
    parser.add_argument("--phone", default="2348011223344")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    async with SessionLocal() as session:
        business = (
            await session.execute(
                select(Business).where(Business.slug == args.business)
            )
        ).scalar_one_or_none()
        if business is None:
            print(f"no business with slug '{args.business}'. Run scripts/seed_demo.py first.")
            return

        if args.reset:
            existing = (
                await session.execute(
                    select(Conversation).where(
                        Conversation.business_id == business.id,
                        Conversation.customer_phone == args.phone,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.status = CONVERSATION_STATUS_ACTIVE
                existing.summary = None
                await session.commit()
                print("conversation reset")

        conversation = (
            await session.execute(
                select(Conversation).where(
                    Conversation.business_id == business.id,
                    Conversation.customer_phone == args.phone,
                )
            )
        ).scalar_one_or_none()
        if conversation is None:
            conversation = Conversation(
                business_id=business.id,
                customer_phone=args.phone,
                status=CONVERSATION_STATUS_ACTIVE,
            )
            session.add(conversation)
            await session.flush()

        print(f"ChiBot CLI - business '{business.name}' as {args.phone}")
        print("Type your message (Ctrl-D or 'exit' to quit).\n")
        while True:
            try:
                line = input("you> ")
            except EOFError:
                break
            if not line.strip():
                continue
            if line.strip().lower() in {"exit", "quit"}:
                break
            reply = await respond(session, business, conversation, line)
            await maybe_refresh_summary(session, business, conversation)
            await session.commit()
            print(f"bot> {reply}")


if __name__ == "__main__":
    asyncio.run(run())