""" FlightGazer color settings module """

"""
VERSION: v.7.1.1
How to modify colors:

If you are using the predefined colors, simply use the name of the color.
The name is also case-sensitive.
->  Example:
    setting = BLACK
If you are using your own custom color, you must use 'graphics.Color(red, green, blue)'
where the red, green, blue values are integers from 0 to 255.
->  Example:
    setting = graphics.Color(123, 123, 123)

Your edits must be between the # CONFIG_START and # CONFIG_END
lines as these settings are what will be copied over when using the updater.

Warnings:
- Do not remove settings as this will cause the display to not load.
- Do not change the amount of lines in this file; this will cause the updater to
default to the original colors.
"""

try:
    try:
        from rgbmatrix import graphics
    except (ModuleNotFoundError, ImportError):
        from RGBMatrixEmulator import graphics
except (ModuleNotFoundError, ImportError):
    raise NotImplementedError

# Color helpers
BLACK = graphics.Color(0, 0, 0)
WARM_WHITE = graphics.Color(255, 230, 160)
COOL_WHITE = graphics.Color(168, 196, 255)
WHITE = graphics.Color(255, 255, 255)
GREY = graphics.Color(160, 160, 160)
DARK_GREY = graphics.Color(64, 64, 64)
FAINT = graphics.Color(30, 30, 30)
RED = graphics.Color(255, 0, 0)
RED_LIGHT = graphics.Color(255, 195, 195)
RED_DARK = graphics.Color(150, 12, 12)
PEACH_ORANGE = graphics.Color(255, 185, 120)
ORANGE = graphics.Color(227, 110, 0)
ORANGE_DARK = graphics.Color(135, 52, 0)
BROWN = graphics.Color(160, 75, 10)
YELLOW_ORANGE = graphics.Color(245, 193, 7)
YELLOW = graphics.Color(255, 255, 0)
YELLOW_DARK = graphics.Color(128, 128, 0)
YELLOW_GREEN = graphics.Color(150, 255, 33)
OLIVE_GREEN = graphics.Color(61, 85, 12)
GREEN = graphics.Color(0, 200, 0)
GREEN_LIGHT = graphics.Color(110, 255, 110)
GREEN_DARK = graphics.Color(20, 100, 15)
GREEN_PURE = graphics.Color(0, 255, 0)
SEAFOAM_GREEN = graphics.Color(16, 227, 114)
CYAN = graphics.Color(60, 245, 255)
CYAN_DARK = graphics.Color(8, 131, 138)
BLUE = graphics.Color(0, 80, 255)
BLUE_LIGHT = graphics.Color(110, 182, 255)
BLUE_DARK = graphics.Color(0, 40, 170)
BLUE_DARKER = graphics.Color(18, 20, 105)
BLUE_PURE = graphics.Color(0, 0, 255)
SAKURA_PINK = graphics.Color(255, 145, 176)
PINK = graphics.Color(251, 83, 114)
MAGENTA = graphics.Color(200, 0, 200)
PURPLE_DARK = graphics.Color(68, 0, 145)
PURPLE = graphics.Color(128, 0, 255)
GRAPE_PURPLE = graphics.Color(112, 0, 145)

# CONFIG_START
# ============ Clock Colors =============
# =======================================
clock_color = WARM_WHITE
seconds_color = WARM_WHITE
am_pm_color = ORANGE_DARK
day_of_week_color = GRAPE_PURPLE
date_color = PURPLE

# stats at the bottom
flyby_header_color = BLUE_DARK
flyby_color = BLUE
track_header_color = GREEN_DARK
track_color = GREEN
range_header_color = YELLOW_DARK
range_color = YELLOW

# clock center row
center_row1_color = DARK_GREY
center_row2_color = DARK_GREY

# ======== Plane Readout Colors =========
# =======================================

# header
callsign_color = WHITE
distance_color = WARM_WHITE
country_color = GREY
uat_indicator_color = SEAFOAM_GREEN

# journey colors
origin_color = ORANGE
destination_color = ORANGE
arrow_color = ORANGE

# journey plus colors
time_header_color = GRAPE_PURPLE
time_readout_color = PURPLE
center_readout_color = DARK_GREY

# enhanced readout colors
latitude_color = ORANGE
longitude_color = ORANGE
groundtrack_color = GRAPE_PURPLE
verticalspeed_color = PURPLE_DARK

# scrolling info line
# (overrides journey plus "center_readout_color" when
# SHOW_EVEN_MORE_INFO setting is enabled)
marquee_color_journey_plus = SAKURA_PINK
marquee_color_enhanced_readout = SAKURA_PINK

# stats at the bottom
altitude_heading_color = BLUE_DARK
altitude_color = BLUE
speed_heading_color = GREEN_DARK
speed_color = GREEN
time_rssi_heading_color = YELLOW_DARK
time_rssi_color = YELLOW

# plane count indicator
plane_count_color = RED
switch_progress_color = FAINT

# CONFIG_END