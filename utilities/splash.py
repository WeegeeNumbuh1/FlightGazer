# FlightGazer splash screen
# Shows a splash screen while we wait for the main script to load
# The splash screen is designed to scroll across the screen rather than being static (because fancy)
# This is expected to only be run by the FlightGazer-init.sh script
# Additionally this file must be in the utilities directory to work properly.
# Last updated: v.6.0.0
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
CURRENT_DIR = Path(__file__).resolve().parent
try:
    try:
        from rgbmatrix import graphics
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
    except:
        os.environ['RGBME_SUPPRESS_ADAPTER_LOAD_ERRORS'] = "True"
        from RGBMatrixEmulator.emulation.options import RGBMatrixEmulatorConfig
        RGBMatrixEmulatorConfig.CONFIG_PATH = Path(f"{CURRENT_DIR}/../emulator_config.json")
        from RGBMatrixEmulator import graphics
        from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions
except: # if display can't be loaded, don't bother showing the splash screen
    sys.exit(1)
try:
    from PIL import Image
except:
    sys.exit(1)

try:
    with open(Path(f"{CURRENT_DIR}/../version"), 'rb') as f:
        VER_STR = f.read(12).decode('utf-8').strip()
except:
    VER_STR = "UNKNOWN"

def sigterm_handler(signum, frame):
    signal.signal(signum, signal.SIG_IGN)
    sys.exit(0)

NO_TEXT_SPLASH = False
try:
    loaded_font = graphics.Font()
    loaded_font.LoadFont(f"{CURRENT_DIR}/../fonts/3x3.bdf")
except FileNotFoundError:
    NO_TEXT_SPLASH = True

class ImageScroller():
    def __init__(self, *args, **kwargs):
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument("image", help="The image to display", default="FG-Splash.ppm")
        self.parser.add_argument('-u', '--update',
                      action='store_true',
                      help="Changes text to 'Now Updating' instead of the default 'Now Loading'."
                      )
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

        # Run with the following rgbmatrix options.
        # `options.hardware_mapping` is missing as we let the
        # local build of rgbmatrix use its defaults.
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
        options.pwm_bits = 8
        options.gpio_slowdown = 2
        options.drop_privileges = False
        self.matrix = RGBMatrix(options=options)

    def run(self):
        if not 'image' in self.__dict__:
            try:
                self.image = Image.open(Path(self.args.image)).convert('RGB')
            except:
                # if we can't open the image, just exit
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

            self.double_buffer = self.matrix.SwapOnVSync(self.double_buffer)
            sleep(0.04)

if __name__ == "__main__":
    try:
        image_scroller = ImageScroller()
        image_scroller.run()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)