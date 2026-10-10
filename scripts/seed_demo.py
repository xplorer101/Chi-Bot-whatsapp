"""Seed a demo business so the webhook can be tested locally.

Usage: python scripts/seed_demo.py
Set DEMO_PHONE_NUMBER_ID to match the phone_number_id you send in test payloads.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.db import SessionLocal
from app.models import FAQ, Business, CatalogItem

PHONE_NUMBER_ID = os.getenv("DEMO_PHONE_NUMBER_ID", "1234567890")

FAQS = [
    (
        "Do you deliver?",
        "Yes, we deliver within Lagos (Ikeja, Yaba, Surulere). Delivery is 1500 naira.",
        "delivery",
    ),
    ("What are your opening hours?", "We are open Monday to Saturday, 9am to 6pm.", "hours"),
    (
        "How do I pay?",
        (
            "You can pay by bank transfer to Mama Ngozi Foodstuff, GTBank 0123456789, "
            "or pay on delivery."
        ),
        "payment",
    ),
]

ITEMS = [
    ("Jollof Rice (party pack)", "Serves 8-10 people.", 2500000, "pack"),
    ("Chin Chin", "Crunchy fried snack.", 150000, "pack"),
    ("Palm Oil", "Fresh red palm oil.", 350000, "5 litres"),
]


async def main() -> None:
    async with SessionLocal() as session:
        business = (
            await session.execute(
                select(Business).where(Business.slug == "mama-ngozi")
            )
        ).scalar_one_or_none()

        if business is None:
            business = Business(
                name="Mama Ngozi Foodstuff",
                slug="mama-ngozi",
                description="Nigerian food and provisions, cooked fresh daily.",
                location="12 Adeola Odeku Street, Victoria Island, Lagos",
                opening_hours={
                    "mon_sat": "09:00-18:00",
                    "sun": "Closed",
                },
                delivery_areas=["Ikeja", "Yaba", "Surulere"],
                payment_details={
                    "bank": "GTBank",
                    "account_name": "Mama Ngozi Foodstuff",
                    "account_number": "0123456789",
                },
                whatsapp_phone_number_id=PHONE_NUMBER_ID,
            )
            session.add(business)
            await session.flush()
        else:
            business.whatsapp_phone_number_id = PHONE_NUMBER_ID

        existing_faqs = {
            f.question
            for f in (
                await session.execute(
                    select(FAQ).where(FAQ.business_id == business.id)
                )
            ).scalars()
        }
        for question, answer, category in FAQS:
            if question not in existing_faqs:
                session.add(
                    FAQ(
                        business_id=business.id,
                        question=question,
                        answer=answer,
                        category=category,
                    )
                )

        existing_items = {
            i.name
            for i in (
                await session.execute(
                    select(CatalogItem).where(CatalogItem.business_id == business.id)
                )
            ).scalars()
        }
        for name, description, price_kobo, unit in ITEMS:
            if name not in existing_items:
                session.add(
                    CatalogItem(
                        business_id=business.id,
                        name=name,
                        description=description,
                        price_kobo=price_kobo,
                        unit=unit,
                    )
                )

        await session.commit()
        print(f"seeded business slug={business.slug} id={business.id}")
        print(f"whatsapp_phone_number_id={business.whatsapp_phone_number_id}")
        print("This phone_number_id is what test webhook payloads must use.")


if __name__ == "__main__":
    asyncio.run(main())