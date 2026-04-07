import cv2
import numpy as np
import supervision as sv
import torch

from config import settings


class Detector:
    def __init__(self, resolution: tuple[int, int], polygons_arr: list):
        self.resolution = resolution
        self.model = torch.hub.load("ultralytics/yolov5", "yolov5n", pretrained=True)
        self.model.classes = [0]
        self.box_annotator = sv.BoxAnnotator(thickness=4)

        # для каждой зоны
        self.zone_arr = []
        self.annotators = []

        for p_cords in polygons_arr:
            cords = np.array(p_cords).reshape(len(p_cords) // 2, 2)
            p_zone = sv.PolygonZone(polygon=cords)
            self.zone_arr.append(p_zone)
            self.zone_annotator = sv.PolygonZoneAnnotator(
                zone=p_zone,
                color=sv.Color.GREEN,
                thickness=2,
                text_thickness=1,
                text_scale=1,
            )
            self.annotators.append(self.zone_annotator)

    def change_zone(self, polygons_arr: np.ndarray):
        self.zone_arr = []
        self.annotators = []
        for p_cords in polygons_arr:
            cords = np.array(p_cords).reshape(len(p_cords) // 2, 2)
            p_zone = sv.PolygonZone(polygon=cords)
            self.zone_arr.append(p_zone)
            self.zone_annotator = sv.PolygonZoneAnnotator(
                zone=p_zone,
                color=sv.Color.GREEN,
                thickness=2,
                text_thickness=1,
                text_scale=1,
            )
            self.annotators.append(self.zone_annotator)

    def detect(self, frame) -> tuple:
        """
        Detects people in the zone

        args:
            frame:  list of pixels in format BGR (B-blue, G-green, R-red) \
                    with size of resolution[0] * resolution[1]
        return:
                was a person detected in the zone

        """

        # frame = cv2.resize(frame, self.resolution)
        results = self.model(frame)
        detections = sv.Detections.from_yolov5(results)
        detections = detections[
            detections.confidence > settings.DETECTION_CONFIDENCE_THRESHOLD
        ]
        people = 0
        for zone, annotator in zip(self.zone_arr, self.annotators):
            trig_arr = zone.trigger(detections)
            people += np.sum(trig_arr == True)
            frame = annotator.annotate(scene=frame)

        frame = self.box_annotator.annotate(scene=frame, detections=detections)

        return (people > 0, frame, self.box_annotator, self.annotators, detections)
