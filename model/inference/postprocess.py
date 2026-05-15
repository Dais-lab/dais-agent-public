"""Heatmap → bounding box annotation 후처리.

DINOv3 추론으로 나온 픽셀 heatmap 을 threshold 기준 마스크로 만들고,
연결 영역(contour)별로 bounding rectangle 을 추출한 뒤 원본 이미지에
빨간색 박스를 그려서 annotation 이미지를 만든다.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image


def heatmap_to_bboxes(
    heatmap: np.ndarray,
    threshold: float = 0.5,
    min_area: int = 50,
) -> list[dict]:
    """Heatmap (H, W, float in [0,1]) → 결함 영역 bbox 리스트.

    각 bbox 는 ``{"x","y","w","h","score"}`` 형식.
    ``score`` 는 해당 bbox 영역 내 heatmap 평균값.
    ``min_area`` 미만인 작은 영역은 노이즈로 보고 제외.
    결과는 score 내림차순.
    """
    mask = (heatmap >= threshold).astype(np.uint8) * 255
    contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
    )
    bboxes: list[dict] = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w * h < min_area:
            continue
        score = float(heatmap[y:y + h, x:x + w].mean())
        bboxes.append({
            "x": int(x), "y": int(y),
            "w": int(w), "h": int(h),
            "score": round(score, 6),
        })
    bboxes.sort(key=lambda b: b["score"], reverse=True)
    return bboxes


def draw_bboxes(
    image: Image.Image,
    bboxes: list[dict],
    color: tuple[int, int, int] = (255, 0, 0),  # RGB 빨강
    thickness: int = 2,
) -> Image.Image:
    """원본 이미지(PIL) 위에 bbox + score 라벨 그려서 새 PIL Image 반환."""
    arr = np.array(image.convert("RGB")).copy()
    for b in bboxes:
        x1, y1 = b["x"], b["y"]
        x2, y2 = x1 + b["w"], y1 + b["h"]
        cv2.rectangle(arr, (x1, y1), (x2, y2), color, thickness)
        label = f"{b['score']:.2f}"
        cv2.putText(
            arr, label, (x1, max(y1 - 5, 12)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
        )
    return Image.fromarray(arr)


__all__ = ["heatmap_to_bboxes", "draw_bboxes"]
