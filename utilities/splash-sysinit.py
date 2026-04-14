# FlightGazer system init splash screen
# Shows a splash screen while we wait for the system to load up.
# It's assumed that this is started very early in the boot process (right after filesystems are available).
# This file must be in the utilities directory to work properly.
# Repurposed from the original FlightGazer splash screen.
# Last updated: v.11.0.0
# By: WeegeeNumbuh1

import sys
if __name__ != '__main__':
    print("This file cannot be loaded as a module.")
    sys.exit(1)

log_prefix = 'FlightGazer boot splash: '
import signal
from time import sleep, monotonic

def sigterm_handler(signum, frame):
    signal.signal(signum, signal.SIG_IGN)
    print(f"{log_prefix}successfully stopped (SIGTERM'd). Runtime: {monotonic() - starttime:.3f} seconds.")
    sys.exit(0)

signal.signal(signal.SIGTERM, sigterm_handler)
print(f"{log_prefix}Firing up...")
starttime = monotonic()
print(f"{log_prefix}Script start: about {starttime:.1f} seconds after system start")
from pathlib import Path
import os
import threading
import subprocess
from collections import deque
os.environ["PYTHONUNBUFFERED"] = "1"
CURRENT_DIR = Path(__file__).resolve().parent

try:
    result = subprocess.run(['systemctl', 'is-active', 'flightgazer'], capture_output=True, text=True)
    cmd = "ps aux | grep '[F]lightGazer\\.py' | awk '{print $2}'"
    result2 = subprocess.check_output(cmd, shell=True).strip().decode()
    if result.returncode == 0 and result.stdout.strip() == 'active' or result2:
        print(f"{log_prefix}ERROR: FlightGazer main service is already running.")
        sys.exit(1)
except Exception:
    print(f"{log_prefix}ERROR: Could not determine running state of the system.")
    print(f"{log_prefix}Splash screen will not run.")
    sys.exit(1)

if os.name != 'nt':
    try:
        PATH_OWNER = CURRENT_DIR.owner()
        OWNER_HOME = os.path.expanduser(f"~{PATH_OWNER}")
    except Exception:
        PATH_OWNER = None
        OWNER_HOME = Path.home()
else:
    PATH_OWNER = None
    OWNER_HOME = Path.home()

emu_settings = Path(CURRENT_DIR, '..', 'emulator_config.json')
SERVICE_PATH = Path('/etc/systemd/system/flightgazer.service')
use_emulator = False
adapter = None
if emu_settings.is_file():
    with open(emu_settings, 'r') as f:
        for line in f:
            if '"display_adapter":' in line.strip():
                adapter = line.strip()
                break
serv_lines = ''
if SERVICE_PATH.is_file():
    try:
        with open(SERVICE_PATH, 'r', encoding='utf-8') as f:
            serv_lines = f.readlines()
    except Exception:
        serv_lines = ''
exec_line = ''
for line in serv_lines:
    if line.strip().startswith('ExecStart='):
        exec_line = line.strip()
if exec_line and ' -e' in exec_line and adapter and 'pi5' in adapter:
    use_emulator = True

if not use_emulator:
    try:
        try:
            from rgbmatrix import graphics
            from rgbmatrix import RGBMatrix, RGBMatrixOptions
        except ImportError:
            # handle case when rgbmatrix is not installed and maybe is present in the home directory
            if (RGBMATRIX_DIR := Path(OWNER_HOME, "rpi-rgb-led-matrix")).exists():
                sys.path.append(Path(RGBMATRIX_DIR, 'bindings', 'python'))
                from rgbmatrix import graphics
                from rgbmatrix import RGBMatrix, RGBMatrixOptions

    except Exception: # if the hardware display can't be loaded, don't bother showing the splash screen
        print(f"{log_prefix}ERROR: No display driver found. Splash screen is unavailable.")
        sys.exit(1)
else:
    try:
        os.environ['RGBME_SUPPRESS_ADAPTER_LOAD_ERRORS'] = "True"
        from RGBMatrixEmulator.emulation.options import RGBMatrixEmulatorConfig
        RGBMatrixEmulatorConfig.CONFIG_PATH = emu_settings
        from RGBMatrixEmulator import graphics
        from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions
    except ImportError:
        print(f"{log_prefix}ERROR: Failed to load emulator. Splash screen is unavailable.")
        sys.exit(1)

if use_emulator:
    print(f"{log_prefix}Using the Emulator with the Raspberry Pi5 mode.")

# debugging stuff
# os.environ['RGBME_SUPPRESS_ADAPTER_LOAD_ERRORS'] = "True"
# from RGBMatrixEmulator.emulation.options import RGBMatrixEmulatorConfig
# RGBMatrixEmulatorConfig.CONFIG_PATH = emu_settings
# from RGBMatrixEmulator import graphics
# from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions

try:
    from ruamel.yaml import YAML
    yaml = YAML()
    can_load_config = True
except ImportError:
    can_load_config = False

config_default = {
    'GPIO_SLOWDOWN': 2,
    'HAT_PWM_ENABLED': True,
    'LED_PWM_BITS': 8,
}
if (CONFIG_FILE := Path(CURRENT_DIR, '..', 'config.yaml')).exists() and can_load_config:
    try:
        config = yaml.load(open(CONFIG_FILE, 'r'))
    except Exception:
        config = None

    if config:
        for key in config_default:
            if (key not in config
                or type(config[key]) != type(config_default[key])
                or config[key] is None
            ):
                config[key] = config_default[key]
    else:
        config = config_default
else:
    config = config_default

NO_TEXT_SPLASH = False
try:
    loaded_font = graphics.Font()
    loaded_font_2 = graphics.Font()
    loaded_font.LoadFont(f"{CURRENT_DIR}/../fonts/3x3.bdf")
    loaded_font_2.LoadFont(f"{CURRENT_DIR}/../fonts/4x5.bdf")
except FileNotFoundError:
    print(f"{log_prefix}ERROR: Could not find font files.")
    print(f"{log_prefix}This isn't good. This means FlightGazer may not load either.")
    sys.exit(1)

def hue2rgb(norm: float) -> tuple[int, int, int]:
    """ Given a normalized hue angle (0 = 0, 1 = 360 deg) and assuming 100% saturation,
    returns a tuple of 8 bit RGB values.
    Derived from https://en.wikipedia.org/wiki/HSL_and_HSV#HSV_to_RGB_alternative """
    rp = (5 + norm * 6) % 6
    gp = (3 + norm * 6) % 6
    bp = (1 + norm * 6) % 6
    r = 1 - max(min(rp, 4 - rp, 1), 0)
    g = 1 - max(min(gp, 4 - gp, 1), 0)
    b = 1 - max(min(bp, 4 - bp, 1), 0)

    return round(r * 255), round(g * 255), round(b * 255)

TIMING_CONTROL = 0
def timing():
    global TIMING_CONTROL
    wait_time = 60
    sleep(wait_time)
    TIMING_CONTROL = 1
    print(f"{log_prefix}{wait_time} seconds have passed since this has started.")
    print(f"{log_prefix}Assuming we have not reached multi-user.target yet.")

threading.Thread(target=timing, daemon=True).start()

class SplashText():
    def __init__(self):
        self.top_text_color_dir = True # true = fade in, false = fade out
        self.spinner = ['◥', '◢', '◣', '◤',]
        self.spinner_index = 0

        # Run with the following rgbmatrix options.
        # nb: If these settings end up not working, then we simply won't have a splash screen
        #     which is not a huge issue.
        options = RGBMatrixOptions()
        options.rows = 32
        options.cols = 64
        options.chain_length = 1
        options.parallel = 1
        options.row_address_type = 0
        options.multiplexing = 0
        options.pwm_lsb_nanoseconds = 130
        options.led_rgb_sequence = "RGB"
        options.pixel_mapper_config = ""
        options.show_refresh_rate = 0
        options.pwm_bits = config['LED_PWM_BITS']
        options.gpio_slowdown = config['GPIO_SLOWDOWN']
        options.brightness = 100
        options.drop_privileges = False
        options.hardware_mapping = "adafruit-hat-pwm" if config['HAT_PWM_ENABLED'] else "adafruit-hat"
        options.disable_hardware_pulsing = False if config['HAT_PWM_ENABLED'] else True
        self.matrix = RGBMatrix(options=options)

    def run(self):

        self.double_buffer = self.matrix.CreateFrameCanvas()
        _skip_frames = 0

        # generate the color array for the progress bar
        c_spectrum = deque()
        for i in range(self.matrix.width):
            c_spectrum.append(
                hue2rgb((i + 1) / self.matrix.width)
            )
        undraw_starting = False

        print(f"{log_prefix}successfully started after {monotonic() - starttime:.3f} seconds.")
        while True:
            # the fade effect
            if TIMING_CONTROL < 1:
                delta = 5
            else:
                delta = 1
            if self.top_text_color_dir:
                commanded_brightness = self.matrix.brightness + delta
                if commanded_brightness >= 100:
                    self.matrix.brightness = 100
                    self.top_text_color_dir = False
                else:
                    self.matrix.brightness += delta
            else:
                commanded_brightness = self.matrix.brightness - delta
                if commanded_brightness <= 0:
                    self.matrix.brightness = 0
                    self.top_text_color_dir = True
                else:
                    self.matrix.brightness -= delta

            # rainbow loading bar at the bottom
            for i, pt in enumerate(c_spectrum):
                self.double_buffer.SetPixel(
                    i, 31, pt[0], pt[1], pt[2]
                )

            if TIMING_CONTROL < 1:
                c_spectrum.rotate(1)
            else:
                # slow down the animation but keep the frame rate
                _skip_frames += 1
                if _skip_frames % 3 == 0:
                    c_spectrum.rotate(1)
                    # the old spinner logic (kept here)
                    # self.spinner_index += 1
                    # if self.spinner_index >= len(self.spinner):
                    #     self.spinner_index = 0
                    _skip_frames = 0

            if TIMING_CONTROL >= 1 and not NO_TEXT_SPLASH:
                _ = graphics.DrawText(
                    self.double_buffer,
                    loaded_font,
                    19,
                    27,
                    graphics.Color(227, 110, 0),
                    "WAITING",
                )

                _ = graphics.DrawText(
                    self.double_buffer,
                    loaded_font,
                    11,
                    31,
                    graphics.Color(227, 110, 0),
                    "TO CONTINUE",
                )

            _ = graphics.DrawText(
                self.double_buffer,
                loaded_font_2,
                19,
                6,
                graphics.Color(
                    255, 255, 255
                ),
                "SYSTEM",
            )

            if TIMING_CONTROL < 1:
                _ = graphics.DrawText(
                    self.double_buffer,
                    loaded_font_2,
                    16,
                    12,
                    graphics.Color(
                        255, 255, 255
                    ),
                    "STARTING",
                )
            else:
                # undraw
                if not undraw_starting:
                    # do this once
                    _ = graphics.DrawText(
                        self.double_buffer,
                        loaded_font_2,
                        16,
                        12,
                        graphics.Color(
                            0, 0, 0
                        ),
                        "STARTING",
                    )
                    undraw_starting = True

                _ = graphics.DrawText(
                    self.double_buffer,
                    loaded_font_2,
                    21,
                    12,
                    graphics.Color(
                        255, 255, 255
                    ),
                    "READY",
                )

            self.double_buffer = self.matrix.SwapOnVSync(self.double_buffer)
            sleep(0.04)

if __name__ == "__main__":
    try:
        image_scroller = SplashText()
        image_scroller.run()
    except KeyboardInterrupt:
        print(f"{log_prefix}successfully stopped. Runtime: {monotonic() - starttime:.3f} seconds")
        sys.exit(0)