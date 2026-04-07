"""SQLAlchemy ORM models for OmniGuard."""

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CameraModel(Base):
    """Represents a camera source (IP stream, webcam, or file)."""

    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_string: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    fps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)

    zones: Mapped[list["ZoneModel"]] = relationship(
        "ZoneModel", back_populates="camera", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Camera id={self.id} name={self.name!r} src={self.connection_string!r}>"


class ZoneModel(Base):
    """Represents a detection zone polygon attached to a camera."""

    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False
    )
    coordinates: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)

    camera: Mapped["CameraModel"] = relationship("CameraModel", back_populates="zones")

    def __repr__(self) -> str:
        return f"<Zone id={self.id} camera_id={self.camera_id} name={self.name!r}>"
