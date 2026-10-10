import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://chibot@127.0.0.1:5432/chibot_test"
)
os.environ.setdefault("AI_MOCK", "true")
os.environ.setdefault("WHATSAPP_DRY_RUN", "true")

import pytest_asyncio
from sqlalchemy import delete

from app.db import SessionLocal, engine
from app.models import Business, CatalogItem, Conversation
from app.models.enums import CONVERSATION_STATUS_ACTIVE


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine_loop():
    """Each test runs on its own event loop; drop pooled connections so the
    async engine is never tied to a closed loop."""
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def tenant():
    sid = str(uuid.uuid4())[:8]
    async with SessionLocal() as session:
        business = Business(
            name=f"Test Biz {sid}",
            slug=f"test-biz-{sid}",
            whatsapp_phone_number_id=f"99{sid}",
        )
        session.add(business)
        await session.flush()
        kunu = CatalogItem(
            business_id=business.id, name="Kunu Drink", price_kobo=100000, stock_qty=5
        )
        jollof = CatalogItem(
            business_id=business.id, name="Jollof Rice", price_kobo=250000, stock_qty=None
        )
        old = CatalogItem(
            business_id=business.id,
            name="Old Stock",
            price_kobo=50000,
            stock_qty=0,
            available=False,
        )
        session.add_all([kunu, jollof, old])
        await session.flush()
        phone = f"23480{sid}"
        convo = Conversation(
            business_id=business.id,
            customer_phone=phone,
            status=CONVERSATION_STATUS_ACTIVE,
        )
        session.add(convo)
        await session.commit()
        data = {
            "business_id": business.id,
            "kunu": kunu.id,
            "jollof": jollof.id,
            "old": old.id,
            "other_business_id": None,
            "phone": phone,
            "conversation_id": convo.id,
        }

    yield data

    async with SessionLocal() as session:
        await session.execute(delete(Business).where(Business.id == data["business_id"]))
        await session.commit()


@pytest_asyncio.fixture
async def other_tenant():
    sid = str(uuid.uuid4())[:8]
    async with SessionLocal() as session:
        business = Business(
            name=f"Other Biz {sid}",
            slug=f"other-biz-{sid}",
            whatsapp_phone_number_id=f"88{sid}",
        )
        session.add(business)
        await session.flush()
        item = CatalogItem(
            business_id=business.id, name="Foreign Item", price_kobo=999000
        )
        session.add(item)
        await session.commit()
        data = {"business_id": business.id, "item": item.id}

    yield data

    async with SessionLocal() as session:
        await session.execute(delete(Business).where(Business.id == data["business_id"]))
        await session.commit()