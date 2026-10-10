"""Seed a demo barbershop (services + weekly hours) for testing bookings.

Usage: python scripts/seed_booking_demo.py
Set DEMO_BOOKING_PHONE_NUMBER_ID to match the phone_number_id you send in payloads.
"""
import asyncio
import os
import sys
from datetime import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.db import SessionLocal
from app.models import FAQ, Business, BusinessHours, Service

PHONE_NUMBER_ID = os.getenv("DEMO_BOOKING_PHONE_NUMBER_ID", "5550001111")

SERVICES = [
    ("Haircut", "Clean cut with clippers or scissors.", 300000, 30),
    ("Beard trim", "Line-up and beard shaping.", 150000, 15),
    ("Haircut + beard", "Full cut and beard trim.", 400000, 45),
]

# Monday(1) to Saturday(6): 09:00-13:00 and 14:00-18:00 (lunch break 13-14).
HOURS = [(wd, time(9, 0), time(13, 0)) for wd in range(1, 7)] + [
    (wd, time(14, 0), time(18, 0)) for wd in range(1, 7)
]

FAQS = [
    ("Where are you located?", "We are at 5 Bode Thomas Street, Surulere, Lagos."),
    ("Do you take walk-ins?", "Yes, but booking ahead is faster."),
]


async def main() -> None:
    async with SessionLocal() as session:
        business = (
            await session.execute(
                select(Business).where(Business.slug == "fresh-cuts")
            )
        ).scalar_one_or_none()

        if business is None:
            business = Business(
                name="Fresh Cuts Barbershop",
                slug="fresh-cuts",
                description="Neighbourhood barbershop in Surulere, Lagos.",
                location="5 Bode Thomas Street, Surulere, Lagos",
                opening_hours={"mon_sat": "09:00-18:00", "sun": "Closed"},
                payment_details={"cash": "Pay at the shop", "transfer": "0123456789"},
                whatsapp_phone_number_id=PHONE_NUMBER_ID,
                booking_min_notice_minutes=60,
                booking_max_days_ahead=21,
                booking_slot_interval_minutes=30,
                booking_requires_approval=True,
                booking_cancellation_window_minutes=120,
            )
            session.add(business)
            await session.flush()

        existing_services = {
            s.name
            for s in (
                await session.execute(
                    select(Service).where(Service.business_id == business.id)
                )
            ).scalars()
        }
        for name, description, price, duration in SERVICES:
            if name not in existing_services:
                session.add(
                    Service(
                        business_id=business.id,
                        name=name,
                        description=description,
                        price_kobo=price,
                        duration_minutes=duration,
                    )
                )

        if not (
            await session.execute(
                select(BusinessHours).where(BusinessHours.business_id == business.id)
            )
        ).first():
            for weekday, start, end in HOURS:
                session.add(
                    BusinessHours(
                        business_id=business.id,
                        weekday=weekday,
                        start_time=start,
                        end_time=end,
                    )
                )

        existing_faqs = {
            f.question
            for f in (
                await session.execute(
                    select(FAQ).where(FAQ.business_id == business.id)
                )
            ).scalars()
        }
        for question, answer in FAQS:
            if question not in existing_faqs:
                session.add(
                    FAQ(
                        business_id=business.id,
                        question=question,
                        answer=answer,
                        position=0,
                    )
                )

        await session.commit()
        print(f"seeded business slug={business.slug} id={business.id}")
        print(f"whatsapp_phone_number_id={business.whatsapp_phone_number_id}")


if __name__ == "__main__":
    asyncio.run(main())
