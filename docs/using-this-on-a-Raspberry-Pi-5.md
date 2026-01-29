# Running FlightGazer on a Raspberry Pi 5 with a Physical RGB Display
> Intended audience: end-users
## Preface
*Valid as of FlightGazer v.9.8.0*

FlightGazer relies on the [rgbmatrix](https://github.com/hzeller/rpi-rgb-led-matrix/) library and its Python bindings to render its information onto an LED RGB display.

The GPIO system on a Raspberry Pi 5 is significantly different compared to past Pi hardware and the rgbmatrix library has had a [long-standing compatibility issue](https://github.com/hzeller/rpi-rgb-led-matrix/issues/1603) with the Pi 5, and therefore it will not work.

## Current Workarounds
### tl;dr
> [!IMPORTANT]
> This feature is experimental and hasn't been tested yet, but it *should* work.

Edit the `emulator_config.json` file in the FlightGazer directory, change the `display_adapter` key to `"pi5"`, and start FlightGazer using Emulate Mode (`-e` flag).

## Details
### Adafruit's Piomatter
Adafruit has a [software library](https://github.com/adafruit/Adafruit_Blinka_Raspberry_Pi5_Piomatter) which works with the PIO system of the Pi5.<br>
However, this is not a drop-in replacement for the rgbmatrix library and would require re-architecting FlightGazer in order to work with this specific software stack.

Thus, this library is unsuitable for FlightGazer *when used directly*.

### RGBMatrixEmulator
FlightGazer installs [RGBMatrixEmulator](https://github.com/ty-porter/RGBMatrixEmulator) as a fallback when the rgbmatrix library is unavailable or fails to load.<br>
[v0.15.0](https://github.com/ty-porter/RGBMatrixEmulator/releases/tag/v0.15.0) adds support for the Pi5 with a "Pi5 adapter" which bridges/shims rgbmatrix calls to the Piomatter library mentioned above.

If you are using a Raspberry Pi 5, the FlightGazer initialization script automatically installs the specific version of RGBMatrixEmulator (`RGBMatrixEmulator[pi5]`) which supports this experimental feature. Other systems and Raspberry Pi hardware that isn't the Pi 5 will use the normal version without this add-in.