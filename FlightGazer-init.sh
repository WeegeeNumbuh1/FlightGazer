#!/bin/bash
# Initialization/bootstrap script for FlightGazer.py
# Repurposed from my other project, "UNRAID Status Screen"
# For changelog, check the 'changelog.txt' file.
# Version = v.9.0.3
# by: WeegeeNumbuh1
export DEBIAN_FRONTEND="noninteractive"
STARTTIME=$(date '+%s')
BASEDIR=$(cd `dirname -- $0` && pwd)
export PYTHONUNBUFFERED=1
export PIP_ROOT_USER_ACTION=ignore # hide pip complaining we're using root
VENVPATH=/etc/FlightGazer-pyvenv
GREEN='\033[0;32m'
ORANGE='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
FADE='\033[2m'
CHECK_FILE="${VENVPATH}/first_run_complete"
THIS_FILE="${BASEDIR}/FlightGazer-init.sh"
LOGFILE="${BASEDIR}/FlightGazer-log.log"
DB_DOWNLOADER="${BASEDIR}/utilities/aircraft_db_fetcher.py"
INTERNET_STAT=0 # think return codes
SKIP_CHECK=0 # 0 = do not skip dependency checks, 1 = skip
WEB_INT=0 # 1 = web interface is present

# Function to send SIGTERM to python when our exit signals are detected
terminate() {
	echo -e "\n${ORANGE}>>> Shutdown signal received, forwarding to child processes.${NC}"
	kill -15 "$child_pid" 2> /dev/null
	sleep 1s
	echo -e "${GREEN}>>> Shutdown complete.${NC}"
	exit 0
	}

interrupt() {
	echo -e "\n${ORANGE}>>> Shutdown signal received, forwarding to child processes.${NC}"
	kill -2 "$child_pid" 2> /dev/null
	sleep 1s
	echo -e "${GREEN}>>> Shutdown complete.${NC}"
	exit 0
	}

help_str(){
	echo ""
	echo "Usage: sudo bash \"${BASEDIR}/$(basename $0)\" [options]"
	echo "[-h]     Print this help message."
	echo "Default (no options) is to run using rgbmatrix and minimal console output."
	echo -e "[-d] [-f] [-t] will trigger interactive mode (console output).\n"
	echo " ***** Main script options *****"
	echo "[-d]     No Display mode - Only console output."
	echo "[-e]     Emulate - Run display via RGBMatrixEmulator instead of real hardware."
	echo "[-f]     No Filter mode - Disable filtering and show all aircraft positions. No API fetching."
	echo "[-v]     Enable verbose/debug messages for the main script."
	echo ""
	echo " *****    Setup options    *****"
	echo "[-t]     Run in tmux, if available."
	echo "[-c]     Install/force-check dependencies only. Do not start main script."
	echo "[-l]     Live/Demo mode: Setup in /tmp, no permanent install."
	echo ""
	echo "Report bugs to WeegeeNumbuh1 <https://github.com/WeegeeNumbuh1/FlightGazer>"
}

cleanup() {
	echo -e "${RED}\n>>> Ctrl+C pressed. Setup or startup cancelled.${NC}"
	# kill splash screen if started
	kill -15 $(ps aux | grep '[s]plash.py' | awk '{print $2}') >/dev/null 2>&1
	if [ $SKIP_CHECK -eq 0 ]; then
		# remove check file (install might be in an inconsistent state)
		rm $CHECK_FILE > /dev/null 2>&1
	fi
	if [ $WEB_INT -eq 1 ]; then
		systemctl is-active flightgazer-webapp >/dev/null 2>&1
		# if we stopped the web interface
		if [ $? -eq 3 ]; then
			systemctl start flightgazer-webapp >/dev/null 2>&1
		fi
	fi
	# https://old.reddit.com/r/bash/comments/1e8plnu/leddyee/
	trap - INT
	kill -INT "$$"
}

emulator_heredoc() {
	cat << EOF > "${BASEDIR}/emulator_config.json"
{
    "pixel_outline": 0,
    "pixel_size": 16,
    "pixel_style": "real",
    "pixel_glow": 8,
    "display_adapter": "browser",
    "suppress_font_warnings": true,
    "suppress_adapter_load_errors": true,
    "browser": {
        "_comment": "For use with the browser adapter only.",
        "port": 8888,
        "target_fps": 25,
        "fps_display": true,
        "quality": 50,
        "image_border": true,
        "debug_text": false,
        "image_format": "JPEG"
    },
    "log_level": "info",
    "icon_path": null,
    "emulator_title": "FlightGazer - Emulated"
}
EOF
}

DFLAG=""
EFLAG=""
FFLAG=""
TFLAG=""
CFLAG=false
VFLAG=""
LFLAG=false
while getopts ':cdefhltv' opt; do
	case "$opt" in
		d)
		DFLAG="-d"
		;;
		e)
		EFLAG="-e"
		;;
		f)
		FFLAG="-f"
		;;
		t)
		TFLAG=true
		;;
		c)
		CFLAG=true
		;;
		v)
		VFLAG="-v"
		;;
		l)
		LFLAG=true
		VENVPATH=/tmp/FlightGazer-pyvenv
		CHECK_FILE=${VENVPATH}/first_run_complete
		;;
		h)
		echo "This is the FlightGazer initialization script."
		help_str
		exit 1
		;;
		\?)
		INVALID_FLAG=true
		echo -e "${RED}Invalid option: -$OPTARG${NC}" >&2
		;;
	esac
done
# getopts block will loop as many times as invalid flags are given,
# if this variable exists, let it loop, then print the help string and exit
if [ "$INVALID_FLAG" = true ]; then
	help_str
	exit 1
fi

echo -ne "\033]0;FlightGazer\007" # set window title
echo -e "\n${ORANGE}>>> Welcome to FlightGazer!${NC}"
if [ -f "${BASEDIR}/version" ]; then
	VER_STR=$(head -c 12 "${BASEDIR}/version")
	# VERSION_MAJOR=$(echo "$VER_STR" | cut -d '.' -f1)
	echo -e "    Version: ${VER_STR}"
fi
if [ `id -u` -ne 0 ]; then
	>&2 echo -e "${RED}>>> ERROR: This script must be run as root.${NC}"
	sleep 1s
	exit 1
fi

# kill the boot splash screen (if present)
# better than using systemd to control the service itself
kill -15 $(ps aux | grep 'splash-sysinit.py' | awk '{print $2}') >/dev/null 2>&1

if [[ $(ps aux | grep '[F]lightGazer\.py' | awk '{print $2}') ]]; then
	echo -e "\n${NC}${RED}>>> ERROR: FlightGazer is already running.${NC}"
	echo "These are the process IDs detected:"
	ps aux | grep '[F]lightGazer.py' | awk '{print $2}'
	echo -e "\n${ORANGE}>>> FlightGazer can only have one running instance at a time.${NC}"
	echo "To stop the other running instance, use:"
	echo "'sudo systemctl stop flightgazer.service' -or-"
	echo "'sudo tmux attach -d -t FlightGazer' and press Ctrl+C -or-"
	echo 'sudo kill -15 $(ps aux | grep '"'"'[F]lightGazer\.py'"'"' | awk '"'"'{print $2}'"'"')'
	sleep 2s
	exit 1
fi

echo -e "${GREEN}>>> Checking dependencies, let's begin.${NC}"
echo -e "${FADE}"

if [ ! -f "${BASEDIR}/FlightGazer.py" ]; then
	echo -e "\n${NC}${RED}>>> ERROR: Cannot find ${BASEDIR}/FlightGazer.py.${NC}"
	sleep 2s
	exit 1
fi

REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=10
if ! command -v python3 >/dev/null 2>&1; then
	echo -e "\n${NC}${RED}>>> ERROR: Python is not installed. Please install it on this system first.${NC}"
	exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
INSTALLED_MAJOR=$(echo "$PYTHON_VERSION" | cut -d '.' -f1)
INSTALLED_MINOR=$(echo "$PYTHON_VERSION" | cut -d '.' -f2)
if [ -f "${BASEDIR}/setup/min_python_version" ]; then
	REQUIRED_PYTHON_NOW=$(head -c 8 "${BASEDIR}/setup/min_python_version")
	REQUIRED_PYTHON_MAJOR=$(echo "$REQUIRED_PYTHON_NOW" | cut -d '.' -f1)
	REQUIRED_PYTHON_MINOR=$(echo "$REQUIRED_PYTHON_NOW" | cut -d '.' -f2)
fi
if (( INSTALLED_MAJOR < REQUIRED_PYTHON_MAJOR )) || \
   (( INSTALLED_MAJOR == REQUIRED_PYTHON_MAJOR && INSTALLED_MINOR < REQUIRED_PYTHON_MINOR )); then
	echo -e "\n${NC}${RED}>>> ERROR: Python version too old. Required: ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR} or higher. Found: ${PYTHON_VERSION}${NC}"
	echo "Python must be updated to a newer version on your system before you can run FlightGazer."
	exit 1
fi

if [ ! -f "${BASEDIR}/utilities/rgbmatrix_check.py" ]; then
	RGBMATRIX_PRESENT=10 # some other number that isn't a return code generated by the script
else
	python3 "${BASEDIR}/utilities/rgbmatrix_check.py" >/dev/null 2>&1
	RGBMATRIX_PRESENT=$?
fi

systemctl list-unit-files flightgazer-webapp.service >/dev/null
if [ $? -eq 0 ]; then
	WEB_INT=1
fi
if [ -f '/proc/device-tree/model' ]; then # probably a Raspberry Pi
	DEV_TYPE=$(tr -d '\0' < /proc/device-tree/model) >/dev/null 2>&1
	# https://stackoverflow.com/a/46163928
else
	DEV_TYPE=''
fi
CORECOUNT=$(grep -c ^processor /proc/cpuinfo)

if [ -d "$VENVPATH" ] && [ -f "$CHECK_FILE" ] && [ -f "${BASEDIR}/utilities/venv_check.py" ]; then
	"${VENVPATH}/bin/python3" "${BASEDIR}/utilities/venv_check.py"
	if [ $? -ne 0 ]; then
		>&2 echo -e "\n${NC}${RED}>>> WARNING: The virtual environment is broken.${NC}"
		echo "    It will be rebuilt this session."
		echo ""
		rm -rf "$VENVPATH"
	fi
fi

if [ ! -f "$CHECK_FILE" ];
then
	echo -e "${NC}> First run or upgrade detected, installing needed dependencies.
  This may take some time, depending on how fast your system is.${FADE}"

	echo "================== System Info ===================="
	if [ -n "$DEV_TYPE" ]; then
		echo -e "> Running on a ${DEV_TYPE}"
	else
		echo -e "> Running on $(uname -a)"
	fi
	if [ $CORECOUNT -eq 1 ]; then
		echo "> WARNING: Only one CPU core detected!"
		echo "  Installation might take a very long time!"
		if [ "$DFLAG" != "-d" ] && [ -n "$DEV_TYPE" ]; then
			echo "> WARNING: It is highly recommended to *NOT* run the rgb-matrix display or its emulator on this system!"
			echo "  Performance may be extremely poor due to only having a single core."
		fi
	else
		echo "> ${CORECOUNT} CPU(s) available"
	fi
	echo ""
	echo -n "> rgbmatrix library: "
	if [ $RGBMATRIX_PRESENT -eq 0 ]; then
		echo "Installed"
	elif [ $RGBMATRIX_PRESENT -eq 1 ]; then
		echo "Unavailable"
	elif [ $RGBMATRIX_PRESENT -eq 3 ]; then
		echo "Present, but not available system-wide"
	else
		echo "Status cannot be determined"
	fi
	echo "==================================================="

	if [ "$LFLAG" = true ]; then
		echo "****************************************************************************"
		echo "> We are currently running in Live/Demo mode; FlightGazer will run"
		echo "  using dependencies in '/tmp' and not install itself onto the system."
		echo ""
		echo "> Once this is set up, if you would like to run FlightGazer again,"
		echo "  don't forget to use the '-l' flag. Not using that implies a full install."
		echo "****************************************************************************"
		sleep 5s
	fi
	if [ $WEB_INT -ne 1 ]; then
		echo ""
		echo "Protip: Install the web interface to make dealing with FlightGazer more convenient!"
		echo "It can be installed with the 'install-FlightGazer-webapp.sh' script in this directory."
		echo ""
	else
		echo ""
		echo "The FlightGazer web interface is present."
		echo "This script will also check the dependencies for it as well."
		echo ""
	fi
	VERB_TEXT='Installing: '
else
	echo -n "> Last dependencies check: "
	date -r "$CHECK_FILE"
	last_check_time=$(date -r "$CHECK_FILE" '+%s')
	# 1 month = 2592000 seconds
	if [ $((STARTTIME - last_check_time)) -lt 7776000 ]; then
		echo "> Last check was less than 3 months ago, skipping tests."
		SKIP_CHECK=1
	fi
	VERB_TEXT='Checking: '
	if [ $CORECOUNT -eq 1 ] && [ -z "$DEV_TYPE" ] && [ "$DFLAG" != "-d" ]; then
		echo "> WARNING: It is highly recommended to *NOT* run the rgb-matrix display or its emulator on this system!"
		echo "  Performance may be extremely poor. Please re-run this script with the '-d' flag."
	fi
fi

trap cleanup SIGINT
if [ $SKIP_CHECK -eq 0 ] || [ "$CFLAG" = true ]; then
	echo -e "${NC}> Checking system image...${FADE}"
	# get rid of git tracking stuff
	rm -rf "${BASEDIR}/.git" >/dev/null 2>&1
	find "${BASEDIR}" -type f -name '.*' -exec rm '{}' \; >/dev/null 2>&1

	# check if this system uses apt
	if ! command -v apt >/dev/null 2>&1; then
		echo -e "${NC}${RED}>>> ERROR: Initial setup cannot continue. This system does not use apt.${NC}"
		sleep 2s
		exit 1
	fi

	# check if this is a systemd system
	if ! command -v systemctl --version >/dev/null 2>&1; then
		echo -e "${NC}${RED}>>> ERROR: Initial setup cannot continue. This system does not use systemd.${NC}"
		sleep 2s
		exit 1
	fi

	# check internet connection
	wget -q --timeout=5 --spider http://google.com && wget -q --connect-timeout=5 --tries=1 --spider http://pypi.org
	if [ $? -ne 0 ]; then
		INTERNET_STAT=1
		>&2 echo -e "${NC}${RED}>>> Warning: Failed to connect to internet or pypi.org (Python packages)."
		echo -e "Dependency checking will be skipped, but will be checked when this is run again.${FADE}"
	fi

	if [ ! -f "$CHECK_FILE" ] && [ $INTERNET_STAT -eq 1 ] && [ ! -d "$VENVPATH" ]; then
		>&2 echo -e "${NC}${RED}>>> ERROR: Initial setup cannot continue. Internet connection is required.${NC}"
		sleep 2s
		exit 1
	fi

	if [ $INTERNET_STAT -eq 0 ]; then
		echo "  > Internet connectivity available, initial setup can continue."
	fi

	read -r OWNER_OF_FGDIR GROUP_OF_FGDIR <<<$(stat -c "%U %G" "${BASEDIR}")
	echo "  > Determining the home directory..."
	USER_HOME=$(sudo -u "$OWNER_OF_FGDIR" sh -c 'echo $HOME') >/dev/null 2>&1
	# https://superuser.com/a/1613980
	echo -e "  > ${USER_HOME}"
fi

# start the splash screen
# note that if this is a fresh install and the rgbmatrix software framework doesn't exist, the splash screen won't run
if [ "$DFLAG" != "-d" ]; then
	if [ ! -d "$VENVPATH" ]; then
		# if the rgbmatrix library is already installed on first install, this may run
		if [ $SKIP_CHECK -eq 0 ] || [ "$CFLAG" = true ]; then
			nohup python3 "${BASEDIR}/utilities/splash.py" "${BASEDIR}/FG-Splash.ppm" -u >/dev/null 2>&1 &
		else
			nohup python3 "${BASEDIR}/utilities/splash.py" "${BASEDIR}/FG-Splash.ppm" >/dev/null 2>&1 &
		fi
	else
		if [ $SKIP_CHECK -eq 0 ] || [ "$CFLAG" = true ]; then
			nohup "${VENVPATH}/bin/python3" "${BASEDIR}/utilities/splash.py" "${BASEDIR}/FG-Splash.ppm" -u >/dev/null 2>&1 &
		else
			nohup "${VENVPATH}/bin/python3" "${BASEDIR}/utilities/splash.py" "${BASEDIR}/FG-Splash.ppm" >/dev/null 2>&1 &
		fi
	fi
fi

if [ ! -f "$CHECK_FILE" ] || [ "$CFLAG" = true ]; then
	echo "  > Updating package lists..."
	echo "    > \"apt-get update\""
	echo "      (this may take some time if this hasn't been run in awhile)"
	apt-get update >/dev/null
	echo "    > \"dpkg --configure -a\""
	dpkg --configure -a >/dev/null
	echo ""
	echo "  > Installing needed dependencies..."
	echo "    [ python3-dev python3-venv python3-numpy libjpeg-dev tmux ]"
	echo "    (this might also take awhile if these components aren't installed, please wait.)"
	# should speed up things
	# https://askubuntu.com/a/1333505
	apt-cache --generate pkgnames | \
	grep --line-regexp --fixed-strings \
	-e python3-dev \
	-e python3-venv \
	-e python3-numpy \
	-e libjpeg-dev \
	-e tmux \
	| xargs apt-get install -y >/dev/null
	echo -e "${FADE}"
	echo "  > Creating systemd services..."
	if [ ! -f "/etc/systemd/system/flightgazer.service" ] && [ "$LFLAG" = false ]; then
		cat <<- EOF > /etc/systemd/system/flightgazer.service
		[Unit]
		Description=FlightGazer service
		After=multi-user.target
		Documentation="https://github.com/WeegeeNumbuh1/FlightGazer"

		[Service]
		User=root
		# Note: unless the -t flag is used, DO NOT use interactive flags unless you want to spam the logs
		ExecStart=bash "${THIS_FILE}" -t
		ExecStop=-tmux send-keys -t FlightGazer C-c || true
		ExecStop=sleep 1s
		Type=forking
		TimeoutStartSec=720
		TimeoutStopSec=5

		[Install]
		WantedBy=multi-user.target
		Also=flightgazer-bootsplash.service
		EOF

		cat <<- EOF > /etc/systemd/system/flightgazer-bootsplash.service
		[Unit]
		Description=FlightGazer boot splash screen
		DefaultDependencies=no
		After=local-fs.target
		Before=network.target
		RefuseManualStart=true
		Documentation="https://github.com/WeegeeNumbuh1/FlightGazer"

		[Service]
		User=root
		ExecStart="${VENVPATH}/bin/python3" "${BASEDIR}/utilities/splash-sysinit.py"
		Type=simple
		Restart=no

		[Install]
		# start real early
		WantedBy=sysinit.target
		EOF
		echo -e "${FADE}"
		systemctl daemon-reload >/dev/null 2>&1
		systemctl enable flightgazer.service 2>&1
		if [ $RGBMATRIX_PRESENT -eq 0 ] || [ $RGBMATRIX_PRESENT -eq 3 ]; then
			echo -e "${NC}${FADE}    > rgb-matrix library present, enabling boot splash..."
			systemctl enable flightgazer-bootsplash.service 2>&1
			echo -e "${NC}${FADE}    > Note: If you do not want the boot splash, use the command"
			echo "      systemctl disable flightgazer-bootsplash.service"
		else
			echo -e "${NC}${FADE}    > rgb-matrix library not present, keeping boot splash disabled..."
			systemctl disable flightgazer-bootsplash.service 2>&1
		fi
		systemctl status flightgazer.service --no-pager
		echo -e "\n${NC}${FADE}    > Service installed. FlightGazer will run at boot via systemd."
		echo -e "${RED}    > Do not move the FlightGazer directory (${ORANGE}${BASEDIR}${RED})!"
		echo -e "      Doing so will cause the service to fail!${NC}${FADE}"
		sleep 5s
	else
		echo "    > Service already exists or we are running"
		echo "      in Live/Demo mode, skipping service creation."
	fi

	# make a config file for the emulator to prevent harmless error spam and to
	# take advantage of the emulator's other rendering options
	if [ ! -f "${BASEDIR}/emulator_config.json" ]; then
		echo "  > Creating RGBMatrixEmulator settings..."
		emulator_heredoc
		chown -f ${OWNER_OF_FGDIR}:${GROUP_OF_FGDIR} "${BASEDIR}/emulator_config.json" >/dev/null 2>&1
		echo "    > RGBMatrixEmulator settings created."
	elif [ $(wc -l < "${BASEDIR}/emulator_config.json") -ne 22 ]; then # count the lines in the heredoc in this script
		echo "  > Updating RGBMatrixEmulator settings..."
		emulator_heredoc
		chown -f ${OWNER_OF_FGDIR}:${GROUP_OF_FGDIR} "${BASEDIR}/emulator_config.json" >/dev/null 2>&1
		echo "    > RGBMatrixEmulator settings updated."
	fi
fi
if [ ! -d "$VENVPATH" ]; then
	mkdir "${VENVPATH}"
	echo ""
	echo "  > Making virtual environment... (this may take awhile)"
	python3 -m venv --system-site-packages "$VENVPATH"
	echo "  > Initializing the virtual environment..."
	"${VENVPATH}/bin/python3" -m pip install --upgrade pip >/dev/null
	# Note: `uv` does python package installs much faster, but as of now
	# it doesn't support the use of --system-site-packages.
	# See: https://github.com/astral-sh/uv/issues/4466
	# The framework in this script exists to switch to using `uv` once that happens.
	# It's as simple as uncommenting the below.
	# "${VENVPATH}/bin/pip3" install --upgrade uv >/dev/null
	# if [ -f "${VENVPATH}/bin/activate" ];then
	# 	export VIRTUAL_ENV=$VENVPATH
	# 	source ."${VENVPATH}/bin/activate" >/dev/null
	# fi
fi
echo ""
STAGEA=$(date '+%s')
if [ ! -f "$CHECK_FILE" ] || [ "$CFLAG" = true ]; then
	echo -e "${NC}Stage 1 of setup took $((STAGEA - STARTTIME)) seconds.${FADE}"
fi

if command -v tmux 2>&1 >/dev/null; then
	TMUX_AVAIL=true
else
	TMUX_AVAIL=false
	if [ "$TFLAG" = true ]; then
	echo -e "${NC}${ORANGE}>>> Warning: tmux option was selected but tmux is not present on the system.${NC}${FADE}"
	fi
fi

echo -e "${NC}> System image ready.${FADE}"
echo -n "> We have: "
"${VENVPATH}/bin/python3" -VV

CHECKMARK='\e[1F\e[30C[ Done ]\n' # move cursor up to the beginning one line up then move 30 spaces right
# install dependencies
if [ $SKIP_CHECK -eq 0 ] || [ "$CFLAG" = true ]; then
	echo ""
	echo -e "${NC}> Packages check:${FADE}"
	if [ -f "${VENVPATH}/bin/uv" ]; then
		VENVCMD="${VENVPATH}/bin/uv pip"
	else
		VENVCMD="${VENVPATH}/bin/pip3"
	fi
	if [ $INTERNET_STAT -eq 0 ]; then
		echo -e "${FADE}${VERB_TEXT}pip"
		"${VENVPATH}/bin/python3" -m pip install --upgrade pip >/dev/null
		if [ $RGBMATRIX_PRESENT -eq 3 ]; then
			echo -e "${CHECKMARK}${FADE}${VERB_TEXT}rgbmatrix"
			"${VENVCMD}" install -e "${USER_HOME}/rpi-rgb-led-matrix/bindings/python" --use-pep517 >/dev/null
		fi
		echo -e "${CHECKMARK}${FADE}${VERB_TEXT}requests"
		"${VENVCMD}" install --upgrade requests >/dev/null
		echo -e "${CHECKMARK}${FADE}${VERB_TEXT}pydispatcher"
		"${VENVCMD}" install --upgrade pydispatcher >/dev/null
		echo -e "${CHECKMARK}${FADE}${VERB_TEXT}schedule"
		"${VENVCMD}" install --upgrade schedule >/dev/null
		echo -e "${CHECKMARK}${FADE}${VERB_TEXT}suntime"
		"${VENVCMD}" install --upgrade suntime >/dev/null
		echo -e "${CHECKMARK}${FADE}${VERB_TEXT}psutil"
		"${VENVCMD}" install --upgrade psutil >/dev/null
		echo -e "${CHECKMARK}${FADE}${VERB_TEXT}yaml"
		"${VENVCMD}" install --upgrade ruamel.yaml >/dev/null
		echo -e "${CHECKMARK}${FADE}${VERB_TEXT}orjson"
		"${VENVCMD}" install --upgrade orjson >/dev/null
		if [ "$VERB_TEXT" == "Installing: " ]; then
			echo -e "${CHECKMARK}${FADE}"
			echo "(The next install may take some time, please be patient.)"
			echo -e "${VERB_TEXT}RGBMatrixEmulator"
		else
			echo -e "${CHECKMARK}${FADE}${VERB_TEXT}RGBMatrixEmulator"
		fi
		"${VENVCMD}" install --upgrade RGBMatrixEmulator >/dev/null
		if [ $WEB_INT -eq 1 ]; then
			systemctl stop flightgazer-webapp >/dev/null 2>&1
			echo -e "${CHECKMARK}${FADE}"
			echo "Web-app components:"
			echo "${VERB_TEXT}Flask"
			"${VENVCMD}" install --upgrade Flask >/dev/null
			echo -e "${CHECKMARK}${FADE}${VERB_TEXT}gunicorn"
			"${VENVCMD}" install --upgrade gunicorn >/dev/null
			systemctl start flightgazer-webapp >/dev/null 2>&1
		fi
		echo -e "${CHECKMARK}${NC}░░░▒▒▓▓ Completed ▓▓▒▒░░░\n${FADE}"
	else
		echo -e "${ORANGE}  Skipping due to no internet.${NC}${FADE}"
	fi
	touch "$LOGFILE"
	chown -f ${OWNER_OF_FGDIR}:${GROUP_OF_FGDIR} "$LOGFILE" >/dev/null 2>&1
	chmod -f 777 "${LOGFILE}" >/dev/null 2>&1
	STAGEB=$(date '+%s')
	echo -e "${NC}Stage 2 of setup took $((STAGEB - STAGEA)) seconds.${FADE}"
	# start the database updater/generator
	echo -e "${NC}> Fetching latest aircraft database...${FADE} (this might take some time)"
	if [ -f "$DB_DOWNLOADER" ]; then
		"${VENVPATH}/bin/python3" "$DB_DOWNLOADER"
		if [ $? -ne 0 ]; then
			echo -e "${NC}${ORANGE}> Failed to generate database.${NC}"
			echo "You can try again at a later time by running"
			echo -e "${VENVPATH}/bin/python3 ${DB_DOWNLOADER}"
			echo "in your console."
		else
			echo -e "${NC}> Success."
			if [ -f "${BASEDIR}/utilities/database.db" ]; then
				chown -f ${OWNER_OF_FGDIR}:${GROUP_OF_FGDIR} "${BASEDIR}/utilities/database.db" >/dev/null 2>&1
			fi
		fi
	else
		echo -e "${NC}${ORANGE}> Unable to check or generate aircraft database"
		echo "  due to downloader script missing.${NC}${FADE}"
	fi
	if [ $INTERNET_STAT -eq 0 ]; then
		touch $CHECK_FILE
	fi
fi

if [ -f "$LOGFILE" ]; then
	LOGLENGTH=$(wc -l < "$LOGFILE")
	if [ $LOGLENGTH -gt 2000 ]; then
		time_now=$(date '+%Y-%m-%d %H:%M')
		echo "$(tail -n 2000 $LOGFILE)" > "$LOGFILE"
		sed -i -e "1i********** $time_now --- This logfile has been truncated to the latest 2000 lines. (was $LOGLENGTH) **********\\" "$LOGFILE"
		echo "> Logfile housekeeping: truncated logfile to latest 2000 lines. (was $LOGLENGTH)"
	fi
fi

ENDTIME=$(date '+%s')
echo "Setup/Initialization took $((ENDTIME - STARTTIME)) seconds."
echo -e "${NC}"
echo -e "${GREEN}>>> Dependencies check complete."
if [ $SKIP_CHECK -eq 1 ] && [ "$DFLAG" = "" ] && [ "$CFLAG" = false ]; then
	echo -e "${NC}${FADE}> Playing splash screen for 5 seconds..."
	sleep 6s # give an extra second to fire up the screen
	kill -15 $(ps aux | grep '[s]plash.py' | awk '{print $2}') > /dev/null 2>&1
fi
echo -e "${ORANGE}>>> Entering main loop!${NC}"
kill -15 $(ps aux | grep '[s]plash.py' | awk '{print $2}') > /dev/null 2>&1
trap - INT # reset the signal handler

echo -ne "${FADE}"
echo ""
echo "     _/_/_/_/ _/_/    _/            _/        _/                          ";
echo "    _/         _/         _/_/_/   _/_/_/  _/_/_/_/                       ";
echo "   _/_/_/     _/    _/   _/    _/ _/    _/  _/                            ";
echo "  _/         _/    _/   _/    _/ _/    _/  _/                             ";
echo " _/         _/_/    _/   _/_/_/ _/    _/    _/_/                          ";
echo "                            _/                     by: WeegeeNumbuh1      ";
echo "                       _/_/     _/_/_/                                    ";
echo "                             _/         _/_/_/ _/_/_/_/   _/_/   _/  _/_/ ";
echo "                            _/  _/_/ _/    _/     _/   _/_/_/_/ _/_/      ";
echo "                           _/    _/ _/    _/   _/     _/       _/         ";
echo "                            _/_/_/   _/_/_/ _/_/_/_/   _/_/_/ _/          ";

echo ""
if [ "$CFLAG" = true ]; then
	echo -e "${NC}${ORANGE}>>> Install-only/dependency check was requested. Not starting main script.${NC}"
	sleep 2s
	exit 0
else
	# fire up the script and watch over it
	echo -e "> Running main script with additional options: [ ${DFLAG} ${EFLAG} ${FFLAG} ${VFLAG} ]"
	if [ -t 1 ]; then
		# always have the -i interactive flag in use if no other options are given
		echo -e "${GREEN}> We're running in an interactive shell. Program output will be shown.${NC}${FADE}"
		if [ "$TMUX_AVAIL" = true ] && [ "$TFLAG" = true ]; then
			tmux new-session -d -s FlightGazer "nice -n -4 ionice -c 2 -n 2 \"${VENVPATH}/bin/python3\" \"${BASEDIR}/FlightGazer.py\" -i ${DFLAG} ${EFLAG} ${FFLAG} ${VFLAG}"
			echo -e "${NC}${ORANGE}>>> Successfully started in tmux."
			echo -e "    Use 'sudo tmux attach' or 'sudo tmux attach -d -t FlightGazer' to see the output!${NC}\n"
			sleep 1s
			exit 0
		else
			trap interrupt SIGINT SIGTERM SIGHUP
			echo -e "${GREEN}  Running in tmux is recommended for extended runs!\n${NC}${FADE}"
			echo -e "\n${NC}${RED}>>> Use Ctrl+C to quit.${NC}${FADE}"
			if [ "$TMUX_AVAIL" = false ] && [ "$TFLAG" = true ]; then
				echo "> Notice: Program will be running in this console window as tmux is not available!"
				sleep 2s
			fi
			TRADITIONAL_START=true
			nice -n -4 ionice -c 2 -n 2 "${VENVPATH}/bin/python3" "${BASEDIR}/FlightGazer.py" -i ${DFLAG} ${EFLAG} ${FFLAG} ${VFLAG} & child_pid=$!
			wait "$child_pid"
		fi
	else
		# edit the entry in /etc/systemd/system/flightgazer.service manually if you want to start with additional flags
		# then use `systemctl daemon-reload` to use the updated settings
		if [ "$TMUX_AVAIL" = true ] && [ "$TFLAG" = true ]; then
			tmux new-session -d -s FlightGazer "nice -n -4 ionice -c 2 -n 2 \"${VENVPATH}/bin/python3\" \"${BASEDIR}/FlightGazer.py\" -i ${DFLAG} ${EFLAG} ${FFLAG} ${VFLAG}"
			echo -e "${NC}${ORANGE}>>> Successfully started in tmux."
			echo -e "    Use 'sudo tmux attach' or 'sudo tmux attach -d -t FlightGazer' to see the output!${NC}\n"
			# keep-alive, assuming this is a simple systemd service
			# we watch the amount of processes running that match the script name
			# and if we terminate it internally we break out and tell systemd we shutdown gracefully
			# while [ $(ps aux | grep '[F]lightGazer.py' | awk '{print $2}' | wc -l) -ne 0 ];
			# do
			# 	sleep 2
			# done
			# echo -e "${GREEN}>>> Shutdown commanded internally.${NC}"
			exit 0
		else
			trap terminate SIGTERM
			TRADITIONAL_START=true
			# don't parse arguments that enable interactive modes
			nice -n -4 ionice -c 2 -n 2 "${VENVPATH}/bin/python3" "${BASEDIR}/FlightGazer.py" ${EFLAG} ${VFLAG} & child_pid=$!
			wait "$child_pid"
		fi
	fi
fi
# the following will only run if the python script exits with an error
if [ "$TRADITIONAL_START" = true ]; then
	>&2 echo -e "\n${NC}${RED}>>> Warning: Script exited unexpectedly.
             Please review the output above for error details.${NC}"
	exit 1
fi