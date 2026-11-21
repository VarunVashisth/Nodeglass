from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Repository(Base):
    __tablename__ = "repositories"
    id: Mapped[str] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]


class SourceFile(Base):
    __tablename__ = "files"
    id: Mapped[str] = mapped_column(primary_key=True)
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str]
    language: Mapped[str]
    content_hash: Mapped[str]
    size: Mapped[int]
    modified: Mapped[float]
    status: Mapped[str]
    errors: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (Index("ix_file_repo_path", "repository_id", "path", unique=True),)


class Entity(Base):
    """Normalized symbols, imports, references, calls and statements.

    Essential ownership/scope/target links are relational; syntax details use JSON.
    """

    __tablename__ = "entities"
    id: Mapped[str] = mapped_column(primary_key=True)
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[str] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(Text)
    qualified_name: Mapped[str]
    scope_id: Mapped[str | None] = mapped_column(
        ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_id: Mapped[str | None] = mapped_column(
        ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("files.id", ondelete="SET NULL"), nullable=True
    )
    resolution: Mapped[str] = mapped_column(default="unresolved")
    start_byte: Mapped[int]
    end_byte: Mapped[int]
    line: Mapped[int]
    column: Mapped[int]
    end_line: Mapped[int]
    end_column: Mapped[int]
    details: Mapped[dict] = mapped_column(JSON, default=dict)
