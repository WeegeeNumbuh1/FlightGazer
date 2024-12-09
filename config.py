''' Configuration file for FlightGazer '''
CONFIG_VERSION: str = "v.1.3"

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

# ===== RGB-Matrix settings ======
# ================================

CLOCK_24HR: bool = False
''' If True, use 24 hour clock. If False, 12 hour clock will be used '''

BRIGHTNESS: int = 100
''' Set the LED brightness (0..100) '''

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