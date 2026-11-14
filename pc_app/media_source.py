import time
from pathlib import Path

import cv2


_IMAGE_EXTENSIONS = {
    ".bmp",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


class MediaFileSource:
    """fornece frames a partir de uma imagem ou vídeo local."""

    def __init__(self, source, loop=True):
        self.path = Path(source).expanduser().resolve()
        self.loop = bool(loop)

        if not self.path.is_file():
            raise FileNotFoundError(f"arquivo de mídia não encontrado: {self.path}")

        self.frames_received = 0
        self.timeline_revision = 0
        self.reconnects = 0
        self.decode_errors = 0
        self.connection_errors = 0
        self.latest_frame = None
        self._opened = False

        self._is_image = self.path.suffix.lower() in _IMAGE_EXTENSIONS
        self._capture = None
        self._frame_interval = 1.0 / 30.0
        self._next_frame_at = 0.0
        self._fps = 30.0
        self._frame_count = 0
        self._position_sec = 0.0
        self._paused = False

        if self._is_image:
            frame = cv2.imread(str(self.path), cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError(f"não foi possível decodificar a imagem: {self.path}")

            self.latest_frame = frame
            self.frames_received = 1
            self._opened = True
            return

        self._capture = cv2.VideoCapture(str(self.path))
        if not self._capture.isOpened():
            self._capture.release()
            self._capture = None
            raise ValueError(f"não foi possível abrir o vídeo: {self.path}")

        fps = float(self._capture.get(cv2.CAP_PROP_FPS))
        if fps > 0.5:
            self._fps = fps
            self._frame_interval = 1.0 / min(fps, 240.0)
        self._frame_count = max(0, int(self._capture.get(cv2.CAP_PROP_FRAME_COUNT)))

        self._opened = True
        self._next_frame_at = time.monotonic()
        self._advance_video(force=True)

    def _advance_video(self, force=False):
        if self._capture is None:
            return

        now = time.monotonic()
        if not force and now < self._next_frame_at:
            return

        ok, frame = self._capture.read()
        if not ok:
            if not self.loop:
                self._opened = False
                return

            self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.timeline_revision += 1
            ok, frame = self._capture.read()

        if not ok or frame is None:
            self.decode_errors += 1
            self._opened = False
            return

        self.latest_frame = frame
        self.frames_received += 1
        self._opened = True
        next_frame = self._capture.get(cv2.CAP_PROP_POS_FRAMES)
        self._position_sec = max(0.0, (next_frame - 1) / self._fps)
        self._next_frame_at = now + self._frame_interval

    def set_paused(self, paused):
        if self._is_image:
            return False
        self._paused = bool(paused)
        self._next_frame_at = time.monotonic() + self._frame_interval
        return True

    def seek(self, position_sec):
        """Posiciona um vídeo local e já entrega o frame solicitado."""
        if self._capture is None or self._frame_count <= 0:
            return False
        frame_index = min(
            max(0, round(float(position_sec) * self._fps)), self._frame_count - 1
        )
        if not self._capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
            return False
        self.timeline_revision += 1
        ok, frame = self._capture.read()
        if not ok or frame is None:
            self.decode_errors += 1
            self._opened = False
            return False
        self.latest_frame = frame
        self.frames_received += 1
        self._opened = True
        self._position_sec = frame_index / self._fps
        self._next_frame_at = time.monotonic() + self._frame_interval
        return True

    def read_frame(self):
        if self._is_image:
            if self.latest_frame is None:
                return None
            return self.latest_frame.copy()

        if not self._paused:
            self._advance_video()
        if not self._opened or self.latest_frame is None:
            return None
        return self.latest_frame.copy()

    def read_frame_snapshot(self):
        frame = self.read_frame()
        return frame, self.frames_received, self.timeline_revision

    def get_status(self):
        return {
            "frames_received": self.frames_received,
            "timeline_revision": self.timeline_revision,
            "decode_errors": self.decode_errors,
            "connection_errors": self.connection_errors,
            "reconnects": self.reconnects,
            "opened": self._opened,
            "seekable": self._capture is not None and self._frame_count > 0,
            "position_sec": self._position_sec,
            "duration_sec": self._frame_count / self._fps,
            "paused": self._paused,
            "recording": False,
            "recording_path": None,
            "recorded_frames": 0,
            "recording_errors": 0,
        }

    def release(self):
        self._opened = False
        if self._capture is not None:
            self._capture.release()
            self._capture = None
