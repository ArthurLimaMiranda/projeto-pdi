"""Barra de reprodução para fontes de vídeo locais."""

import pygame


def _time_label(seconds):
    value = max(0, int(seconds))
    minutes, seconds = divmod(value, 60)
    return f"{minutes:02d}:{seconds:02d}"


class VideoTimeline:
    def __init__(self):
        self.pause_rect = pygame.Rect(300, 492, 114, 38)
        self.rail = pygame.Rect(440, 509, 628, 7)
        self.seek_area = self.rail.inflate(12, 34)
        self.dragging = False
        self.preview_sec = None
        self.was_paused = False

    def _position(self, x, duration):
        fraction = max(0.0, min(1.0, (x - self.rail.left) / self.rail.width))
        return fraction * duration

    def _finish_drag(self, x, source):
        duration = source.get_status()["duration_sec"]
        source.seek(self._position(x, duration))
        source.set_paused(self.was_paused)
        self.dragging = False
        self.preview_sec = None

    def handle_event(self, event, source):
        status = source.get_status()
        if not status["seekable"]:
            return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.pause_rect.collidepoint(event.pos):
                source.set_paused(not status["paused"])
                return True
            if self.seek_area.collidepoint(event.pos):
                self.was_paused = status["paused"]
                source.set_paused(True)
                self.dragging = True
                self.preview_sec = self._position(event.pos[0], status["duration_sec"])
                return True
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            if hasattr(event, "buttons") and not event.buttons[0]:
                self._finish_drag(event.pos[0], source)
                return True
            self.preview_sec = self._position(event.pos[0], status["duration_sec"])
            return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.dragging:
            self._finish_drag(event.pos[0], source)
            return True
        return False

    def draw(self, screen, source, font):
        status = source.get_status()
        if not status["seekable"]:
            return

        pygame.draw.rect(screen, (35, 40, 47), self.pause_rect, border_radius=7)
        pygame.draw.rect(screen, (92, 101, 112), self.pause_rect, 2, border_radius=7)
        label = "Reproduzir" if status["paused"] and not self.dragging else "Pausar"
        rendered = font.render(label, True, (245, 245, 245))
        screen.blit(rendered, rendered.get_rect(center=self.pause_rect.center))

        position = self.preview_sec if self.dragging else status["position_sec"]
        duration = status["duration_sec"]
        fraction = min(1.0, position / duration) if duration > 0 else 0.0
        knob_x = self.rail.left + round(fraction * self.rail.width)
        pygame.draw.rect(screen, (76, 84, 94), self.rail, border_radius=3)
        if knob_x > self.rail.left:
            pygame.draw.rect(
                screen, (116, 235, 170),
                (self.rail.left, self.rail.y, knob_x - self.rail.left, self.rail.height),
                border_radius=3,
            )
        pygame.draw.circle(screen, (225, 255, 236), (knob_x, self.rail.centery), 10)

        label = f"{_time_label(position)} / {_time_label(duration)}"
        screen.blit(font.render(label, True, (235, 235, 235)), (1088, 502))
