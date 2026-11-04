"""OCR wrapper around RapidOCR (PaddleOCR models on ONNX Runtime) with deskew/sharpen preprocessing.

PaddleOCR itself needs the heavy paddlepaddle runtime (no wheels for recent Python versions); RapidOCR runs the same
PP-OCR detection/recognition models through onnxruntime and installs with pip alone.
"""
import math
import threading
from dataclasses import dataclass, field

import cv2
import numpy as np

MAX_PIXELS = 40_000_000
BLUR_THRESHOLD = 150.0  # variance of Laplacian below this is treated as blurry (tuned on the specimen set)

_engine = None
_lock = threading.Lock()


class OcrError(Exception):
    pass


@dataclass
class Line:
    text: str
    conf: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class OcrResult:
    lines: list[Line]
    image: np.ndarray
    quality: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(l.text for l in sorted(self.lines, key=lambda l: (round(l.cy / 10), l.x0)))


def _get_engine():
    global _engine
    with _lock:
        if _engine is None:
            from rapidocr_onnxruntime import RapidOCR

            _engine = RapidOCR()
    return _engine


def decode_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise OcrError("File is not a readable image (use PNG or JPG).")
    if img.shape[0] * img.shape[1] > MAX_PIXELS:
        raise OcrError("Image resolution is too large.")
    return img


def _run(img: np.ndarray) -> tuple[list[Line], list[float]]:
    engine = _get_engine()
    with _lock:
        res, _ = engine(img)
    lines, angles = [], []
    for box, text, conf in res or []:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        lines.append(Line(text.strip(), float(conf), min(xs), min(ys), max(xs), max(ys)))
        if len(text) >= 6:
            dx, dy = box[1][0] - box[0][0], box[1][1] - box[0][1]
            if dx > 0:
                angles.append(math.degrees(math.atan2(dy, dx)))
    return lines, angles


def _rotate(img: np.ndarray, angle: float) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(img, m, (nw, nh), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))


def _sharpen(img: np.ndarray) -> np.ndarray:
    big = cv2.resize(img, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(big, (0, 0), 3)
    return cv2.addWeighted(big, 2.2, blur, -1.2, 0)


def _score(lines: list[Line]) -> float:
    return sum(l.conf * min(len(l.text), 20) for l in lines)


def run_ocr(data: bytes) -> OcrResult:
    img = decode_image(data)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    quality = {"width": img.shape[1], "height": img.shape[0], "blur_score": round(blur_var, 1),
               "blurry": blur_var < BLUR_THRESHOLD, "skew_degrees": 0.0, "deskewed": False, "sharpened": False}

    lines, angles = _run(img)
    best_img, best_lines = img, lines
    skew = float(np.median(angles)) if angles else 0.0
    quality["skew_degrees"] = round(skew, 1)
    if abs(skew) > 1.0:
        rot = _rotate(img, skew)
        l2, _ = _run(rot)
        if _score(l2) >= _score(best_lines) * 0.9:
            best_img, best_lines = rot, l2
            quality["deskewed"] = True
    if quality["blurry"]:
        sharp = _sharpen(best_img)
        l3, _ = _run(sharp)
        if _score(l3) > _score(best_lines):
            best_img, best_lines = sharp, l3
            quality["sharpened"] = True

    confs = [l.conf for l in best_lines]
    quality["mean_confidence"] = round(float(np.mean(confs)), 3) if confs else 0.0
    quality["line_count"] = len(best_lines)
    return OcrResult(best_lines, best_img, quality)


def ocr_crop(res: OcrResult, x0: float, y0: float, x1: float, y1: float, scale: float = 2.5) -> list[Line]:
    """Re-run OCR on a cropped region at higher zoom (used for values the full-page pass missed, e.g. the GSTIN)."""
    h, w = res.image.shape[:2]
    xa, ya, xb, yb = max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))
    if xb - xa < 10 or yb - ya < 5:
        return []
    crop = res.image[ya:yb, xa:xb]
    crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    crop = cv2.copyMakeBorder(crop, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    lines, _ = _run(crop)
    return lines
