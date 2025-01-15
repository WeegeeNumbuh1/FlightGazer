''' Configuration file for FlightGazer '''
CONFIG_VERSION: str = "v.1.6" # do not modify this

# ===== General settings =====
# ============================

FLYBY_STATS_ENABLED: bool = True
''' Save general stats of planes and API usage to a CSV file in the directory this is stored in '''

UNITS: int = 0
''' Select which units to use. 
0 = aeronautical (nmi, ft, kt)
1 = metric (km, m, km/h)
2 = imperial (mi, ft, mph) '''

HEIGHT_LIMIT: float = 15000
''' Filter out planes at an altitude higher than this (feet or meters)'''

RANGE: float = 2
''' Radius of which planes need to be in for detailed tracking (nautical miles, kilometers, or miles) '''

FLYBY_STALENESS: int = 60
''' If the same plane appears again before this time, do not consider it as a flyby (in minutes) '''

API_KEY: str = ""
''' Put your FlightAware API key here. Leave as "" to not use the API '''

API_DAILY_LIMIT: int | None = None
''' Set this to None if you want to have unlimited API calls '''

CUSTOM_DUMP1090_LOCATION: str = ""
''' URL of your dump1090 install if it is in a different location or on a different network device.
ex: `http://localhost/custom_name_here` or `http://192.168.xxx.xxx:8080` (no trailing `/`) '''

CUSTOM_DUMP978_LOCATION: str = ""
''' URL of your dump978 install if it is in a different location or on a different network device.
If you're not using dump978, leave the value as a blank string.
ex: `http://192.168.xxx.xxx:8978` '''

# ===== Screen Output settings =====
# ==================================

ENHANCED_READOUT: bool = False
''' If True, show more details on plane info screen and replaces origin and destination readout.
Will not use API even if a key is provided. Useful if API is not in use.
Additional details include plane coordinates, ground track, vertical rate, and RSSI '''

DISPLAY_SUNRISE_SUNSET: bool = False
''' If True, show sunrise and sunset times on the Clock screen '''

DISPLAY_RECEIVER_STATS: bool = False
''' If True, show receiver stats (gain, noise, % loud signals) on the Clock screen.
Overwrites sunrise/sunset display if `DISPLAY_SUNRISE_SUNSET` is enabled.
If your setup uses a remote dump1090 instance, this likely will not show anything useful. '''

CLOCK_24HR: bool = False
''' If True, use 24 hour clock. If False, 12 hour clock will be used '''

# ===== Brightness settings =====
# ===============================

BRIGHTNESS: int = 100
''' Set the LED brightness (0..100) '''

ENABLE_TWO_BRIGHTNESS: bool = False
''' If True, enables dynamically switching brightness. If False, only `BRIGHTNESS` will be used. '''

BRIGHTNESS_2: int = 50
''' Secondary LED brightness (0..100).
`BRIGHTNESS_2` will be used from sunset to sunrise and `BRIGHTNESS` will be used for all other times. '''

BRIGHTNESS_SWITCH_TIME: dict = {
    "Sunrise": "06:00",
    "Sunset": "18:00"
}
''' Set the time of day (in 24-hr format) to switch brightness levels. '''

USE_SUNRISE_SUNSET: bool = False
''' If True, use sunrise and sunset times to adjust brightness.
If sunrise or sunset times are not available, will fall back to `BRIGHTNESS_SWITCH_TIME` values.'''

ACTIVE_PLANE_DISPLAY_BRIGHTNESS: int | None = None
''' When there is an active plane, use a different brightness level (0..100). Useful for grabbing attention.
Overrides all other brightness settings when a plane is being tracked.
If you would like to keep it the same brightness, set this to None '''

# ===== RGB-Matrix settings ======
# ================================

GPIO_SLOWDOWN: int = 2
''' Set this to the specific value that works for your setup. 
Higher values are more suited for faster/more modern Raspberry Pi's '''

HAT_PWM_ENABLED: bool = True
''' If you set the quality modification for the RGB-Matrix hat, set to True. False if not '''

RGB_ROWS: int = 32
''' Number of LED rows in your display '''

RGB_COLS: int = 64
''' Number of LED columns in your display '''

LED_PWM_BITS: int = 8
''' Lower decreases color depth but increases refresh rate. Adjust to taste '''