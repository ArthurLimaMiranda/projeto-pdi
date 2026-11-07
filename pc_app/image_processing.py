"""PDI clássico: remoção opcional de ruído seguida de realce da cena.

O operador escolhe as duas camadas. O computador não interpreta a cena nem
controla os motores. Todos os filtros recebem somente o frame atual.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np


BASE_MODES = ("original", "baixa_luz", "contraste", "marcadores")
NOISE_MODES = ("nenhum", "sal_pimenta", "listras", "estatico")
MODES = BASE_MODES  # atalhos existentes do console
MODE_NAMES = {
    "original": "Sem realce",
    "baixa_luz": "Baixa luz",
    "contraste": "Contraste local",
    "marcadores": "Marcadores",
}
NOISE_NAMES = {
    "nenhum": "Sem filtro",
    "sal_pimenta": "Sal e pimenta",
    "listras": "Listras (FFT)",
    "estatico": "Estático",
}

BASE_PARAMETER_SPECS = {
    "original": (),
    "baixa_luz": (("gamma", 0.25, 1.50, 0.05), ("clahe_clip", 1.0, 6.0, 0.25)),
    "contraste": (("contrast_clip", 1.0, 6.0, 0.25), ("clahe_tiles", 2, 12, 1)),
    "marcadores": (("marker_threshold", 10, 70, 2), ("marker_min_area", 6, 80, 2)),
}
NOISE_PARAMETER_SPECS = {
    "nenhum": (),
    "sal_pimenta": (("median_kernel", 3, 7, 2), ("impulse_threshold", 20, 100, 5)),
    "listras": (("notch_radius", 2, 10, 1), ("notch_pairs", 1, 4, 1)),
    "estatico": (("static_strength", 4, 25, 1), ("static_search", 7, 15, 2)),
}


@dataclass
class ProcessingSettings:
    mode: str = "original"
    noise_mode: str = "nenhum"
    focus: str = "base"  # camada cujo par de controles deslizantes está visível
    gamma: float = 0.60
    clahe_clip: float = 2.0
    contrast_clip: float = 2.0
    clahe_tiles: int = 8
    median_kernel: int = 5
    impulse_threshold: int = 35
    notch_radius: int = 4
    notch_pairs: int = 3
    static_strength: int = 10
    static_search: int = 7
    marker_threshold: int = 25
    marker_min_area: int = 18
    marker_roi: tuple[float, float, float, float] = (0.17, 0.35, 0.92, 0.89)
    marked_objects: list[tuple[float, float]] = field(default_factory=list)
    mirror: bool = False

    def parameter_specs(self):
        if self.focus == "base":
            return BASE_PARAMETER_SPECS[self.mode]
        if self.focus == "noise":
            return NOISE_PARAMETER_SPECS[self.noise_mode]
        raise ValueError(f"camada de ajuste inválida: {self.focus}")

    def reset_current_mode(self):
        """Restaura só os controles da camada em foco."""
        defaults = ProcessingSettings()
        for attribute, _, _, _ in self.parameter_specs():
            setattr(self, attribute, getattr(defaults, attribute))
        if self.focus == "base" and self.mode == "marcadores":
            self.marker_roi = defaults.marker_roi
            self.marked_objects.clear()

    def parameter_ratio(self, parameter: int):
        attribute, minimum, maximum, _ = self.parameter_specs()[parameter - 1]
        return (getattr(self, attribute) - minimum) / (maximum - minimum)

    def set_parameter_ratio(self, parameter: int, ratio: float):
        attribute, minimum, maximum, step = self.parameter_specs()[parameter - 1]
        ratio = max(0.0, min(1.0, float(ratio)))
        steps = round((maximum - minimum) / step)
        value = minimum + round(ratio * steps) * step
        setattr(self, attribute, int(value) if isinstance(minimum, int) else round(value, 2))

    def adjust(self, parameter: int, direction: int):
        if parameter not in (1, 2) or direction not in (-1, 1):
            raise ValueError("parâmetro ou direção inválidos")
        specs = self.parameter_specs()
        if parameter > len(specs):
            return
        attribute, minimum, maximum, step = specs[parameter - 1]
        value = max(minimum, min(maximum, getattr(self, attribute) + step * direction))
        setattr(self, attribute, int(value) if isinstance(minimum, int) else round(value, 2))

    def parameter_labels(self):
        if self.focus == "base":
            if self.mode == "baixa_luz":
                return (f"gama: {self.gamma:.2f}", f"CLAHE clip: {self.clahe_clip:.1f}")
            if self.mode == "contraste":
                return (f"CLAHE clip: {self.contrast_clip:.1f}", f"tiles: {self.clahe_tiles}x{self.clahe_tiles}")
            if self.mode == "marcadores":
                return (f"sensibilidade: {self.marker_threshold}",
                        f"fragmento mínimo: {self.marker_min_area} px")
        else:
            if self.noise_mode == "sal_pimenta":
                return (f"mediana: {self.median_kernel}x{self.median_kernel}", f"limiar: {self.impulse_threshold}")
            if self.noise_mode == "listras":
                return (f"raio notch: {self.notch_radius}", f"pares de picos: {self.notch_pairs}")
            if self.noise_mode == "estatico":
                return (f"forca NLM: {self.static_strength}", f"busca: {self.static_search}x{self.static_search}")
        return ("sem parametros", "")


def _clahe(channel, clip, tiles):
    return cv2.createCLAHE(clipLimit=clip, tileGridSize=(tiles, tiles)).apply(channel)


def remove_impulse_noise(frame, kernel=5, threshold=35):
    """Mediana integral em ruído denso; substituição seletiva em pontos raros."""
    median = cv2.medianBlur(frame, kernel)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray_median = cv2.cvtColor(median, cv2.COLOR_BGR2GRAY)
    difference = np.abs(gray.astype(np.int16) - gray_median.astype(np.int16))
    # Na gravação, muitos impulsos foram espalhados pela compressão do vídeo.
    # A máscara seletiva deixa seus halos; a mediana integral remove o conjunto.
    if np.mean(difference > threshold) > 0.03:
        return median
    result = frame.copy()
    mask = difference > threshold
    result[mask] = median[mask]
    return result


def remove_periodic_noise(frame, radius=4, pairs=3):
    """Acha picos espectrais isolados e aplica notches simétricos na FFT."""
    height, width = frame.shape[:2]
    if min(height, width) < 32:
        return frame.copy()

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    window = np.outer(np.hanning(height), np.hanning(width)).astype(np.float32)
    spectrum = np.fft.fftshift(np.fft.fft2((gray - gray.mean()) * window))
    log_magnitude = np.log1p(np.abs(spectrum)).astype(np.float32)
    score = log_magnitude - cv2.GaussianBlur(log_magnitude, (0, 0), 8)

    cy, cx = height // 2, width // 2
    yy, xx = np.ogrid[:height, :width]
    dc_radius = max(8, round(min(height, width) * 0.05))
    central = (yy - cy) ** 2 + (xx - cx) ** 2 < dc_radius ** 2
    score[central] = -np.inf
    mask = np.ones((height, width), np.float32)

    for _ in range(pairs):
        py, px = np.unravel_index(np.argmax(score), score.shape)
        if score[py, px] < 2.0:
            break  # sem pico isolado: preservar a cena
        conjugate = ((2 * cy - py) % height, (2 * cx - px) % width)
        for qy, qx in ((py, px), conjugate):
            distance2 = (yy - qy) ** 2 + (xx - qx) ** 2
            mask *= 1 - np.exp(-distance2 / (2 * radius ** 2))
            margin = max(8, 2 * radius)
            score[max(0, qy - margin):min(height, qy + margin + 1),
                  max(0, qx - margin):min(width, qx + margin + 1)] = -np.inf

    mask[central] = 1.0  # mantém o brilho médio e as estruturas grandes
    spectrum_color = np.fft.fftshift(
        np.fft.fft2(frame.astype(np.float32), axes=(0, 1)), axes=(0, 1)
    )
    recovered = np.fft.ifft2(
        np.fft.ifftshift(spectrum_color * mask[..., None], axes=(0, 1)), axes=(0, 1)
    )
    return np.clip(np.real(recovered), 0, 255).astype(np.uint8)


def remove_static_noise(frame, strength=10, search=7):
    """Aplica NLM somente quando há granulação difusa sem impulsos densos."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    residual = cv2.absdiff(gray, cv2.medianBlur(gray, 5))
    # Q75 distingue granulação espalhada de cenas limpas. A cauda acima de
    # 60 distingue sal e pimenta, para o qual NLM deixa pontos e cria halos.
    if np.percentile(residual, 75) < 8 or np.mean(residual > 60) > 0.025:
        return frame.copy()
    return cv2.fastNlMeansDenoisingColored(frame, None, strength, strength, 7, search)


def segment_marker_edges(frame, threshold=25, min_area=18,
                         roi=(0.17, 0.35, 0.92, 0.89)):
    """Máscara binária das bordas na ROI, sem presumir objetos fechados."""
    height, width = frame.shape[:2]
    x0, y0, x1, y1 = (int(roi[0] * width), int(roi[1] * height),
                      int(roi[2] * width), int(roi[3] * height))
    x0, x1 = sorted((max(0, min(width, x0)), max(0, min(width, x1))))
    y0, y1 = sorted((max(0, min(height, y0)), max(0, min(height, y1))))
    if x1 - x0 < 5 or y1 - y0 < 5:
        return np.zeros_like(frame)

    luminance = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)[:, :, 0]
    luminance = _clahe(luminance, 2.0, 8)
    luminance = cv2.bilateralFilter(luminance, 7, 20, 5)
    edges = cv2.Canny(luminance, threshold, threshold * 3)
    mask = np.zeros((height, width), np.uint8)
    mask[y0:y1, x0:x1] = edges[y0:y1, x0:x1]

    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    clean = np.zeros_like(mask)
    for component in range(1, count):
        if stats[component, cv2.CC_STAT_AREA] >= min_area:
            clean[labels == component] = 255
    return cv2.cvtColor(clean, cv2.COLOR_GRAY2BGR)


def process_frame(frame_bgr, settings=None):
    """Recebe BGR e devolve BGR: ruído -> realce -> espelhamento opcional."""
    if frame_bgr is None:
        return None
    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3 or frame_bgr.dtype != np.uint8:
        raise ValueError("process_frame espera uma imagem BGR uint8 de 3 canais")

    settings = settings or ProcessingSettings()
    if settings.mode not in BASE_MODES or settings.noise_mode not in NOISE_MODES:
        raise ValueError("modo de PDI inválido")

    if settings.noise_mode == "sal_pimenta":
        result = remove_impulse_noise(frame_bgr, settings.median_kernel, settings.impulse_threshold)
    elif settings.noise_mode == "listras":
        result = remove_periodic_noise(frame_bgr, settings.notch_radius, settings.notch_pairs)
    elif settings.noise_mode == "estatico":
        result = remove_static_noise(frame_bgr, settings.static_strength, settings.static_search)
    else:
        result = frame_bgr.copy()

    if settings.mode == "baixa_luz":
        y, cr, cb = cv2.split(cv2.cvtColor(result, cv2.COLOR_BGR2YCrCb))
        y = cv2.bilateralFilter(y, 5, 20, 5)
        lut = np.clip(255 * (np.arange(256) / 255) ** settings.gamma, 0, 255).astype(np.uint8)
        y = _clahe(cv2.LUT(y, lut), settings.clahe_clip, settings.clahe_tiles)
        result = cv2.cvtColor(cv2.merge((y, cr, cb)), cv2.COLOR_YCrCb2BGR)
    elif settings.mode == "contraste":
        lab = cv2.cvtColor(result, cv2.COLOR_BGR2LAB)
        lab[:, :, 0] = _clahe(lab[:, :, 0], settings.contrast_clip, settings.clahe_tiles)
        result = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    elif settings.mode == "marcadores":
        result = segment_marker_edges(result, settings.marker_threshold,
                                      settings.marker_min_area, settings.marker_roi)

    return cv2.flip(result, 1) if settings.mirror else result
