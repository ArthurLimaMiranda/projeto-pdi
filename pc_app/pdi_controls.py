"""Seletores independentes de realce e ruído na janela Pygame."""

import pygame

from image_processing import BASE_MODES, MODE_NAMES, NOISE_MODES, NOISE_NAMES


EXPLANATIONS = {
    "original": "Sem realce da cena.",
    "baixa_luz": "Gama e CLAHE na luminância para áreas escuras.",
    "contraste": "CLAHE em Lab para contraste local.",
    "marcadores": "Máscara de bordas; clique em cada objeto para contar.",
    "nenhum": "Sem filtro de ruído.",
    "sal_pimenta": "Mediana integral se há muitos pontos; seletiva se raros.",
    "listras": "Notch na FFT remove interferência periódica.",
    "estatico": "NLM atua apenas em granulação difusa detectada.",
}


class PDIControls:
    def __init__(self):
        self.mode_rects = {
            mode: pygame.Rect(300 + index * 240, 550, 225, 38)
            for index, mode in enumerate(BASE_MODES)
        }
        self.noise_rects = {
            mode: pygame.Rect(300 + index * 240, 608, 225, 38)
            for index, mode in enumerate(NOISE_MODES)
        }
        self.slider_rects = (pygame.Rect(300, 670, 450, 56), pygame.Rect(790, 670, 450, 56))
        self.reset_rect = pygame.Rect(300, 737, 190, 39)
        self.mirror_rect = pygame.Rect(500, 737, 190, 39)
        self.dragging = None
        self.roi_start = None

    @staticmethod
    def _rail(rect):
        return pygame.Rect(rect.x + 15, rect.y + 34, rect.width - 30, 6)

    def _move_slider(self, parameter, x, settings):
        rail = self._rail(self.slider_rects[parameter - 1])
        settings.set_parameter_ratio(parameter, (x - rail.left) / rail.width)

    def handle_event(self, event, settings, frame_rect=None, processed_rect=None):
        if settings.mode == "marcadores" and frame_rect is not None:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and frame_rect.collidepoint(event.pos):
                self.roi_start = event.pos
                return True
            if event.type == pygame.MOUSEMOTION and self.roi_start is not None:
                if hasattr(event, "buttons") and not event.buttons[0]:
                    self.roi_start = None
                    return False
                self._set_marker_roi(self.roi_start, event.pos, frame_rect, settings)
                return True
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.roi_start is not None:
                self._set_marker_roi(self.roi_start, event.pos, frame_rect, settings)
                self.roi_start = None
                return True
        if settings.mode == "marcadores" and processed_rect is not None:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and processed_rect.collidepoint(event.pos):
                px = (event.pos[0] - processed_rect.x) / processed_rect.width
                py = (event.pos[1] - processed_rect.y) / processed_rect.height
                x0, y0, x1, y1 = settings.marker_roi
                if not (x0 <= px <= x1 and y0 <= py <= y1):
                    return False
                for index, (mx, my) in enumerate(settings.marked_objects):
                    dx = (px - mx) * processed_rect.width
                    dy = (py - my) * processed_rect.height
                    if dx * dx + dy * dy <= 15 * 15:
                        settings.marked_objects.pop(index)
                        return True
                settings.marked_objects.append((px, py))
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for mode, rect in self.mode_rects.items():
                if rect.collidepoint(event.pos):
                    settings.mode = mode
                    settings.focus = "base"
                    self.dragging = None
                    self.roi_start = None
                    return True
            for mode, rect in self.noise_rects.items():
                if rect.collidepoint(event.pos):
                    settings.noise_mode = mode
                    settings.focus = "noise"
                    self.dragging = None
                    return True
            if self.mirror_rect.collidepoint(event.pos):
                settings.mirror = not settings.mirror
                self.dragging = None
                return True
            if self.reset_rect.collidepoint(event.pos):
                settings.reset_current_mode()
                self.dragging = None
                return True
            for parameter, rect in enumerate(self.slider_rects[:len(settings.parameter_specs())], 1):
                if rect.collidepoint(event.pos):
                    self.dragging = parameter
                    self._move_slider(parameter, event.pos[0], settings)
                    return True
        elif event.type == pygame.MOUSEMOTION and self.dragging is not None:
            if self.dragging > len(settings.parameter_specs()):
                self.dragging = None
                return False
            if hasattr(event, "buttons") and not event.buttons[0]:
                self.dragging = None
                return False
            self._move_slider(self.dragging, event.pos[0], settings)
            return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.dragging is not None:
            if self.dragging <= len(settings.parameter_specs()):
                self._move_slider(self.dragging, event.pos[0], settings)
            self.dragging = None
            return True
        return False

    @staticmethod
    def _set_marker_roi(start, end, frame_rect, settings):
        x0, x1 = sorted((start[0], end[0]))
        y0, y1 = sorted((start[1], end[1]))
        if x1 - x0 < 8 or y1 - y0 < 8:
            return
        new_roi = (
            max(0.0, min(1.0, (x0 - frame_rect.x) / frame_rect.width)),
            max(0.0, min(1.0, (y0 - frame_rect.y) / frame_rect.height)),
            max(0.0, min(1.0, (x1 - frame_rect.x) / frame_rect.width)),
            max(0.0, min(1.0, (y1 - frame_rect.y) / frame_rect.height)),
        )
        if new_roi != settings.marker_roi:
            settings.marker_roi = new_roi
            settings.marked_objects.clear()

    @staticmethod
    def draw_marker_roi(screen, settings, frame_rect):
        if settings.mode != "marcadores" or frame_rect is None:
            return
        x0, y0, x1, y1 = settings.marker_roi
        outline = pygame.Rect(frame_rect.x + round(x0 * frame_rect.width),
                              frame_rect.y + round(y0 * frame_rect.height),
                              round((x1 - x0) * frame_rect.width),
                              round((y1 - y0) * frame_rect.height))
        pygame.draw.rect(screen, (80, 240, 130), outline, 2)

    @staticmethod
    def draw_marker_count(screen, settings, frame_rect, font):
        if settings.mode != "marcadores" or frame_rect is None:
            return
        for px, py in settings.marked_objects:
            center = (frame_rect.x + round(px * frame_rect.width),
                      frame_rect.y + round(py * frame_rect.height))
            pygame.draw.circle(screen, (105, 255, 150), center, 6)
        count_rect = pygame.Rect(frame_rect.x + 4, frame_rect.bottom - 26, 250, 22)
        pygame.draw.rect(screen, (22, 37, 30), count_rect, border_radius=3)
        label = font.render(f"Quantidade marcada: {len(settings.marked_objects)}", True,
                            (165, 255, 192))
        screen.blit(label, (count_rect.x + 5, count_rect.y + 3))

    @staticmethod
    def _text(screen, font, value, x, y, color=(235, 235, 235)):
        screen.blit(font.render(value, True, color), (x, y))

    @staticmethod
    def _button(screen, rect, label, selected, focused, font):
        background = (39, 97, 78) if selected else (35, 40, 47)
        border = (164, 255, 202) if selected and focused else (92, 101, 112)
        pygame.draw.rect(screen, background, rect, border_radius=7)
        pygame.draw.rect(screen, border, rect, 2, border_radius=7)
        surface = font.render(label, True, (245, 245, 245))
        screen.blit(surface, surface.get_rect(center=rect.center))

    def draw(self, screen, settings, small_font, tiny_font):
        self._text(screen, tiny_font, "CENA - realce ou análise", 300, 533)
        for mode, rect in self.mode_rects.items():
            self._button(screen, rect, MODE_NAMES[mode], mode == settings.mode,
                         settings.focus == "base", small_font)

        self._text(screen, tiny_font, "RUÍDO - pode combinar com o realce acima", 300, 591)
        for mode, rect in self.noise_rects.items():
            self._button(screen, rect, NOISE_NAMES[mode], mode == settings.noise_mode,
                         settings.focus == "noise", small_font)

        layer = "cena" if settings.focus == "base" else "ruído"
        self._text(screen, tiny_font, f"AJUSTANDO: {layer}", 300, 652, (164, 255, 202))
        labels = settings.parameter_labels()
        specs = settings.parameter_specs()
        if not specs:
            self._text(screen, small_font, "Sem parâmetros nesta opção.", 300, 683)
        for parameter, rect in enumerate(self.slider_rects[:len(specs)], 1):
            self._text(screen, small_font, labels[parameter - 1], rect.x + 15, rect.y)
            rail = self._rail(rect)
            pygame.draw.rect(screen, (76, 84, 94), rail, border_radius=3)
            knob_x = rail.left + round(settings.parameter_ratio(parameter) * rail.width)
            if knob_x > rail.left:
                pygame.draw.rect(screen, (116, 235, 170),
                                 (rail.left, rail.y, knob_x - rail.left, rail.height), border_radius=3)
            pygame.draw.circle(screen, (225, 255, 236), (knob_x, rail.centery), 11)

        self._button(screen, self.reset_rect, "Restaurar padrão", False, False, small_font)
        self._button(screen, self.mirror_rect,
                     f"Espelhar: {'ligado' if settings.mirror else 'desligado'}",
                     settings.mirror, settings.mirror, small_font)
        selected = settings.mode if settings.focus == "base" else settings.noise_mode
        self._text(screen, tiny_font, EXPLANATIONS[selected], 710, 747)
