from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, event, String, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from app.core.config import settings, ROOT

(ROOT / 'data').mkdir(exist_ok=True)
engine = create_engine(settings.database_url, connect_args={'check_same_thread': False} if settings.database_url.startswith('sqlite') else {})
if settings.database_url.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
SessionLocal = sessionmaker(engine, expire_on_commit=False)

def now():
    return datetime.now(timezone.utc).isoformat()

class Base(DeclarativeBase):
    pass

class Conversation(Base):
    __tablename__ = 'conversations'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[str] = mapped_column(default=now)
    status: Mapped[str] = mapped_column(default='active')

class Turn(Base):
    __tablename__ = 'turns'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id'), index=True)
    created_at: Mapped[str] = mapped_column(default=now)
    data: Mapped[dict] = mapped_column(JSON)

class Escalation(Base):
    __tablename__ = 'escalations'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id'), index=True)
    turn_id: Mapped[str] = mapped_column(ForeignKey('turns.id'))
    created_at: Mapped[str] = mapped_column(default=now)
    status: Mapped[str] = mapped_column(default='Open')
    packet: Mapped[dict] = mapped_column(JSON)

class KnowledgeDocument(Base):
    __tablename__ = 'knowledge_documents'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)

class EvaluationRun(Base):
    __tablename__ = 'evaluation_runs'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[str] = mapped_column(default=now)
    data: Mapped[dict] = mapped_column(JSON)

# v2 additions are additive; legacy conversations and audit JSON remain intact.
class CallSession(Base):
    __tablename__='call_sessions'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid4()))
    conversation_id:Mapped[str]=mapped_column(ForeignKey('conversations.id'),unique=True)
    provider_call_id:Mapped[str|None]=mapped_column(String,unique=True,nullable=True)
    created_at:Mapped[str]=mapped_column(default=now)
    ended_at:Mapped[str|None]=mapped_column(nullable=True)
    state:Mapped[str]=mapped_column(default='RINGING')
    mode:Mapped[str]=mapped_column(default='MOCK_CALL_MODE')
    customer_id:Mapped[str|None]=mapped_column(nullable=True)
    authentication_status:Mapped[str]=mapped_column(default='UNVERIFIED')
    data:Mapped[dict]=mapped_column(JSON,default=dict)

class CallEvent(Base):
    __tablename__='call_events'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid4()))
    call_id:Mapped[str]=mapped_column(ForeignKey('call_sessions.id'),index=True)
    created_at:Mapped[str]=mapped_column(default=now)
    event_type:Mapped[str]=mapped_column(String)
    data:Mapped[dict]=mapped_column(JSON,default=dict)

class CustomerDemoProfile(Base):
    __tablename__='demo_customers'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    created_at:Mapped[str]=mapped_column(default=now)
    data:Mapped[dict]=mapped_column(JSON)

class AuthenticationEvent(Base):
    __tablename__='authentication_events'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid4()))
    call_id:Mapped[str]=mapped_column(ForeignKey('call_sessions.id'))
    created_at:Mapped[str]=mapped_column(default=now)
    status:Mapped[str]=mapped_column(String)
    data:Mapped[dict]=mapped_column(JSON,default=dict)

class KnowledgeGap(Base):
    __tablename__='knowledge_gaps'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    created_at:Mapped[str]=mapped_column(default=now)
    updated_at:Mapped[str]=mapped_column(default=now)
    frequency:Mapped[int]=mapped_column(default=1)
    status:Mapped[str]=mapped_column(default='Open')
    data:Mapped[dict]=mapped_column(JSON)

class AdminAudit(Base):
    __tablename__='admin_audit'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=lambda:str(uuid4()))
    created_at:Mapped[str]=mapped_column(default=now)
    action:Mapped[str]=mapped_column(String)
    data:Mapped[dict]=mapped_column(JSON)
