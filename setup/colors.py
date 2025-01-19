""" Helper module to define colors for RGB-Matrix """

try:
    from rgbmatrix import graphics
except:
    from RGBMatrixEmulator import graphics

# Color helpers
BLACK = graphics.Color(0, 0, 0)
WARM_WHITE = graphics.Color(255, 230, 160)
WHITE = graphics.Color(255, 255, 255)
GREY = graphics.Color(192, 192, 192)
DARK_GREY = graphics.Color(64, 64, 64)
YELLOW = graphics.Color(255, 255, 0)
YELLOW_DARK = graphics.Color(128, 128, 0)
YELLOW_GREEN = graphics.Color(150, 255, 33)
CYAN = graphics.Color(60, 245, 255)
BLUE = graphics.Color(55, 14, 237)
BLUE_LIGHT = graphics.Color(110, 182, 255)
BLUE_DARK = graphics.Color(29, 0, 156)
BLUE_DARKER = graphics.Color(0, 0, 156/2)
PINK = graphics.Color(200, 0, 200)
PINK_DARK = graphics.Color(112, 0, 145)
PURPLE = graphics.Color(68, 0, 145)
SEA_GREEN = graphics.Color(16, 227, 114)
GREEN = graphics.Color(0, 200, 0)
GREEN_LIGHT = graphics.Color(110, 255, 110)
GREEN_DARK = graphics.Color(20, 100, 15)
ORANGE = graphics.Color(227, 110, 0)
ORANGE_DARK = graphics.Color(113, 55, 0)
RED = graphics.Color(255, 0, 0)
RED_LIGHT = graphics.Color(255, 195, 195)
