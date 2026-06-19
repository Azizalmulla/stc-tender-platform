from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, with_loader_criteria, Session
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


@event.listens_for(Session, "do_orm_execute")
def _apply_tender_visibility(execute_state):
    """Transparently restrict Tender SELECTs to the statuses allowed for the
    current request (public => clean only). No-op when no request context set
    the contextvar (internal scrape/reprocess/scripts), so those keep full access.
    """
    if not execute_state.is_select or execute_state.is_column_load or execute_state.is_relationship_load:
        return
    # Imported lazily to avoid a circular import at module load time.
    from app.api.visibility import current_statuses
    from app.models.tender import Tender

    statuses = current_statuses()
    if statuses is None:
        return
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            Tender,
            Tender.extraction_quality_status.in_(statuses),
            include_aliases=True,
        )
    )


def get_db():
    """Dependency for FastAPI endpoints"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
