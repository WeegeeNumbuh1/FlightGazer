# FlightGazer splash screen
# Shows a splash screen while we wait for the main script to load
# The splash screen is designed to scroll across the screen rather than being static (because fancy)
# This is expected to only be run by the FlightGazer-init.sh script
# Additionally this file must be in the utilities directory to work properly.
# Last updated: v.11.0.0
# By: WeegeeNumbuh1

import sys
if __name__ != '__main__':
    print("This file cannot be loaded as a module.")
    sys.exit(1)
from time import sleep
import signal
import argparse
from pathlib import Path
import os
import threading
CURRENT_DIR = Path(__file__).resolve().parent
INIT_PROGRESS_FILE = Path('/run/FlightGazer/init_progress')
init_progress_percentage = 0
args_main = argparse.ArgumentParser()
args_main.add_argument("image",
                help="The image to display",
                default=f"{Path(CURRENT_DIR, '..', 'FG-Splash.ppm')}"
                )
args_main.add_argument('-u', '--update',
                action='store_true',
                help="Changes text to 'Now Updating' instead of the default 'Now Loading'."
                )
args_main.add_argument('-e', '--emulate',
                action='store_true',
                help="Use the emulator instead of rgbmatrix."
                )
args_init = args_main.parse_args()
if args_init.emulate:
    EMULATE_DISPLAY: bool = True
else:
    EMULATE_DISPLAY = False

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
    if not EMULATE_DISPLAY:
        try:
            from rgbmatrix import graphics
            from rgbmatrix import RGBMatrix, RGBMatrixOptions
        except ImportError:
            # handle case when rgbmatrix is not installed and maybe is present in the home directory
            if (RGBMATRIX_DIR := Path(OWNER_HOME, "rpi-rgb-led-matrix")).exists:
                sys.path.append(Path(RGBMATRIX_DIR, 'bindings', 'python'))
                try:
                    from rgbmatrix import graphics
                    from rgbmatrix import RGBMatrix, RGBMatrixOptions
                except ImportError:
                    EMULATE_DISPLAY = True
    if EMULATE_DISPLAY:
        os.environ['RGBME_SUPPRESS_ADAPTER_LOAD_ERRORS'] = "True"
        from RGBMatrixEmulator.emulation.options import RGBMatrixEmulatorConfig
        RGBMatrixEmulatorConfig.CONFIG_PATH = Path(CURRENT_DIR, '..', 'emulator_config.json')
        from RGBMatrixEmulator import graphics
        from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions
except Exception: # if display can't be loaded, don't bother showing the splash screen
    print("FG-Splash: Error: No display driver found. Splash screen is not available.")
    sys.exit(1)
try:
    from PIL import Image
except Exception:
    print("FG-Splash: Error: PIL (Pillow) library not found. Splash screen is not available.")
    sys.exit(1)

try:
    from ruamel.yaml import YAML
    yaml = YAML()
    can_load_config = True
except ImportError:
    can_load_config = False

try:
    with open(Path(CURRENT_DIR, '..', 'version'), 'rb') as f:
        VER_STR = f.read(12).decode('utf-8').strip()
except Exception:
    VER_STR = "UNKNOWN"

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

def sigterm_handler(signum, frame):
    signal.signal(signum, signal.SIG_IGN)
    sys.exit(0)

def check_progress():
    """ Check the initialization progress file when running an update. """
    global init_progress_percentage
    if INIT_PROGRESS_FILE.is_file():
        try:
            with open(INIT_PROGRESS_FILE, 'rb') as fi:
                right_now = fi.read(5).decode('utf-8').strip()
                # note, further calculations can handle float
                if not right_now:
                    init_progress_percentage = 0
                else:
                    init_progress_percentage = float(right_now)
        except Exception:
            pass
def progress_checker():
    while True:
        check_progress()
        sleep(0.5)

NO_TEXT_SPLASH = False
try:
    loaded_font = graphics.Font()
    loaded_font.LoadFont(f"{CURRENT_DIR}/../fonts/3x3.bdf")
except FileNotFoundError:
    NO_TEXT_SPLASH = True

class ImageScroller():
    def __init__(self, *args, **kwargs):
        self.parser = args_main
        self.args = self.parser.parse_args()
        signal.signal(signal.SIGTERM, sigterm_handler) # register signal handler
        if self.args.update:
            self.top_text = "NOW UPDATING"
        else:
            self.top_text = "NOW LOADING"
        self.top_text_len = 0
        self.top_text_color_control = 0 # do a nifty fade effect
        self.top_text_color_dir = True # true = fade in, false = fade out
        # self.spinner = ['|', '/', '-', '\\'] # spinner for the text
        self.spinner = ['◥', '◢', '◣', '◤',]
        self.spinner_index = 0
        self.progress_color = graphics.Color(227, 110, 0) # orange, like Rin Hoshizora or Matikanefukukitaru

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

    def draw_line(self, canvas, x_start:int, y_start:int, color, count:int):
        """ Pulled from FlightGazer """
        if count is None:
            count = 0
        if count > self.matrix.width:
            count = self.matrix.width
        indicator_color = color
        for i in range(count):
            canvas.SetPixel(
                x_start + i,
                y_start,
                indicator_color.red,
                indicator_color.green,
                indicator_color.blue
            )

    def run(self):
        if not 'image' in self.__dict__:
            try:
                self.image = Image.open(Path(self.args.image)).convert('RGB')
            except Exception:
                # if we can't open the image, just exit
                print(f"FG-Splash: Error: Could not open image '{self.args.image}'. Please check the file path and format.")
                sys.exit(1)
        self.image = self.image.resize([self.matrix.width, self.matrix.height])

        self.double_buffer = self.matrix.CreateFrameCanvas()
        img_width, img_height = self.image.size

        # let's scroll
        xpos = 0
        _skip_frames = 0
        while True:
            xpos += 1
            if (xpos >= img_width):
                xpos = 0

            # the fade effect
            if self.top_text_color_dir:
                self.top_text_color_control += 10
                if self.top_text_color_control >= 255:
                    self.top_text_color_control = 255
                    self.top_text_color_dir = False
            else:
                self.top_text_color_control -= 10
                if self.top_text_color_control <= 0:
                    self.top_text_color_control = 0
                    self.top_text_color_dir = True
            # spinner effect
            _skip_frames += 1
            if _skip_frames % 3 == 0:
                self.spinner_index += 1
                if self.spinner_index >= len(self.spinner):
                    self.spinner_index = 0
                _skip_frames = 0

            # scrolls to the right
            self.double_buffer.SetImage(self.image, xpos)
            self.double_buffer.SetImage(self.image, xpos - img_width)

            # calculate the progress bar length
            fill_length = int(
                round((init_progress_percentage / 100) * self.matrix.width, 0)
            )

            if not NO_TEXT_SPLASH:
                _ = graphics.DrawText(
                    self.double_buffer,
                    loaded_font,
                    1,
                    31,
                    graphics.Color(30, 30, 30),
                    f"VER:{VER_STR}",
                )

                self.top_text_len = graphics.DrawText(
                    self.double_buffer,
                    loaded_font,
                    (self.double_buffer.width - self.top_text_len),
                    4,
                    graphics.Color(
                        self.top_text_color_control,
                        self.top_text_color_control,
                        self.top_text_color_control
                    ),
                    self.top_text,
                )

                _ = graphics.DrawText(
                    self.double_buffer,
                    loaded_font,
                    1,
                    4,
                    graphics.Color(
                        self.top_text_color_control,
                        self.top_text_color_control,
                        self.top_text_color_control
                    ),
                    self.spinner[self.spinner_index],
                )

            if self.args.update:
                self.draw_line(self.double_buffer, 0, 31, self.progress_color, fill_length)
            self.double_buffer = self.matrix.SwapOnVSync(self.double_buffer)
            sleep(0.04)

if __name__ == "__main__":
    try:
        threading.Thread(target=progress_checker, daemon=True).start()
        image_scroller = ImageScroller()
        image_scroller.run()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)