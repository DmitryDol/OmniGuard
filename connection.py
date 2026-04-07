import logging

# On Windows, Qt's QPSQL plugin requires libpq.dll from a PostgreSQL client
# installation. Install PostgreSQL 17 client tools and ensure its bin directory
# (e.g. C:\Program Files\PostgreSQL\17\bin) is in the system PATH.
# See README.md for installation instructions.

import psycopg2
from collections import defaultdict

from PySide6.QtCore import Qt
from PySide6.QtSql import QSqlDatabase, QSqlQuery, QSqlQueryModel
from PySide6.QtWidgets import QApplication, QTableView

from camera import Camera
from config import configure_logging, settings

configure_logging()
logger = logging.getLogger(__name__)


def ensure_database_exists(host, port, user, password, db_name):
    """Create the target database if it doesn't exist.

    Uses psycopg2 because CREATE DATABASE must run outside a transaction,
    which Qt SQL does not support.
    """
    conn = None
    try:
        conn = psycopg2.connect(
            host=host, port=port, user=user, password=password, dbname="postgres"
        )
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
            )
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{db_name}"')
                logger.info("Database '%s' created.", db_name)
            else:
                logger.debug("Database '%s' already exists.", db_name)
    except Exception as e:
        logger.error("Failed to ensure database exists: %s", e)
        raise
    finally:
        if conn:
            conn.close()


# TODO : заменить плейсхолдеры на $число
class Data:
    def __init__(
        self, db_type="QPSQL", host=None, db_name=None, user=None, password=None
    ) -> None:
        super(Data, self).__init__()
        self.db_name = db_name or settings.DB_NAME
        _host = host or settings.DB_HOST
        _user = user or settings.DB_USER
        _password = password or settings.DB_PASSWORD
        _port = settings.DB_PORT

        ensure_database_exists(_host, _port, _user, _password, self.db_name)

        self.db = QSqlDatabase.addDatabase(db_type)
        self.db.setHostName(_host)
        self.db.setPort(_port)
        self.db.setDatabaseName(str(self.db_name))
        self.db.setUserName(_user)
        self.db.setPassword(_password)

        if not self.db.open():
            raise Exception(f"Cannot open database: {self.db.lastError().text()}")


    def get_zones(self):
        query = QSqlQuery(self.db)
        if not query.exec("select * from zones"):
            raise Exception(f"Query error: {query.lastError().text()}")
        query.exec("SELECT camera_id, coordinates FROM zones")

        zones_with_camera_id = defaultdict(list)
        while query.next():
            camera_id = query.value("camera_id")
            coordinates = query.value("coordinates")
            coordinates = list(map(int, coordinates.split()))
            zones_with_camera_id[camera_id].append(coordinates)

        return zones_with_camera_id

    def get_zones_by_camera_id(self, camera_id):
        return self.get_zones()[camera_id]

    def get_cameras(self) -> list[Camera]:
        query = QSqlQuery(self.db)
        if not query.exec("select * from cameras"):
            raise Exception(f"Query error: {query.lastError().text()}")

        cameras = []
        while query.next():
            id = int(query.value("id"))
            connection_string = query.value("connection_string")
            if connection_string.isdigit():
                connection_string = int(connection_string)
            name = query.value("name")
            fps = query.value("fps")
            resolution = tuple(map(int, query.value("resolution").split()))

            cameras.append(Camera(id, connection_string, name, fps, resolution))

        return cameras

    def get_camera(self, id) -> Camera:
        query = QSqlQuery(self.db)
        if not query.exec(f"select * from cameras where id={id};"):
            raise Exception(f"Query error: {query.lastError().text()}")

        if not query.next():
            raise Exception("No record found")

        connection_string = query.value("connection_string")
        if connection_string.isdigit():
            connection_string = int(connection_string)
        name = query.value("name")
        fps = query.value("fps")
        resolution = tuple(map(int, query.value("resolution").split()))

        return Camera(connection_string, name, fps, resolution)

    def execute_query(self, query_text, params=None):
        query = QSqlQuery(self.db)
        query.prepare(query_text)

        if params:
            if isinstance(params, dict):
                for key, value in params.items():
                    query.bindValue(key, value)
            else:
                for i, value in enumerate(params):
                    query.bindValue(f":{i + 1}", value)

        if not query.exec():
            raise Exception(f"Query error: {query.lastError().text()}")

    def exec_query_list(self, query_text, params=None):
        query = QSqlQuery(self.db)
        query.prepare(query_text)
        if params:
            for i, param in enumerate(params, start=0):
                query.bindValue(i, param)

        if not query.exec():
            raise Exception(f"Query error: {query.lastError().text()}")

    def add_cam_list(self, connection_string, fps, resolution, name=None):
        self.exec_query_list(
            """INSERT INTO cameras (connection_string, name, fps, resolution) VALUES ($1, $2, $3, $4);
        """,
            [connection_string, name, fps, resolution],
        )

    def add_cam_exec(self, connection_string, fps, resolution, name=None):
        query = QSqlQuery(self.db)
        if not query.exec(
            f"INSERT INTO cameras (connection_string, name, fps, resolution) VALUES ('{connection_string}', '{name}', {fps}, '{resolution}')"
        ):
            raise Exception(f"Query error: {query.lastError().text()}")

    def create_tables(self):
        query = QSqlQuery(self.db)
        if not query.exec("""
            CREATE TABLE IF NOT EXISTS cameras (
                id SERIAL PRIMARY KEY,
                connection_string TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                fps INTEGER,
                resolution TEXT
            );
            """):
            raise Exception(f"Failed to create cameras table: {query.lastError().text()}")

        if not query.exec("""
            CREATE TABLE IF NOT EXISTS zones (
                id SERIAL PRIMARY KEY,
                camera_id INTEGER REFERENCES cameras(id) ON DELETE CASCADE,
                coordinates TEXT NOT NULL,
                name TEXT
            );
            """):
            raise Exception(f"Failed to create zones table: {query.lastError().text()}")

    def add_camera(self, connection_string, fps, resolution, name=None):
        self.execute_query(
            """
        INSERT INTO cameras (connection_string, name, fps, resolution)
        VALUES (:connection_string, :name, :fps, :resolution);
        """,
            {
                ":connection_string": connection_string,
                ":name": name,
                ":fps": fps,
                ":resolution": resolution,
            },
        )

    def add_zone_exec(self, camera_id: int, coordinates: str, name: str = None):
        query = QSqlQuery(self.db)
        if not query.exec(
            f"""INSERT INTO zones (camera_id, coordinates, name) VALUES (\'{camera_id}\', \'{coordinates}\', \'{name}\');"""
        ):
            raise Exception(f"Query error: {query.lastError().text()}")

    def add_zone(self, camera_id: int, coordinates: str, name: str = None):
        self.execute_query(
            """
        INSERT INTO zones (camera_id, coordinates, name)
        VALUES (:camera_id, :coordinates, :name);
        """,
            {":camera_id": camera_id, ":coordinates": coordinates, ":name": name},
        )

    def update_camera(
        self, camera_id, new_connection_string, new_fps, new_resolution, new_name=None
    ):
        self.execute_query(
            """
        UPDATE cameras
        SET connection_string = COALESCE(:connection_string, connection_string),
            name = COALESCE(:name, name),
            fps = COALESCE(:fps, fps),
            resolution = COALESCE(:resolution, resolution)
        WHERE id = :camera_id;
        """,
            {
                ":connection_string": new_connection_string,
                ":name": new_name,
                ":fps": new_fps,
                ":resolution": new_resolution,
                ":camera_id": camera_id,
            },
        )

    def update_zone(
        self, zone_id, new_camera_id=None, new_coordinates=None, new_name=None
    ):
        self.execute_query(
            """
        UPDATE zones
        SET camera_id = COALESCE(:camera_id, camera_id),
            coordinates = COALESCE(:coordinates, coordinates),
            name = COALESCE(:name, name)
        WHERE id = :zone_id;
        """,
            {
                ":camera_id": new_camera_id,
                ":coordinates": new_coordinates,
                ":name": new_name,
                ":zone_id": zone_id,
            },
        )

    def delete_camera(self, camera_id):
        self.execute_query(
            """
        DELETE FROM cameras
        WHERE id = :camera_id;
        """,
            {":camera_id": camera_id},
        )

    def delete_zone(self, zone_id):
        self.execute_query(
            """
        DELETE FROM zones
        WHERE id = :zone_id;
        """,
            {":zone_id": zone_id},
        )

    def delete_zone_by_camera_id(self, camera_id):
        self.execute_query(
            """
        DELETE FROM zones
        WHERE camera_id = :camera_id;
        """,
            {":camera_id": camera_id},
        )
