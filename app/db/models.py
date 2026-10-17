from datetime import datetime
from decimal import Decimal
from enum import Enum
from sqlalchemy import Integer, DateTime, String, ForeignKey, UniqueConstraint, Numeric
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped, relationship


class Base(DeclarativeBase):
    pass

class Status(Enum):
    pending = "pending"
    running = "running"
    found = "found"
    failed = "failed"
    not_found = "not_found"
    canceled = "canceled"

class Store(Enum):
    dns = "dns"
    citilink = "citilink"
    onlinetrade = "onlinetrade"

class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime,
                                                 default=datetime.now)
    total_products: Mapped[int] = mapped_column()


    products: Mapped[list["Product"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan"
    )

class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer,
                                        ForeignKey("jobs.id"))
    query: Mapped[str] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer)


    job: Mapped["Job"] = relationship(
        back_populates="products"
    )
    searches: Mapped[list["Search"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )

class Search(Base):
    __tablename__ = "searches"
    __table_args__ = (
        UniqueConstraint("product_id", "store"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer,
                                            ForeignKey("products.id"))
    store: Mapped[Store] = mapped_column()
    status: Mapped[Status] = mapped_column(default=Status.pending)
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column()
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


    product: Mapped["Product"] = relationship(
        back_populates="searches",
    )
    offers: Mapped[list["Offer"]] = relationship(
        back_populates="search",
        cascade="all, delete-orphan",
    )

class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    search_id: Mapped[int] = mapped_column(Integer,
                                           ForeignKey("searches.id"))
    name: Mapped[str] = mapped_column(String)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    url: Mapped[str] = mapped_column(String)


    search: Mapped["Search"] = relationship(
        back_populates="offers",
    )