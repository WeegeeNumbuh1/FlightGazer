# Tips and Tricks For Using FlightGazer
> Intended audience: end-users

## Preface
These are a collection of various settings and configurations that are supported by FlightGazer, along with other recommendations for ensuring the success of deploying FlightGazer onto your own setup.<br>
The following used to be part of the main readme file, but has now been separated out and into its own individual file for easier reference.
- signed: WeegeeNumbuh1

## Try These
<details name="tech-tips"><summary><b>Configuration details for a remote dump1090 installation (eg: FlightAware-provided FlightFeeder)</b></summary>
<br>

Set `CUSTOM_DUMP1090_LOCATION` to the IP address of the device running dump1090.<br>
Example: `http://192.168.xxx.xxx:8080` or `http://192.168.xxx.xxx/skyaware`<br>
And then set `PREFER_LOCAL` to `false`.

</details>
<details name="tech-tips"><summary><b>If you initially built your ADS-B receiver around RadarBox24/AirNav Radar's rbfeeder or Flightradar24's Pi24 image</b></summary>
<br>

`rbfeeder` and `Pi24` setups don't provide a web interface that FlightGazer can look at.<br>
Therefore, FlightGazer can only run directly on those systems and must be installed on those devices.<br>
Set `PREFER_LOCAL` to `true` so that FlightGazer can read the data from these setups.<br>

If you managed to install a working web interface like `tar1090` with these setups then you're an advanced user and you already know what you're doing.<br>

</details>

<details name="tech-tips"><summary><b>Connecting to a separate dump978 feeder (over the network)</b></summary>
<br>

Set `CUSTOM_DUMP978_LOCATION` to the IP address of the dump978 system.<br>
Example: `http://192.168.xxx.xxx:8978`<br><br>
If dump1090 is running on the same system FlightGazer is running off of, leave `PREFER_LOCAL` to `true`.<br><br>
FlightGazer was designed to handle reading from both a local dump1090 instance and a remote dump978 system at the same time.
However, if your network goes down or the dump978 system disconnects, this will cause FlightGazer to pause its processing as if dump1090 failed as well.<br><br>
Also important to note, if your dump978 instance uses a different set location than your dump1090 one, the distance data for UAT aircraft will be overridden by your dump1090 location.

</details>

<details name="tech-tips"><summary><b>Using FlightGazer just as a basic dump1090 parser (no display)</b></summary>
<br>

Enable both `NO_DISPLAY_MODE` (the `-d` flag) and `NO_FILTER` mode (`-f`) at script startup to enable just the dump1090 json parsing functionality.<br><br>
This combination is useful for determining how many *flights* (not exactly each unique aircraft) were detected by your site over the span of a day. `FLYBY_STALENESS` still is used (which influences this value) but its minimum time is raised to 60 minutes in `NO_FILTER` mode.<br>
If you don't plan on using the display and intend to run FlightGazer with this combination of modes, adjust the value of `FLYBY_STALENESS` to values appropriate to your local area traffic. (see: the Changelog and go to v.3.0.1)<br><br>
As a side-effect, if you're interested in finding lapses in the aircraft database (e.g., detecting aircraft that have no known type or owner), this combination of startup features can help the database maintainers know what to add in future updates (if you're in contact with them).
</details>

<details name="tech-tips"><summary><b>Turning off the screen at night</b></summary>
<br>

`ENABLE_TWO_BRIGHTNESS: true`<br>
`BRIGHTNESS_2: 0`<br>
*if you don't want to track aircraft either:*<br>
`DISABLE_ACTIVE_BRIGHTNESS_AT_NIGHT: true`

If you don't want it to turn off at sunset,<br>
`USE_SUNRISE_SUNSET: false`<br>
then set `BRIGHTNESS_SWITCH_TIME` to whatever time you want.

Note that FlightGazer will still be running *and* driving the screen even with a brightness of `0` so CPU usage will remain the same.

</details>
<details name="tech-tips"><summary><b>Only turn on the screen when there's an aircraft nearby (no clock)</b></summary>
<br>

`BRIGHTNESS: 0`<br>
`ENABLE_TWO_BRIGHTNESS: false`<br>
`ACTIVE_PLANE_DISPLAY_BRIGHTNESS: <your value here>`<br>

*Note:* If you use `NO_FILTER` mode with the above settings, the display will remain blank.

</details>

<details name="tech-tips"><summary><b>Hiding elements on the display</b></summary>
<br>

Go to the color config file and set whatever element you don't want to show to `BLACK`.<br>
Example: `seconds_color = BLACK`

</details>

<details name="tech-tips"><summary><b>Reduce flickering on a physical RGB matrix display</b></summary>
<br>

- [Do the PWM mod](https://github.com/hzeller/rpi-rgb-led-matrix?tab=readme-ov-file#improving-flicker)
- [Reserve a CPU core solely for the display](https://github.com/hzeller/rpi-rgb-led-matrix?tab=readme-ov-file#cpu-use)
- Lower the value for `LED_PWM_BITS` (though `8` seems good enough)
- Switch CPU governor to `performance` or add `force_turbo=1` to a Raspberry Pi's `config.txt` file

</details>

## Didn't find what you were looking for?
Feel free to file an issue to [This Repository](https://github.com/WeegeeNumbuh1/FlightGazer/issues).