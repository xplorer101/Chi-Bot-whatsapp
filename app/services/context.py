from sqlalchemy import select

from app.models import FAQ, CatalogItem, Service


async def load_faqs(session, business_id: str) -> list[FAQ]:
    stmt = (
        select(FAQ)
        .where(FAQ.business_id == business_id)
        .order_by(FAQ.position, FAQ.created_at)
    )
    return list((await session.execute(stmt)).scalars())


async def load_items(session, business_id: str) -> list[CatalogItem]:
    stmt = (
        select(CatalogItem)
        .where(CatalogItem.business_id == business_id)
        .order_by(CatalogItem.created_at)
    )
    return list((await session.execute(stmt)).scalars())


async def load_services(session, business_id: str) -> list[Service]:
    stmt = (
        select(Service)
        .where(Service.business_id == business_id, Service.active.is_(True))
        .order_by(Service.created_at)
    )
    return list((await session.execute(stmt)).scalars())