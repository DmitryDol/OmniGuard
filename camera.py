import cv2


class Camera:
    def __init__(
        self,
        id: int,
        camera_ip_and_port,
        name: str,
        fps: int,
        resolution: tuple[int, int] = (1280, 720),
        is_file: bool = False,
    ) -> None:
        self.name = name
        self.ip = camera_ip_and_port
        self.id = id
        self.camera_fps = fps
        self.resolution = resolution
        self.is_file = is_file
        self._open()

    def _open(self):
        if isinstance(self.ip, int):
            # Local webcam / USB camera (Camo Studio, etc.)
            self.cap = cv2.VideoCapture(self.ip)
        elif self.is_file:
            # Video file — no FFMPEG backend override, use default
            self.cap = cv2.VideoCapture(self.ip)
        else:
            # IP / RTSP / HTTP camera
            self.cap = cv2.VideoCapture(self.ip, cv2.CAP_FFMPEG)

    def connect_to_camera(self):
        self._open()

    def read(self):
        """Read next frame. Loops video files; reconnects on camera failure."""
        if not self.cap.isOpened():
            self.connect_to_camera()

        ret, frame = self.cap.read()

        if not ret:
            if self.is_file:
                # Loop video file from the beginning
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
            else:
                self.connect_to_camera()
                ret, frame = self.cap.read()

        if frame is None:
            # Return blank frame to avoid crashes
            import numpy as np
            frame = np.zeros((*self.resolution[::-1], 3), dtype="uint8")

        return cv2.resize(frame, self.resolution)