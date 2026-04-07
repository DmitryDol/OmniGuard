import logging

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # PostgreSQL config
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "admin"
    DB_NAME: str = "omniguard_db"

    # Socket server config
    SOCKET_SERVER_IP: str = "0.0.0.0"
    SOCKET_SERVER_PORT: int = 8000

    # Email notifications config
    SMTP_SENDER_EMAIL: str = ""
    SMTP_SENDER_PASSWORD: str = ""
    SMTP_RECEIVER_EMAIL: str = ""

    # Video recording config
    VIDEO_STORAGE_PATH: str = "data/videos/"
    VIDEO_LIFETIME_HOURS: int = 48

    # Detection config
    DETECTION_EVERY_N_FRAMES: int = 5
    DETECTION_CONFIDENCE_THRESHOLD: float = 0.5
    DETECTION_MODEL: str = "l"  # nano, small, medium, large
    ZONE_COLOR: tuple[int, int, int] = (0, 0, 255)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def configure_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        datefmt="%Y-%m-%d %H:%M:%S",
        format="[%(asctime)s.%(msecs)03d] %(module)10s:%(lineno)-3d %(levelname)-7s - %(message)s",
    )


settings = Settings()
