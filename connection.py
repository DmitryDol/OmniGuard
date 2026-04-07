"""Data access layer using SQLAlchemy ORM.

Replaces the old QSqlQuery-based implementation.
The public interface of the ``Data`` class is preserved so that callers
in main.py require minimal changes.
"""

import logging
from collections import defaultdict

from camera import Camera
from config import configure_logging
from database import get_session, init_db
from db_models import CameraModel, ZoneModel

configure_logging()
logger = logging.getLogger(__name__)


class Data:
    """Repository for Camera and Zone persistence.

    Uses SQLAlchemy ORM sessions internally.  Each method opens a session,
    performs the operation inside a transaction, and commits (or rolls back)
    before returning — keeping sessions short-lived and thread-safe.
    """

    def __init__(self) -> None:
        init_db()
        logger.info("Data layer ready.")

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def create_tables(self) -> None:
        """No-op: tables are created automatically by init_db() via SQLAlchemy.

        Kept for backward compatibility with existing callers.
        """

    # ------------------------------------------------------------------
    # Camera queries
    # ------------------------------------------------------------------

    def get_cameras(self) -> list[Camera]:
        with get_session() as session:
            rows = session.query(CameraModel).all()
            return [self._to_camera(r) for r in rows]

    def get_camera(self, camera_id: int) -> Camera:
        with get_session() as session:
            row = session.get(CameraModel, int(camera_id))
            if row is None:
                raise ValueError(f"Camera with id={camera_id} not found.")
            return self._to_camera(row)

    def add_camera(
        self, connection_string: str, fps: int, resolution: str, name: str | None = None
    ) -> None:
        with get_session() as session:
            cam = CameraModel(
                connection_string=str(connection_string),
                name=name,
                fps=int(fps),
                resolution=resolution,
            )
            session.add(cam)
            session.commit()
            logger.info("Camera added: %r", cam)

    # Alias kept for backward compatibility with old callers in main.py
    def add_cam_exec(
        self, connection_string: str, fps: int, resolution: str, name: str | None = None
    ) -> None:
        self.add_camera(connection_string, fps, resolution, name)

    def update_camera(
        self,
        camera_id: int,
        new_connection_string: str,
        new_fps: int,
        new_resolution: str,
        new_name: str | None = None,
    ) -> None:
        with get_session() as session:
            cam = session.get(CameraModel, int(camera_id))
            if cam is None:
                raise ValueError(f"Camera with id={camera_id} not found.")
            if new_connection_string is not None:
                cam.connection_string = str(new_connection_string)
            if new_name is not None:
                cam.name = new_name
            if new_fps is not None:
                cam.fps = int(new_fps)
            if new_resolution is not None:
                cam.resolution = new_resolution
            session.commit()
            logger.info("Camera %s updated.", camera_id)

    def delete_camera(self, camera_id: int) -> None:
        with get_session() as session:
            cam = session.get(CameraModel, int(camera_id))
            if cam is not None:
                session.delete(cam)
                session.commit()
                logger.info("Camera %s deleted.", camera_id)

    # ------------------------------------------------------------------
    # Zone queries
    # ------------------------------------------------------------------

    def get_zones(self) -> dict:
        """Return {camera_id: [[x, y, ...], ...]} mapping."""
        with get_session() as session:
            rows = session.query(ZoneModel).all()
            zones: dict = defaultdict(list)
            for row in rows:
                coords = list(map(int, row.coordinates.split()))
                zones[row.camera_id].append(coords)
            return zones

    def get_zones_by_camera_id(self, camera_id: int) -> list:
        return self.get_zones()[camera_id]

    def add_zone(
        self, camera_id: int, coordinates: str, name: str | None = None
    ) -> None:
        with get_session() as session:
            zone = ZoneModel(camera_id=int(camera_id), coordinates=coordinates, name=name)
            session.add(zone)
            session.commit()
            logger.debug("Zone added for camera %d.", camera_id)

    # Alias kept for backward compatibility
    def add_zone_exec(
        self, camera_id: int, coordinates: str, name: str | None = None
    ) -> None:
        self.add_zone(camera_id, coordinates, name)

    def update_zone(
        self,
        zone_id: int,
        new_camera_id: int | None = None,
        new_coordinates: str | None = None,
        new_name: str | None = None,
    ) -> None:
        with get_session() as session:
            zone = session.get(ZoneModel, int(zone_id))
            if zone is None:
                raise ValueError(f"Zone with id={zone_id} not found.")
            if new_camera_id is not None:
                zone.camera_id = int(new_camera_id)
            if new_coordinates is not None:
                zone.coordinates = new_coordinates
            if new_name is not None:
                zone.name = new_name
            session.commit()

    def delete_zone(self, zone_id: int) -> None:
        with get_session() as session:
            zone = session.get(ZoneModel, int(zone_id))
            if zone is not None:
                session.delete(zone)
                session.commit()

    def delete_zone_by_camera_id(self, camera_id: int) -> None:
        with get_session() as session:
            session.query(ZoneModel).filter(
                ZoneModel.camera_id == int(camera_id)
            ).delete()
            session.commit()
            logger.debug("All zones for camera %d deleted.", camera_id)

    # ------------------------------------------------------------------
    # For view_data in main.py — returns raw dicts for table display
    # ------------------------------------------------------------------

    def get_cameras_as_dicts(self) -> list[dict]:
        """Return list of camera dicts for display in a QStandardItemModel."""
        with get_session() as session:
            rows = session.query(CameraModel).all()
            return [
                {
                    "id": r.id,
                    "connection_string": r.connection_string,
                    "name": r.name or "",
                    "fps": r.fps,
                    "resolution": r.resolution or "",
                }
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_camera(row: CameraModel) -> Camera:
        """Convert a CameraModel ORM row to a Camera domain object."""
        src = row.connection_string
        is_file = False
        # If the stored value is a digit string, treat it as a webcam index
        if isinstance(src, str):
            if src.isdigit():
                src = int(src)
            elif not src.lower().startswith(("http://", "https://", "rtsp://")):
                is_file = True

        resolution = tuple(map(int, row.resolution.split())) if row.resolution else (1280, 720)
        return Camera(
            id=row.id,
            camera_ip_and_port=src,
            name=row.name or "",
            fps=row.fps or 30,
            resolution=resolution,
            is_file=is_file,
        )
