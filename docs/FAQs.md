# Frequently Asked Questions Regarding FlightGazer
> Intended audience: end-users

## Preface

This document serves to both provide solutions to potentially common inquries and as a supplemental troubleshooting guide when using FlightGazer.<br>
It's impossible to cover all situations and scenarios when it comes to using FlightGazer, but this should be the first thing to refer to before going through the hassle of filing a bug report. This section used to exist in the main readme file, but has been separated out for easier reference.<br>
Should your question not be answered here, feel free to file an issue to [This Repository](https://github.com/WeegeeNumbuh1/FlightGazer/issues) on GitHub.
- signed: WeegeeNumbuh1

## FAQ's

### Using

**Q: My RGB display is blank when running this, what broke?**<br>
**A:** Check the `HAT_PWM_ENABLED` value in `config.yaml` and make sure it matches your hardware setup.<br>
This project assumes the use of the adafruit rgbmatrix bonnet and only 1 HUB75-based RGB panel.<br>
Other setups are not guaranteed to work but they might work by using the Advanced RGB Matrix options in the config file.<br>
Getting the RGB display to work is beyond the scope of this project if it wasn't working before using FlightGazer.

**Q: I broke it 🥺**<br>
**A:** Try running the updater first. If it's still broken, uninstall then reinstall FlightGazer.

**Q: Can I run the physical display *and* the emulator at the same time? I'd like to see the display in a web browser while the main display is still working.**<br>
**A:** No. It's one or the other. The emulator is meant as a fallback/for development, or to try out FlightGazer before fully committing to using a real display.

**Q: How do I make this work with *ABC* or *XYZ*?**<br>
**A:** Refer to the [tips-n-tricks](tips-n-tricks.md) document first, which might already have an answer.<br>
If your question isn't found there, please file an issue.

**Q: I see a dot on the right of the aircraft readout display. What is it?**<br>
**A:** That is an indicator of how many aircraft are within your defined area. The number of dots lit up indicate how many are present. There will almost always be at least one lit up, all the way to 6. If the number is greater than 1, FlightGazer will start switching between aircraft to show you what else is flying in your area. *Note*: If the indicator disappears but it appears that FlightGazer is still tracking an aircraft, this means that the connection to dump1090 has been lost. The display will eventually return to the clock in this case.

**Q: Can I customize the colors?**<br>
**A:** Edit the `colors.py` file in the `utilities` directory.

**Q: FlightGazer detected a plane and it couldn't determine a journey. This same plane showed up again a few minutes later and the result didn't change. What happened?**<br>
**A:** If this plane is blocked from public tracking, there will never be a result. If you know it isn't, try lowering the value for `FLYBY_STALENESS`.<br>
This situation has been seen when a plane just takes off and the API that FlightGazer uses hasn't begun tracking the plane just yet, therefore there isn't a result that the API can give. When this plane shows up again, FlightGazer will reuse the same API result since it would not count this as a new flyby, a metric controlled by `FLYBY_STALENESS`.<br>

**Q: I found an error with some of the aircraft info (type, owner, airline, etc.)**<br>
**A:** FlightGazer relies on external databases in order to provide this information without the need for API calls. Since the information contained within those databases is outside of the author's control, you will basically have to wait and see if the data is corrected at some point in the future.<br>
Additionally, if the aircraft broadcasts incorrect information (ex: mistyped callsign, wrong transponder code, etc.), there is no way for FlightGazer to know this and will do a best-effort approach to what it was given.

**Q: I restarted/updated my system but it took longer for FlightGazer to start. What's going on?**<br>
**A:** The initialization script that starts FlightGazer checks if there are any updates to the dependencies it uses.<br>
If it has been over three (3) months since it last checked, then the next time it restarts, it will run these checks. It usually takes a few minutes to do this, but if your internet connection is slow or the system is loaded with other processes, then it could take longer. For reference, a modern PC with a fast internet connection can complete the upgrade in less than 30 seconds, sometimes as fast as 10. A Raspberry Pi Zero 2W can take 5-6 minutes.

**Q: Okay, but this update is taking a *really long* time. Then, it just stops after awhile. Is it broken?**<br>
**A:** First, restart the whole system. Then, let FlightGazer do the update again (it should do this automatically at system startup). Most failures can be traced to networking issues and not FlightGazer itself.<br>

### Conceptual Stuff

**Q: Why use the FlightAware API? Why not something more "free" like [adsbdb](https://www.adsbdb.com/) or [adsb.lol](https://api.adsb.lol/docs)?**<br>
**A:** In the Author's experience, adsbdb/adsb.lol cannot handle chartered/position-only flights (i.e. general aviation, military, etc) and are lacking (correct) information for some flights. Because these open APIs rely on crowdsourcing and are maintained by a small group of people, the data offered by these APIs is prone to being outdated or incorrect. After testing, these APIs just aren't rigorous enough to be used for this project. It's better to have no information than misinformation. Plus, FlightGazer is still useful without having journey info anyway. I (WeegeeNumbuh1) do wish FlightAware had a much lighter API endpoint for pulling very basic information like what this project uses.

**Q: Why use a different font for the Callsign? I don't like how it looks different by default next to other readouts.**<br>
**A:** If it's too bothersome, set `ALTERNATIVE_FONT` to `true` in the config file to make it more uniform.<br>
Reasoning: The original/default font is perfect with numerical readouts that update frequently (eg: speed, RSSI, altitude, seconds, etc) as the general glyph shape doesn't change between updates.<br>
The alternative font is perfect for the callsign because callsigns are alphanumeric, the readout changes less often, and the alternative font offers quick differentation between between homoglyphs ('0' vs 'O', '5' vs 'S') compared to the default font.
Additionally, with fields that aren't alphanumeric (country code) or use a limited set of the alphabet (direction + distance), there's less of a need for the alternative font's advantages.<br>

### Development-Related

**Q: Can I customize the layout beyond what can be done in `config.yaml` (clock, aircraft info, etc)?**<br>
**A:** Sure, just change some things in the script. Have fun. (also, you can just fork this project)<br>
(note: any changes done to the main script will be overwritten if you update with the updater)

**Q: Why are you using the `/etc` directory for the virtual enviornment? Shouldn't it be in `/opt`?**<br>
**A:** Yes. Using `/etc` was mistakenly chosen at the very start of this project (even before the first commit). As many other features have been bolted onto FlightGazer since then, moving the virtual environment to `/opt` will break existing update routines and other services. It's going to be stuck like this for the foreseeable future.

**Q: Why are your commits so *huge*?**<br>
**A:** Yes.<br>

**Q: No `dev` or `test` branch? and why**<br>
**A:** Nope. Testing is (mostly) done before a commit.<br>Reason: Can't be bothered to deal with multiple branches and merging. *We'll do it live* as they say.<br>

**Q: Some of your code is not pythonic!!!1!!111** ![](https://cdn.discordapp.com/emojis/359007558532595713.webp?size=20)<br>
**A:** but it works, does it not? ![](https://cdn.discordapp.com/emojis/389287695903621121.webp?size=20)<br>
(it should be >98% pythonic at this point)