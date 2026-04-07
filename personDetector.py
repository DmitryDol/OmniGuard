import logging

import cv2
import numpy as np
import supervision as sv
from PIL import Image

from config import settings

logger = logging.getLogger(__name__)

PERSON_CLASS_ID = 0  # COCO class ID for "person"

# ── Model factory ─────────────────────────────────────────────────────────
# Maps the DETECTION_MODEL config value to the corresponding rfdetr class.
# To switch models, change DETECTION_MODEL in .env (e.g. DETECTION_MODEL=nano).

_MODEL_REGISTRY: dict[str, tuple[str, str]] = {
    "nano":   ("rfdetr", "RFDETRNano"),
    "small":  ("rfdetr", "RFDETRSmall"),
    "medium": ("rfdetr", "RFDETRMedium"),
    "large":  ("rfdetr", "RFDETRLarge"),
}


def _create_model(size: str = "l"):
    """
    Factory function to create an Ultralytics RT-DETR model based on size.
    Allowed sizes: 'l', 'x'
    """
    from ultralytics import RTDETR
    model_name = f"rtdetr-{size}.pt"
    logger.info(f"Loading RT-DETR model: {model_name}")
    return RTDETR(model_name)


class Detector:
    def __init__(self, resolution: tuple[int, int], polygons_arr: list):
        self.resolution = resolution
        try:
            self.model = _create_model(settings.DETECTION_MODEL)
            logger.info("RT-DETR model loaded via Ultralytics.")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
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
        Detects people on the provided frame, runs zone triggering,
        and returns annotated frame + detection objects.
        """
        # Run inference (Ultralytics usage)
        results = self.model.predict(
            source=frame,
            conf=settings.DETECTION_CONFIDENCE_THRESHOLD,
            classes=[PERSON_CLASS_ID],
            verbose=False,
        )
        
        # Parse into supervision format
        detections = sv.Detections.from_ultralytics(results[0])

        # RF-DETR puts extra metadata (source_image, source_shape, etc.)
        # into detections.data which breaks supervision's validation
        # during filtering and zone.trigger(). Clear it entirely.
        detections.data = {}

        # Filter to only "person" class (class_id == 0 in COCO)
        if detections.class_id is not None:
            detections = detections[detections.class_id == PERSON_CLASS_ID]

        people = 0
        for zone, annotator in zip(self.zone_arr, self.annotators):
            trig_arr = zone.trigger(detections)
            people += np.sum(trig_arr == True)
            frame = annotator.annotate(scene=frame)

        frame = self.box_annotator.annotate(scene=frame, detections=detections)

        return (people > 0, frame, self.box_annotator, self.annotators, detections)
