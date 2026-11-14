import logging
import time
from collections import deque

import pygame

from camera_viewer import CameraViewer
from config import (
    APP_VERSION,
    CONTROL_ANGULAR_SIGN,
    CONTROL_COMMAND_TIMEOUT_SEC,
    CONTROL_PACKET_REPEATS,
    CONTROL_SEND_HZ,
    DEFAULT_SPEED,
    FLASH_OFF_VALUE,
    FLASH_ON_VALUE,
    FPS,
    GATEWAY_CONTROL_PORT,
    GATEWAY_HOST,
    GATEWAY_STREAM_URL,
    LOG_LEVEL,
    MAX_SPEED,
    MEDIA_LOOP,
    MEDIA_SOURCE,
    MIN_SPEED,
    ROBOT_CAMERA_URL,
    ROBOT_IP,
    ROBOT_UDP_PORT,
    RUN_MODE,
    SESSION_TOKEN,
    SPEED_STEP,
    VALID_RUN_MODES,
    WINDOW_H,
    WINDOW_W,
)
from gateway_client import GatewayRobotClient
from image_processing import (
    MAX_STATIC_FRAMES,
    MODE_NAMES,
    MODES,
    NOISE_NAMES,
    ProcessingSettings,
    process_frame,
)
from media_source import MediaFileSource
from null_robot_client import NullRobotClient
from pdi_controls import PDIControls
from robot_client import RobotClient
from video_timeline import VideoTimeline


logger = logging.getLogger(__name__)


MODE_LABELS = {
    "gateway": "gateway da atividade",
    "robot": "robô direto de desenvolvimento",
    "video": "arquivo local",
}


def configure_logging():
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def draw_text(screen, text, x, y, font, color=(235, 235, 235)):
    screen.blit(font.render(str(text), True, color), (x, y))


def draw_frame_panel(screen, frame, rect, title, font, small_font, empty_text):
    """Mostra um frame sem deformar sua proporção, com área reservada fixa."""
    pygame.draw.rect(screen, (27, 31, 36), rect)
    pygame.draw.rect(screen, (69, 78, 88), rect, 1)
    draw_text(screen, title, rect.x + 12, rect.y + 10, font)
    image_area = rect.inflate(-16, -56)
    image_area.y += 18
    if frame is None:
        draw_text(screen, empty_text, image_area.x + 16, image_area.centery, small_font, (255, 205, 120))
        return None

    height, width = frame.shape[:2]
    scale = min(image_area.width / width, image_area.height / height)
    size = (max(1, int(width * scale)), max(1, int(height * scale)))
    surface = CameraViewer.frame_to_surface(frame, target_size=size)
    if surface is not None:
        x = image_area.x + (image_area.width - size[0]) // 2
        y = image_area.y + (image_area.height - size[1]) // 2
        screen.blit(surface, (x, y))
        return pygame.Rect(x, y, *size)
    return None


def get_manual_command(keys):
    if keys[pygame.K_w] or keys[pygame.K_UP]:
        return "forward"
    if keys[pygame.K_s] or keys[pygame.K_DOWN]:
        return "backward"
    if keys[pygame.K_a] or keys[pygame.K_LEFT]:
        return "left"
    if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
        return "right"
    return "stop"


def send_robot_command(robot, command):
    actions = {
        "forward": robot.forward,
        "backward": robot.backward,
        "left": robot.left,
        "right": robot.right,
        "stop": robot.stop,
    }
    return actions.get(command, robot.stop)()


def build_runtime():
    if RUN_MODE not in VALID_RUN_MODES:
        valid = ", ".join(sorted(VALID_RUN_MODES))
        raise ValueError(f"PDI_MODE inválido: {RUN_MODE}. use: {valid}")

    if RUN_MODE == "gateway":
        source = CameraViewer(GATEWAY_STREAM_URL)
        robot = GatewayRobotClient(
            gateway_host=GATEWAY_HOST,
            control_port=GATEWAY_CONTROL_PORT,
            session_token=SESSION_TOKEN,
            send_hz=CONTROL_SEND_HZ,
            packet_repeats=CONTROL_PACKET_REPEATS,
            angular_sign=CONTROL_ANGULAR_SIGN,
            command_timeout_sec=CONTROL_COMMAND_TIMEOUT_SEC,
        )
        source_description = GATEWAY_STREAM_URL
        control_description = f"{GATEWAY_HOST}:{GATEWAY_CONTROL_PORT}"
        control_enabled = True
        return source, robot, source_description, control_description, control_enabled

    if RUN_MODE == "robot":
        source = CameraViewer(ROBOT_CAMERA_URL)
        robot = RobotClient(
            robot_ip=ROBOT_IP,
            udp_port=ROBOT_UDP_PORT,
            send_hz=CONTROL_SEND_HZ,
            packet_repeats=CONTROL_PACKET_REPEATS,
            angular_sign=CONTROL_ANGULAR_SIGN,
            command_timeout_sec=CONTROL_COMMAND_TIMEOUT_SEC,
        )
        source_description = ROBOT_CAMERA_URL
        control_description = f"{ROBOT_IP}:{ROBOT_UDP_PORT}"
        control_enabled = True
        return source, robot, source_description, control_description, control_enabled

    if not MEDIA_SOURCE:
        raise ValueError(
            "PDI_MEDIA_SOURCE precisa apontar para uma imagem ou vídeo quando PDI_MODE=video"
        )

    source = MediaFileSource(MEDIA_SOURCE, loop=MEDIA_LOOP)
    robot = NullRobotClient()
    source_description = MEDIA_SOURCE
    control_description = "desativado"
    control_enabled = False
    return source, robot, source_description, control_description, control_enabled


def main():
    configure_logging()
    logger.info("iniciando pdi student console v%s", APP_VERSION)
    logger.info("modo: %s", RUN_MODE)

    source, robot, source_description, control_description, control_enabled = build_runtime()
    logger.info("fonte: %s", source_description)
    logger.info("controle: %s", control_description)

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption(f"pdi student console v{APP_VERSION}")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("monospace", 24)
    small_font = pygame.font.SysFont("monospace", 16)
    tiny_font = pygame.font.SysFont("monospace", 14)

    speed = DEFAULT_SPEED
    flash_enabled = False
    running = True
    processing_error = None
    processing_ms = 0.0
    last_processing_log = 0.0
    processing_settings = ProcessingSettings()
    recent_frames = deque(maxlen=MAX_STATIC_FRAMES)
    last_frame_number = None
    last_stream_revision = None
    processing_key = None
    processed_frame = None
    pdi_controls = PDIControls()
    video_timeline = VideoTimeline() if RUN_MODE == "video" else None
    mode_keys = {pygame.K_0 + index: mode for index, mode in enumerate(MODES)}
    original_image_rect = None
    processed_image_rect = None

    robot.set_speed(speed)
    robot.set_flash(FLASH_OFF_VALUE)
    robot.stop()

    try:
        while running:
            clock.tick(FPS)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    continue
                if video_timeline and video_timeline.handle_event(event, source):
                    continue
                if pdi_controls.handle_event(event, processing_settings,
                                             original_image_rect, processed_image_rect):
                    if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                        logger.info("PDI: %s + %s; ajustando %s: %s; espelhar: %s",
                                    MODE_NAMES[processing_settings.mode],
                                    NOISE_NAMES[processing_settings.noise_mode],
                                    processing_settings.focus,
                                    processing_settings.parameter_labels(),
                                    processing_settings.mirror)
                    continue
                if event.type != pygame.KEYDOWN:
                    continue

                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in mode_keys:
                    processing_settings.mode = mode_keys[event.key]
                    processing_settings.focus = "base"
                    logger.info("PDI: %s", MODE_NAMES[processing_settings.mode])
                elif event.key == pygame.K_m:
                    processing_settings.mirror = not processing_settings.mirror
                    logger.info("espelhamento: %s", processing_settings.mirror)
                elif event.key in (pygame.K_q, pygame.K_e, pygame.K_z, pygame.K_c):
                    parameter = 1 if event.key in (pygame.K_q, pygame.K_e) else 2
                    direction = -1 if event.key in (pygame.K_q, pygame.K_z) else 1
                    processing_settings.adjust(parameter, direction)
                    logger.info("parâmetros PDI: %s", processing_settings.parameter_labels())
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    speed = min(MAX_SPEED, speed + SPEED_STEP)
                    robot.set_speed(speed)
                    logger.info("velocidade manual: %s", speed)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    speed = max(MIN_SPEED, speed - SPEED_STEP)
                    robot.set_speed(speed)
                    logger.info("velocidade manual: %s", speed)
                elif event.key == pygame.K_l and control_enabled:
                    flash_enabled = not flash_enabled
                    robot.set_flash(FLASH_ON_VALUE if flash_enabled else FLASH_OFF_VALUE)
                    logger.info("flash: %s", "on" if flash_enabled else "off")

            keys = pygame.key.get_pressed()
            holding_stop = keys[pygame.K_SPACE]
            command = get_manual_command(keys) if control_enabled and not holding_stop else "stop"
            if command == "stop":
                send_robot_command(robot, command)

            input_frame, frame_number, stream_revision = source.read_frame_snapshot()
            accumulate = (not control_enabled or holding_stop) and (
                processing_settings.noise_mode == "estatico"
                and processing_settings.static_frames > 1
            )
            if (not accumulate or input_frame is None or stream_revision != last_stream_revision
                    or (recent_frames and recent_frames[-1].shape != input_frame.shape)):
                recent_frames.clear()
            if accumulate and input_frame is not None and frame_number != last_frame_number:
                recent_frames.append(input_frame)
            last_frame_number = frame_number
            last_stream_revision = stream_revision
            settings_key = tuple(value for name, value in vars(processing_settings).items()
                                 if name not in ("focus", "marked_objects"))
            key = (stream_revision, frame_number, len(recent_frames), settings_key)
            if input_frame is None:
                processing_key = None
                processed_frame = None
                processing_error = None

            if input_frame is not None and key != processing_key:
                started_at = time.perf_counter()
                processed_frame = None
                processing_error = None
                try:
                    processed_frame = process_frame(input_frame, processing_settings,
                                                    recent_frames=tuple(recent_frames))
                    if processed_frame is None:
                        raise ValueError("process_frame retornou none")
                    processing_key = key
                except Exception as exc:
                    processing_key = None
                    processing_error = str(exc)
                    now = time.monotonic()
                    if now - last_processing_log >= 2.0:
                        logger.exception("falha no pipeline de processamento")
                        last_processing_log = now
                finally:
                    processing_ms = (time.perf_counter() - started_at) * 1000.0

            if command != "stop":
                if processed_frame is None:
                    command = "stop"
                send_robot_command(robot, command)

            robot_status = robot.get_status()
            source_status = source.get_status()

            screen.fill((18, 18, 18))
            draw_text(screen, f"pdi student console v{APP_VERSION}", 20, 20, font)
            draw_text(
                screen,
                f"modo: {MODE_LABELS[RUN_MODE]}",
                20,
                58,
                small_font,
                color=(120, 255, 120),
            )

            draw_text(screen, "fonte", 20, 100, small_font)
            draw_text(screen, source_description[:31], 20, 126, tiny_font)
            draw_text(
                screen,
                f"stream: {'ok' if source_status['opened'] else 'sem frame'}",
                20,
                148,
                tiny_font,
            )
            draw_text(screen, f"frames: {source_status['frames_received']}", 20, 170, tiny_font)
            draw_text(screen, f"reconexões: {source_status['reconnects']}", 20, 192, tiny_font)
            draw_text(screen, f"pipeline: {processing_ms:.1f} ms", 20, 214, tiny_font)
            if processing_settings.noise_mode == "estatico" and processing_settings.static_frames > 1:
                target = processing_settings.static_frames
                capture_label = (f"quadros NLM: {min(len(recent_frames), target)}/{target}"
                                 if accumulate else "segure ESPAÇO para acumular")
                draw_text(screen, capture_label,
                          20, 236, tiny_font)

            draw_text(screen, "controle", 20, 258, small_font)
            draw_text(screen, control_description[:35], 20, 284, tiny_font)
            draw_text(screen, f"velocidade: {speed}", 20, 306, tiny_font)
            draw_text(screen, f"comando: {command}", 20, 328, tiny_font)
            draw_text(
                screen,
                f"flash: {'on' if flash_enabled else 'off'}" if control_enabled else "flash: n/a",
                20,
                350,
                tiny_font,
            )

            draw_text(screen, "comunicação", 20, 394, small_font)
            udp_color = (120, 255, 120) if robot_status["send_errors"] == 0 else (255, 180, 120)
            draw_text(screen, f"pacotes: {robot_status['packets_sent']}", 20, 420, tiny_font, udp_color)
            draw_text(screen, f"erros udp: {robot_status['send_errors']}", 20, 442, tiny_font, udp_color)
            draw_text(
                screen,
                f"fail-safe: {'ativo' if robot_status['failsafe_active'] else 'normal'}",
                20,
                464,
                tiny_font,
                (255, 180, 120) if robot_status["failsafe_active"] else (120, 255, 120),
            )

            draw_text(screen, "controles", 20, 518, small_font)
            if control_enabled:
                draw_text(screen, "wasd / setas: mover", 20, 544, tiny_font)
                draw_text(screen, "espaço: parar", 20, 566, tiny_font)
                draw_text(screen, "+ / -: velocidade", 20, 588, tiny_font)
                draw_text(screen, "l: flash", 20, 610, tiny_font)
            else:
                draw_text(screen, "modo de mídia: sem controle", 20, 544, tiny_font)
            draw_text(screen, "esc: sair", 20, 632, tiny_font)

            if processing_error:
                draw_text(screen, "erro no pipeline", 20, 684, small_font, color=(255, 120, 120))
                draw_text(screen, processing_error[:32], 20, 710, tiny_font, color=(255, 120, 120))

            original_image_rect = draw_frame_panel(
                screen, input_frame, pygame.Rect(300, 92, 470, 390),
                "ORIGINAL", small_font, tiny_font, "aguardando frame",
            )
            pdi_controls.draw_marker_roi(screen, processing_settings, original_image_rect)
            processed_image_rect = draw_frame_panel(
                screen, processed_frame, pygame.Rect(790, 92, 470, 390),
                "MÁSCARA (BORDAS)" if processing_settings.mode == "marcadores" else "PROCESSADA",
                small_font, tiny_font,
                "erro no PDI" if processing_error else "aguardando frame",
            )
            pdi_controls.draw_marker_count(screen, processing_settings, processed_image_rect, tiny_font)

            if video_timeline:
                video_timeline.draw(screen, source, small_font)
            pdi_controls.draw(screen, processing_settings, small_font, tiny_font)

            pygame.display.flip()
    finally:
        logger.info("encerrando aplicação")
        robot.stop()
        robot.set_flash(FLASH_OFF_VALUE)
        robot.close()
        source.release()
        pygame.quit()


if __name__ == "__main__":
    main()
