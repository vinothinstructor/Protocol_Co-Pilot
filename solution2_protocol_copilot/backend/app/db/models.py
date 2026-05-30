from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, func
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector
from app.config import settings

Base = declarative_base()


class AmendmentPattern(Base):
    __tablename__ = "amendment_patterns"
    id = Column(Integer, primary_key=True)
    pattern_id = Column(String(32), unique=True, nullable=False)
    category = Column(String(64), nullable=False)
    example_clause = Column(Text, nullable=False)
    amendment = Column(Text, nullable=False)
    root_cause = Column(Text, nullable=False)
    therapeutic_areas = Column(JSON, nullable=False)
    source = Column(String(255), default="Synthetic, modeled on Tufts CSDD amendment categories")
    embedding = Column(Vector(settings.embedding_dim), nullable=True)


class ClauseHistory(Base):
    __tablename__ = "clause_history"
    id = Column(Integer, primary_key=True)
    protocol_id = Column(String(64), nullable=False)
    clause_id = Column(String(64), nullable=False)
    action = Column(String(32), nullable=False)
    original_text = Column(Text)
    new_text = Column(Text)
    risk_before = Column(Integer)
    risk_after = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ProtocolVersion(Base):
    __tablename__ = "protocol_versions"
    id = Column(Integer, primary_key=True)
    protocol_id = Column(String(64), nullable=False)
    version = Column(String(16), nullable=False)
    document = Column(JSON, nullable=False)
    overall_risk = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
