""" Helper module to define fonts for RGB-Matrix """

import os
try:
    from rgbmatrix import graphics
except:
    from RGBMatrixEmulator import graphics

# Fonts
DIR_PATH = os.path.dirname(os.path.realpath(__file__))
microscopic = graphics.Font()
""" 3x3 """
smallest = graphics.Font()
""" 3x5 """
smallest_alt = graphics.Font()
""" 3x5 """
extrasmall = graphics.Font()
""" 4x4 """
small = graphics.Font()
""" 4x5 """
regular = graphics.Font()
""" 6x12 """
regularplus = graphics.Font()
""" 6x13 """
large = graphics.Font()
""" 8x13 """
large_bold = graphics.Font()
""" 8x13 """
microscopic.LoadFont(f"{DIR_PATH}/../fonts/3x3.bdf")
smallest.LoadFont(f"{DIR_PATH}/../fonts/3x5.bdf")
smallest_alt.LoadFont(f"{DIR_PATH}/../fonts/3x5_alt.bdf")
extrasmall.LoadFont(f"{DIR_PATH}/../fonts/4x4.bdf")
small.LoadFont(f"{DIR_PATH}/../fonts/4x5.bdf")
regular.LoadFont(f"{DIR_PATH}/../fonts/6x12.bdf")
regularplus.LoadFont(f"{DIR_PATH}/../fonts/6x13.bdf")
large.LoadFont(f"{DIR_PATH}/../fonts/8x13.bdf")
large_bold.LoadFont(f"{DIR_PATH}/../fonts/8x13B.bdf")