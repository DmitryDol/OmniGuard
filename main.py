import logging
import socket
import struct
import sys
import time

import cv2
import numpy as np
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QApplication, QMainWindow

from camera import Camera
from config import configure_logging, settings
from connection import Data
from email_server import Email_server
from out_of_date_video_cleaner import Cleaner
from personDetector import Detector
from UIFiles.ui_add_edit_camera import Ui_AddEditCamera
from UIFiles.ui_cameras_list import Ui_CamerasWindow
from UIFiles.ui_change_email import Ui_EmailPathChanging
from UIFiles.ui_main_window import Ui_MainWindow
from source_selection_dialog import SourceSelectionDialog
from zone_redactor import ZoneRedactorWindow

configure_logging()
logger = logging.getLogger(__name__)


class VideoThread(QThread):
    change_pixmap_signal = Signal(np.ndarray)

    def __init__(
        self,
        detector: Detector,
        is_active_detector: bool,
        activate_detector_every_n_frames: int,
        video_path: str = None,
        server_ip: str = None,
        server_port: int = None,
    ):
        super().__init__()
        # socket for sending video to the client
        self.server_ip = server_ip or settings.SOCKET_SERVER_IP
        self.server_port1 = server_port or settings.SOCKET_SERVER_PORT
        self.server_port2 = self.server_port1 + 1
        self.client_socket1 = None
        self.client_socket2 = None
        self.client_connected = False

        # path to store videos
        self.video_path = video_path or settings.VIDEO_STORAGE_PATH

        # person detector based on YOLOv5 nano
        self.detector = detector
        # cv2 video capture
        self.camera = None
        self.cameras: list[Camera] = []
        self.zones: dict = {}
        # is it necessary to detect on the current frame or not
        self.is_active_detector = is_active_detector
        # is used to speed up performance, responsible for how many frames will be skipped between detections
        self.activate_detector_every_n_frames = activate_detector_every_n_frames

        # email info. wiil be changed when user input this data in settings
        self.reciever_to_alert = None
        self.sender_server = None

        # annotators that are used in skipped frames
        self.box_annotator = None
        self.detections = None
        self.annotators = None

        self.start_detection_time = None
        self.end_detection_time = None
        self.video_writer = None
        self.running = False

    def set_cameras(self, cameras: list[Camera]):
        self.cameras = cameras

    def set_zones(self, zones):
        self.zones = zones

    def set_camera(self, camera: Camera):
        self.camera = camera

    def set_email_settings(self, sender: Email_server, reciever_email: str) -> None:
        """
        save emails to follow up alert sending
        """
        self.sender_server = sender
        self.reciever_to_alert = reciever_email

    def set_active_detector(self, is_active: bool) -> None:
        """
        Set is_active_detector to is_active value
        """
        self.is_active_detector = is_active

    def set_video_path(self, path):
        self.video_path = path

    def save(self, frame: np.ndarray) -> None:
        """
        add frame to video.
        File name is created based on the start_detection_time and end_detection_time
        args:
            frame: cv2 video capture frame
        """
        if self.video_writer is not None:
            self.video_writer.write(frame)

    def realise(self) -> None:
        """
        end of detection, save file to file_path
        """
        if self.video_writer is not None:
            self.video_writer.release()
        # cv2.destroyAllWindows()

    def send_frame(self, frame, client_socket: socket.socket) -> bool:
        if frame is None or getattr(frame, "size", 0) == 0:
            return True
        _, buffer = cv2.imencode(".jpg", frame)
        data = buffer.tobytes()
        size = len(data)
        client_socket.settimeout(0.5)
        try:
            client_socket.sendall(struct.pack(">L", size) + data)
            return True
        except Exception as e:
            client_socket.close()
            if self.client_connected:
                logger.info("Mobile client disconnected: %s", e)
            self.client_connected = False
            return False

    def stop(self):
        self.running = False

    def bind_server(self, port):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.server_ip, port))
        server_socket.listen(1)
        return server_socket

    def run(self):
        import threading

        # Start socket servers in background daemon threads so they never
        # block the main video-processing loop.
        def accept_clients():
            try:
                server_socket1 = self.bind_server(self.server_port1)
                server_socket2 = self.bind_server(self.server_port2)
                logger.info(
                    "Listening for mobile client on %s:%d and %d",
                    self.server_ip, self.server_port1, self.server_port2,
                )
                while self.running:
                    try:
                        self.client_socket1, _ = server_socket1.accept()
                        self.client_socket2, _ = server_socket2.accept()
                        self.client_connected = True
                        logger.info("Mobile client connected")
                    except OSError:
                        break
            except Exception as e:
                logger.warning("Socket server error (mobile streaming disabled): %s", e)

        socket_thread = threading.Thread(target=accept_clients, daemon=True)
        socket_thread.start()

        last_send = 0
        frame_num = 0
        NOTIFICATION_FREQ = 300
        self.running = True

        # FPS measurement
        fps_frame_count = 0
        fps_start_time = time.time()
        current_fps = 0.0

        while self.running:
            if not isinstance(self.camera, Camera) or not self.camera.cap.isOpened():
                time.sleep(0.05)
                continue

            main_frame = self.camera.read()
            was_human_detected_in_zone = []
            oth_frames = []
            oth_box_annotators = []
            oth_annotators = []
            oth_detections = []

            for camera in self.cameras:
                if camera is not self.camera:
                    oth_frames.append(camera.read())
            frame_num += 1

            # ── Detection ────────────────────────────────────────────────
            if (
                self.is_active_detector
                and frame_num == self.activate_detector_every_n_frames
            ):
                frame_num = 0
                self.detector.change_zone(self.zones[self.camera.id])
                (
                    was_detected_in_zone,
                    main_frame,
                    self.box_annotator,
                    self.annotators,
                    self.detections,
                ) = self.detector.detect(main_frame)
                was_human_detected_in_zone.append(was_detected_in_zone)
                for i, frame in enumerate(oth_frames):
                    if self.zones[self.cameras[i].id]:
                        self.detector.change_zone(self.zones[self.cameras[i].id])
                        (
                            was_detected_in_zone,
                            frame,
                            temp_box_annotator,
                            temp_annotators,
                            temp_detections,
                        ) = self.detector.detect(frame)
                        was_human_detected_in_zone.append(was_detected_in_zone)
                        oth_box_annotators.append(temp_box_annotator)
                        oth_annotators.append(temp_annotators)
                        oth_detections.append(temp_detections)

                if any(was_human_detected_in_zone):
                    if self.video_writer is None:
                        self.start_detection_time = time.strftime(
                            "%d.%m.%Y_%H-%M-%S", time.localtime()
                        )
                        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                        output_filename = (
                            f"{self.video_path}{self.start_detection_time}.avi"
                        )
                        self.video_writer = cv2.VideoWriter(
                            output_filename,
                            fourcc,
                            self.camera.camera_fps,
                            self.camera.resolution,
                        )
                    self.save(main_frame)

                    if (
                        self.sender_server
                        and self.reciever_to_alert
                        and time.time() - last_send > NOTIFICATION_FREQ
                    ):
                        self.sender_server.send_email(self.reciever_to_alert, main_frame)
                        last_send = time.time()

            elif (
                self.is_active_detector
                and self.annotators
                and self.annotators[0]
                and self.box_annotator
            ):
                # Annotate skipped frames with previous detection results
                main_frame = self.box_annotator.annotate(
                    scene=main_frame, detections=self.detections
                )
                for annotator in self.annotators:
                    main_frame = annotator.annotate(scene=main_frame)
                self.save(main_frame)

            else:
                if self.video_writer is not None:
                    self.realise()
                    self.video_writer = None
                frame_num = self.activate_detector_every_n_frames - 1

            # ── Measure and overlay real FPS ─────────────────────────────
            fps_frame_count += 1
            elapsed = time.time() - fps_start_time
            if elapsed >= 1.0:
                current_fps = fps_frame_count / elapsed
                fps_frame_count = 0
                fps_start_time = time.time()

            cv2.putText(
                main_frame,
                f"FPS: {current_fps:.1f}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

            self.change_pixmap_signal.emit(main_frame)

            # ── Stream to mobile client if connected ─────────────────────
            if self.client_connected:
                success1 = self.send_frame(main_frame, self.client_socket1)
                
                if self.client_connected and oth_frames:
                    frame1 = oth_frames[0]
                    if oth_box_annotators and oth_annotators:
                        if oth_box_annotators[0] and oth_detections and oth_detections[0]:
                            frame1 = oth_box_annotators[0].annotate(
                                scene=frame1, detections=oth_detections[0]
                            )
                        if oth_annotators[0]:
                            for annotator in oth_annotators[0]:
                                frame1 = annotator.annotate(scene=frame1)
                    self.send_frame(frame1, self.client_socket2)

            if isinstance(self.camera, Camera) and not self.camera.cap.isOpened():
                self.camera.connect_to_camera()




class HumanDetectorDesktopApp(QMainWindow):
    def __init__(self, initial_camera: "Camera | None" = None) -> None:
        super(HumanDetectorDesktopApp, self).__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # path to store videos
        self.video_path = settings.VIDEO_STORAGE_PATH
        Cleaner(settings.VIDEO_LIFETIME_HOURS).clean_directory(self.video_path)

        self.data = Data()
        self.data.create_tables()

        # TODO : подгрузка зон с БД
        # в детектор теперь идет массив зон типа [[x,y,x,y...],[x,y,x,y...]...] без решейпа
        self.zones = self.data.get_zones()
        self.detector = Detector(
            resolution=(1280, 720), polygons_arr=[[0, 0, 0, 0, 0, 0, 0, 0]]
        )
        # activate people detection every n frames, if 1 - always active
        self.activate_detector_every_n_frames = settings.DETECTION_EVERY_N_FRAMES

        # Load cameras from DB. The initial_camera is already saved in the DB by the startup logic.
        self.cameras = self.data.get_cameras()
        if len(self.cameras) == 0:
            self.cameras.append(Camera(1, 0, "webcam 1", 30, (1280, 720)))

        for cam in self.cameras:
            self.ui.cb_current_camera.addItem(str(cam.name))

        initial_idx = 0
        if initial_camera is not None:
            for i, cam in enumerate(self.cameras):
                if cam.id == initial_camera.id:
                    initial_idx = i
                    break

        self.current_camera = self.cameras[initial_idx]
        self.ui.cb_current_camera.setCurrentIndex(initial_idx)
        self.ui.cb_current_camera.currentIndexChanged.connect(self.cb_index_changed)

        self.email_server = None
        self.reciever_email = None

        self.ui.settings.triggered.connect(self.open_settings_window)
        self.ui.cameras_settings.triggered.connect(self.open_cameras_list_window)
        self.ui.zone_settings.triggered.connect(self.open_zone_redactor)

        self.video_stream = self.ui.video_stream
        self.is_active_detector = False

        self.ui.activate_people_detector.clicked.connect(
            self.activate_detector_button_clicked
        )

        self.thread = VideoThread(
            self.detector, self.is_active_detector, self.activate_detector_every_n_frames
        )
        self.thread.set_camera(self.current_camera)
        self.thread.set_cameras(self.cameras)
        self.thread.set_zones(self.zones)
        self.thread.change_pixmap_signal.connect(self.update_image)
        self.thread.start()

    def cb_update(self):
        self.ui.cb_current_camera.clear()
        for i in range(len(self.cameras)):
            self.ui.cb_current_camera.addItem(self.cameras[i].name)

    def cb_index_changed(self, index):
        self.detector.change_zone(
            self.data.get_zones_by_camera_id(self.cameras[index].id)
        )
        self.current_camera = self.cameras[index]
        self.thread.set_camera(self.current_camera)
        self.thread.set_cameras(self.cameras)
        self.thread.set_zones(self.zones)

    def add_new_camera(self):
        ip = self.ui_add_edit_camera.le_ip.text()
        fps = int(self.ui_add_edit_camera.le_fps.text())
        resolution = self.ui_add_edit_camera.le_resolution.text()
        name = self.ui_add_edit_camera.le_name.text()

        if name == "":
            name = None

        self.data.add_camera(ip, fps, resolution, name)
        self.cameras = self.data.get_cameras()
        self.cb_update()
        self.view_data()
        self.add_edit_camera_window.close()

    def edit_curr_camera(self):
        indexes = self.ui_cameras_list_window.tbl_cameras.selectedIndexes()
        if not indexes:
            return
        row = indexes[0].row()
        id_index = self.ui_cameras_list_window.tbl_cameras.model().index(row, 0)
        id = str(self.ui_cameras_list_window.tbl_cameras.model().data(id_index))

        ip = self.ui_add_edit_camera.le_ip.text()
        fps = int(self.ui_add_edit_camera.le_fps.text())
        resolution = self.ui_add_edit_camera.le_resolution.text()
        name = self.ui_add_edit_camera.le_name.text()

        if name == "":
            name = None

        self.data.update_camera(id, ip, fps, resolution, name)
        self.cameras = self.data.get_cameras()
        self.cb_update()

        self.view_data()
        self.add_edit_camera_window.close()

    def delete_curr_camera(self):
        indexes = self.ui_cameras_list_window.tbl_cameras.selectedIndexes()
        if not indexes:
            return
        row = indexes[0].row()
        id_index = self.ui_cameras_list_window.tbl_cameras.model().index(row, 0)
        id = str(self.ui_cameras_list_window.tbl_cameras.model().data(id_index))

        self.data.delete_camera(id)
        self.view_data()

    def open_add_edit_camera_window(self):
        self.add_edit_camera_window = QtWidgets.QDialog()
        self.ui_add_edit_camera = Ui_AddEditCamera()
        self.ui_add_edit_camera.setupUi(self.add_edit_camera_window)

        sender = self.sender()
        if sender.text() == "Добавить камеру":
            self.ui_add_edit_camera.btn_save_camera.clicked.connect(self.add_new_camera)
        else:
            indexes = self.ui_cameras_list_window.tbl_cameras.selectedIndexes()
            if indexes:
                row = indexes[0].row()
                id_index = self.ui_cameras_list_window.tbl_cameras.model().index(row, 0)
                cam_id = str(self.ui_cameras_list_window.tbl_cameras.model().data(id_index))
                camera_data = self.data.get_camera(cam_id)
                self.ui_add_edit_camera.le_ip.setText(str(camera_data.ip))
                self.ui_add_edit_camera.le_fps.setText(str(camera_data.camera_fps))
                self.ui_add_edit_camera.le_name.setText(str(camera_data.name))
                self.ui_add_edit_camera.le_resolution.setText(' '.join(map(str, camera_data.resolution)))
            self.ui_add_edit_camera.btn_save_camera.clicked.connect(self.edit_curr_camera)

        self.add_edit_camera_window.show()

    def view_data(self):
        headers = ["id", "connection_string", "name", "fps", "resolution"]
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(headers)
        for cam in self.data.get_cameras_as_dicts():
            row = [QStandardItem(str(cam[h] or "")) for h in headers]
            self.model.appendRow(row)
        self.ui_cameras_list_window.tbl_cameras.setModel(self.model)
        self.ui_cameras_list_window.tbl_cameras.resizeColumnsToContents()

    def open_cameras_list_window(self):
        self.cameras_list_window = QtWidgets.QDialog()
        self.ui_cameras_list_window = Ui_CamerasWindow()
        self.ui_cameras_list_window.setupUi(self.cameras_list_window)
        self.ui_cameras_list_window.tbl_cameras.resizeColumnsToContents()

        self.ui_cameras_list_window.btn_add_camera.clicked.connect(
            self.open_add_edit_camera_window
        )
        self.ui_cameras_list_window.btn_edit_camera.clicked.connect(
            self.open_add_edit_camera_window
        )
        self.ui_cameras_list_window.btn_delete_camera.clicked.connect(
            self.delete_curr_camera
        )

        self.view_data()

        self.cameras_list_window.show()

    def open_zone_redactor(self):
        # добавить готовые зоны из бд если есть и сунуть их туда же их в конструктор
        list_of_polygons = self.data.get_zones_by_camera_id(self.current_camera.id)
        last_frame = self.current_camera.read()
        self.zone_redactor_window = ZoneRedactorWindow(last_frame, list_of_polygons)
        self.zone_redactor_window.data_saved.connect(self.update_zone_list)
        self.zone_redactor_window.show()

    @Slot(list)
    def update_zone_list(self):
        self.list_of_zones = self.zone_redactor_window.detector_coords
        self.data.delete_zone_by_camera_id(self.current_camera.id)
        for zone in self.list_of_zones:
            zone = " ".join(map(str, zone))
            self.data.add_zone_exec(self.current_camera.id, zone)
        self.detector.change_zone(np.array(self.list_of_zones))
        self.zones[self.current_camera.id] = self.list_of_zones
        self.thread.set_zones(self.zones)

    # connected to click on settings
    def open_settings_window(self):
        """
        Create new window where you can
            change zone,
            sender and reciever emails,
            video path
        and some more things will be added)
        """
        self.settings_window = QtWidgets.QDialog()
        self.ui_settings_window = Ui_EmailPathChanging()
        self.ui_settings_window.setupUi(self.settings_window)
        
        if hasattr(self.ui_settings_window, 'btn_save_zone'):
            try:
                self.ui_settings_window.btn_save_zone.clicked.connect(self.save_new_cords)
            except AttributeError:
                pass
                
        if hasattr(self.ui_settings_window, 'btn_save_video_path'):
            self.ui_settings_window.btn_save_video_path.clicked.connect(self.update_video_path)

        self.ui_settings_window.btn_save_reciever.clicked.connect(self.save_reciever)
        self.ui_settings_window.btn_save_sender.clicked.connect(self.save_sender)

        self.settings_window.show()

    def update_video_path(self):
        self.video_path = self.ui_settings_window.le_video_path.text()

    # connected to click on button btn_save_reciever
    def save_reciever(self):
        """
        initialize email server and set it in video thread if sender server already initialized
        """
        self.reciever_email = self.ui_settings_window.le_reciever_email.text()
        if self.email_server:
            self.thread.set_email_settings(self.email_server, self.reciever_email)

    # connected to click on button btn_save_sender
    def save_sender(self):
        """
        initialize email server and set it in video thread if reciever email already initialized
        """
        print(self.ui_settings_window.le_sender_pass.text(), "\n\n")
        self.email_server = Email_server(
            self.ui_settings_window.le_sender_email.text(),
            #'phfm ysxx evul awtr'
            self.ui_settings_window.le_sender_pass.text(),
        )
        if self.reciever_email:
            self.thread.set_email_settings(self.email_server, self.reciever_email)

    # connected to click on button btn_save_zone
    def save_new_cords(self):
        """
        change protected area
        """
        cords = list(map(int, self.ui_settings_window.le_right_top_cords.text().split()))
        cords.extend(
            list(map(int, self.ui_settings_window.le_left_top_cords.text().split()))
        )
        cords.extend(
            list(map(int, self.ui_settings_window.le_left_bottom_cords.text().split()))
        )
        cords.extend(
            list(map(int, self.ui_settings_window.le_right_bottom_cords.text().split()))
        )
        self.detector.change_zone(np.array(cords, dtype=int).reshape((4, 2)))

    # connected to click on button activate_people_detector
    def activate_detector_button_clicked(self):
        """
        change text on activate_people_detector button,
        change is_active_detector in thread (video stream)
        """
        if self.is_active_detector:
            self.is_active_detector = False
            self.ui.activate_people_detector.setText(
                "Включить\nраспознавание людей\nна видео"
            )
        else:
            self.is_active_detector = True
            self.ui.activate_people_detector.setText(
                "Выключить\nраспознавание людей\nна видео"
            )

        self.thread.set_active_detector(self.is_active_detector)

    @Slot(np.ndarray)
    def update_image(self, cv_img):
        qt_img = self.convert_cv_qt(cv_img)
        self.video_stream.setPixmap(qt_img)

    def convert_cv_qt(self, cv_img):
        """
        convert image from cv2 format to qt format
        """
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_Qt_format = QtGui.QImage(
            rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888
        )
        p = convert_to_Qt_format.scaled(1280, 720, Qt.KeepAspectRatio)
        return QPixmap.fromImage(p)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Show source selection dialog before the main window
    dialog = SourceSelectionDialog()
    if dialog.exec() != SourceSelectionDialog.Accepted:
        sys.exit(0)

    from connection import Data
    data = Data()

    cam_str = str(dialog.camera_url)

    # Ensure the selected camera exists in the DB so it acquires a valid ID
    existing_cameras = data.get_cameras()
    initial_camera = next((c for c in existing_cameras if str(c.ip) == cam_str), None)

    if initial_camera is None:
        existing_names = {c.name for c in existing_cameras if c.name}
        final_name = dialog.camera_name or "Camera"
        counter = 2
        while final_name in existing_names:
            final_name = f"{dialog.camera_name or 'Camera'} {counter}"
            counter += 1

        res_str = f"{dialog.resolution[0]} {dialog.resolution[1]}"
        data.add_camera(cam_str, dialog.fps, res_str, final_name)
        existing_cameras = data.get_cameras()
        initial_camera = existing_cameras[-1]

    window = HumanDetectorDesktopApp(initial_camera=initial_camera)
    window.show()
    sys.exit(app.exec())
