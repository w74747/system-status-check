import os
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError

app = FastAPI(title="System Status Check API", version="1.0.0")

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./health_audit.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class HealthLog(Base):
    __tablename__ = "health_logs"

    id = Column(Integer, primary_key=True, index=True)
    checked_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(50), nullable=False)


# Create audit table if it does not exist
try:
    Base.metadata.create_all(bind=engine)
except OperationalError:
    pass


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: str


def check_dependencies() -> bool:
    """
    Verify critical dependencies are reachable.
    Returns True if all dependencies are available.
    """
    # Check primary database connectivity
    try:
        db = SessionLocal()
        try:
            db.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        finally:
            db.close()
    except Exception:
        return False
    return True


def write_audit_log(health_status: str) -> None:
    """Persist an audit entry; failures here must not break the response."""
    try:
        db = SessionLocal()
        try:
            log = HealthLog(
                checked_at=datetime.now(timezone.utc),
                status=health_status,
            )
            db.add(log)
            db.commit()
        finally:
            db.close()
    except Exception:
        pass  # Audit logging is best-effort


@app.get("/api/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
def health_check() -> JSONResponse:
    timestamp = datetime.now(timezone.utc).isoformat()

    dependencies_ok = check_dependencies()

    if not dependencies_ok:
        write_audit_log("unavailable")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unavailable",
                "service": "system-status-check",
                "timestamp": timestamp,
            },
        )

    write_audit_log("operational")

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "operational",
            "service": "system-status-check",
            "timestamp": timestamp,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
