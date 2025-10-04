# FlightGazer system init splash screen
# Shows a splash screen while we wait for the system to load up.
# Requires that the rgb-matrix library is present and it's assumed that this
# is started very early in the boot process (right after filesystems are available).
# This file must be in the utilities directory to work properly.
# Repurposed from the original FlightGazer splash screen.
# Last updated: v.8.3.0
# By: WeegeeNumbuh1

import sys
if __name__ != '__main__':
    print("This file cannot be loaded as a module.")
    sys.exit(1)

import signal

def sigterm_handler(signum, frame):
    signal.signal(signum, signal.SIG_IGN)
    print("FlightGazer boot splash screen: successfully stopped.")
    sys.exit(0)

signal.signal(signal.SIGTERM, sigterm_handler)
from time import sleep
from pathlib import Path
import os
import threading
import subprocess
os.environ["PYTHONUNBUFFERED"] = "1"
CURRENT_DIR = Path(__file__).resolve().parent
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
    print("FlightGazer boot splash screen: ERROR: No display driver found. Splash screen is not available.")
    sys.exit(1)

# debugging stuff
# os.environ['RGBME_SUPPRESS_ADAPTER_LOAD_ERRORS'] = "True"
# from RGBMatrixEmulator.emulation.options import RGBMatrixEmulatorConfig
# RGBMatrixEmulatorConfig.CONFIG_PATH = Path(CURRENT_DIR, '..', 'emulator_config.json')
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

try:
    result = subprocess.run(['systemctl', 'is-active', 'flightgazer'], capture_output=True, text=True)
    cmd = "ps aux | grep '[F]lightGazer\.py' | awk '{print $2}'"
    result2 = subprocess.check_output(cmd, shell=True).strip().decode()
    if result.returncode == 0 and result.stdout.strip() == 'active' or result2:
        print("FlightGazer boot splash screen: ERROR: FlightGazer main service is already running.")
        sys.exit(1)
except Exception:
    print("FlightGazer boot splash screen: ERROR: Could not determine running state of the system.")
    print("FlightGazer boot splash screen: Splash screen will not run.")
    sys.exit(1)

NO_TEXT_SPLASH = False
try:
    loaded_font = graphics.Font()
    loaded_font_2 = graphics.Font()
    loaded_font.LoadFont(f"{CURRENT_DIR}/../fonts/3x3.bdf")
    loaded_font_2.LoadFont(f"{CURRENT_DIR}/../fonts/4x5.bdf")
except FileNotFoundError:
    print("FlightGazer boot splash screen: ERROR: Could not find font files.")
    print("FlightGazer boot splash screen: This isn't good. This means FlightGazer may not load either.")
    sys.exit(1)

TIMING_CONTROL = 0
def timing():
    global TIMING_CONTROL
    sleep(20)
    TIMING_CONTROL = 1
    sleep(10)
    TIMING_CONTROL = 2
    print("FlightGazer boot splash screen: 30 seconds have passed since this has started.")
    print("FlightGazer boot splash screen: Assuming we have not reached multi-user.target yet.")

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
        print("FlightGazer boot splash screen: successfully started.")

        _skip_frames = 0
        while True:
            # the fade effect
            if TIMING_CONTROL < 2:
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
            # spinner effect
            _skip_frames += 1
            if _skip_frames % 3 == 0:
                self.spinner_index += 1
                if self.spinner_index >= len(self.spinner):
                    self.spinner_index = 0
                _skip_frames = 0

            if TIMING_CONTROL >= 2 and not NO_TEXT_SPLASH:
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

            if TIMING_CONTROL < 2:
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

            # _ = graphics.DrawText(
            #     self.double_buffer,
            #     loaded_font,
            #     15,
            #     27,
            #     graphics.Color(
            #         self.matrix.brightness,
            #         self.matrix.brightness,
            #         self.matrix.brightness
            #     ),
            #     self.spinner[self.spinner_index],
            # )

            self.double_buffer = self.matrix.SwapOnVSync(self.double_buffer)
            sleep(0.04)

if __name__ == "__main__":
    try:
        image_scroller = SplashText()
        image_scroller.run()
    except (KeyboardInterrupt, SystemExit):
        print("FlightGazer boot splash screen: successfully stopped.")
        sys.exit(0)