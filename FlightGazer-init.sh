#!/bin/bash
# Initialization/bootstrap script for FlightGazer.py
# Repurposed from my other project, "UNRAID Status Screen"
# For changelog, check the 'changelog.txt' file.
# Version = v.4.2.5
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
CHECK_FILE=${VENVPATH}/first_run_complete
PROFILING_FLAG=${BASEDIR}/profile
THIS_FILE=${BASEDIR}/FlightGazer-init.sh
LOGFILE=${BASEDIR}/FlightGazer-log.log
INTERNET_STAT=0 # think return codes
SKIP_CHECK=0 # 0 = do not skip dependency checks, 1 = skip

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
	echo "Usage: sudo bash $BASEDIR/$(basename $0) [options]"
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
	echo "[-c]     Install/check dependencies only. Do not start main script."
	echo "[-l]     Live/Demo mode: Setup in /tmp, no permanent install."
	echo ""
	echo "Report bugs to WeegeeNumbuh1 <https://github.com/WeegeeNumbuh1/FlightGazer>"
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
	VER_STR=$(head -c 12 ${BASEDIR}/version)
	echo -e "    Version: ${VER_STR}"
fi
if [ `id -u` -ne 0 ]; then
	>&2 echo -e "${RED}>>> ERROR: This script must be run as root.${NC}"
	sleep 1s
	exit 1
fi

if [[ $(ps aux | grep '[F]lightGazer.py' | awk '{print $2}') ]]; then
	echo -e "\n${NC}${RED}>>> ERROR: FlightGazer is already running.${NC}"
	echo "These are the process IDs detected:"
	ps aux | grep '[F]lightGazer.py' | awk '{print $2}'
	echo -e "\n${ORANGE}>>> FlightGazer can only have one running instance at a time.${NC}"
	echo "To stop the other running instance, use:"
	echo "'sudo systemctl stop flightgazer.service' -or-"
	echo "'sudo tmux attach -d -t FlightGazer' and press Ctrl+C -or-"
	echo 'kill -15 $(ps aux | grep '"'"'[F]lightGazer.py'"'"' | awk '"'"'{print \$2}'"'"')'
	sleep 2s
	exit 1
fi

echo -e "${GREEN}>>> Checking dependencies, let's begin.${NC}"
echo -e "${FADE}"

if [ ! -f "${BASEDIR}/FlightGazer.py" ]; then
	echo -e "\n${NC}${RED}>>> ERROR: Cannot find ${BASEDIR}/FlightGazer.py."
	sleep 2s
	exit 1
fi

if [ ! -f "$CHECK_FILE" ];
then 
	echo "> First run detected, installing needed dependencies.
  This may take some time depending on your internet connection."
	if [ "$LFLAG" = true ]; then
		echo "****************************************************************************"
		echo "> We are currently running in Live/Demo mode; no permanent changes to"
		echo "  the system will occur. FlightGazer will run using dependencies in '/tmp'."
		echo "****************************************************************************"
	fi
	VERB_TEXT='Installing: '
else
	echo -n "> Last dependencies check: "
	date -r $CHECK_FILE
	last_check_time=$(date -r $CHECK_FILE '+%s')
	# 1 month = 2592000 seconds
	if [ $((STARTTIME - last_check_time)) -lt 7776000 ]; then
		echo "> Last check was less than 3 months ago, skipping tests 👍"
		SKIP_CHECK=1
	fi
	VERB_TEXT='Checking: '
fi

if [ $SKIP_CHECK -eq 0 ]; then
	echo "> Checking system image..."

	# check if this system uses apt
	command -v apt 2>&1 >/dev/null
	if [ $? -ne 0 ]; then
		echo -e "${NC}${RED}>>> ERROR: Initial setup cannot continue. This system does not use apt.${NC}"
		sleep 2s
		exit 1
	fi

	# check if this is a systemd system
	command -v systemctl --version 2>&1 >/dev/null
	if [ $? -ne 0 ]; then
		echo -e "${NC}${RED}>>> ERROR: Initial setup cannot continue. This system does not use systemd.${NC}"
		sleep 2s
		exit 1
	fi

	# check internet connection
	wget -q --timeout=10 --spider http://google.com
	if [ $? -ne 0 ]; then
		INTERNET_STAT=1
		>&2 echo -e "${NC}${RED}>>> Warning: Failed to connect to internet. File checking will be skipped.${FADE}"
	fi

	if [ ! -f "$CHECK_FILE" ] && [ $INTERNET_STAT -eq 1 ] && [ ! -d "$VENVPATH" ]; then
		>&2 echo -e "${NC}${RED}>>> ERROR: Initial setup cannot continue. Internet connection is required.${NC}"
		sleep 2s
		exit 1
	fi

	if [ $INTERNET_STAT -eq 0 ]; then
		echo "  > Internet connectivity available, initial setup can continue."
		read -r OWNER_OF_FGDIR GROUP_OF_FGDIR <<<$(stat -c "%U %G" ${BASEDIR})
	fi
fi

# start the splash screen
if [ "$DFLAG" != "-d" ]; then
	nohup python $BASEDIR/utilities/splash.py $BASEDIR/FG-Splash.ppm >/dev/null 2>&1 &
fi

if [ ! -f "$CHECK_FILE" ];
then
	echo "  > Updating package lists..."
	echo "    > \"apt-get update\""
	echo "      (this may take some time if this hasn't been run in awhile)"
	apt-get update >/dev/null
	echo "    > \"dpkg --configure -a\""
	dpkg --configure -a >/dev/null
	echo ""
	echo "  > Installing needed dependencies..."
	echo "    > \"python3-dev\""
	apt-get install -y python3-dev >/dev/null
	echo "    > \"python3-venv\""
	apt-get install -y python3-venv >/dev/null
	echo "    > \"tmux\""
	apt-get install -y tmux >/dev/null
	echo ""
	echo "  > Creating systemd service..."
	if [ ! -f "/etc/systemd/system/flightgazer.service" ] && [ "$LFLAG" = false ]; then
		cat <<- EOF > /etc/systemd/system/flightgazer.service
		[Unit]
		Description=FlightGazer service
		After=multi-user.target

		[Service]
		User=root
		# Note: unless the -t flag is used, DO NOT use interactive flags unless you want to spam the logs
		ExecStart=bash $THIS_FILE -t
		ExecStop=-tmux send-keys -t FlightGazer C-c || true
		ExecStop=sleep 1s
		Type=forking
		TimeoutStartSec=600
		TimeoutStopSec=5
		
		[Install]
		WantedBy=multi-user.target
		EOF
		echo -e "${FADE}"
		systemctl daemon-reload 2>&1
		systemctl enable flightgazer.service 2>&1
		systemctl status flightgazer.service
		echo -e "${NC}${FADE}    > Service installed. FlightGazer will run at boot via systemd."
	else
		echo "    > Service already exists or we are running in Live/Demo mode, skipping service creation."
	fi

	# we make a config file first because by default it will output a ton of errors
	# plus we want to take advantage of the emulator's other rendering options
	if [ ! -f "${BASEDIR}/emulator_config.json" ]; then
	echo "  > Creating RGBMatrixEmulator settings..."
	cat << EOF > ${BASEDIR}/emulator_config.json
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
        "target_fps": 10,
        "fps_display": true,
        "quality": 70,
        "image_border": true,
        "debug_text": false,
        "image_format": "JPEG"
    },
    "log_level": "info"
}
EOF
	chown -f ${OWNER_OF_FGDIR}:${GROUP_OF_FGDIR} ${BASEDIR}/emulator_config.json >/dev/null 2>&1
	echo "    > RGBMatrixEmulator settings created."
	fi
fi

if [ ! -d "$VENVPATH" ]; then
	mkdir ${VENVPATH}
	echo ""
	echo "  > Making virtual environment... (this may take awhile)"
	python3 -m venv --system-site-packages ${VENVPATH}
fi
echo ""

if command -v tmux 2>&1 >/dev/null; then
	TMUX_AVAIL=true
else
	TMUX_AVAIL=false
	if [ "$TFLAG" = true ]; then
	echo -e "${NC}${ORANGE}>>> Warning: tmux option was selected but tmux is not present on the system.${NC}${FADE}"
	fi
fi

echo "> System image ready."
echo -n "> We have: "
${VENVPATH}/bin/python3 -VV

CHECKMARK='\e[1F\e[30C✅\n' # move cursor up to the beginning one line up then move 30 spaces right
# install dependencies
if [ -f "$PROFILING_FLAG" ]; then
	echo -e "ℹ️ Profiling flag detected\n -> ${VERB_TEXT}scalene"
	pip install --upgrade scalene >/dev/null
fi

if [ $SKIP_CHECK -eq 0 ]; then
	echo ""
	echo "> Packages check:"
	if [ $INTERNET_STAT -eq 0 ]; then
		echo -e "${VERB_TEXT}pip"
		${VENVPATH}/bin/python3 -m pip install --upgrade pip >/dev/null
		echo -e "${CHECKMARK}${VERB_TEXT}requests"
		${VENVPATH}/bin/pip3 install --upgrade requests >/dev/null
		echo -e "${CHECKMARK}${VERB_TEXT}pydispatcher"
		${VENVPATH}/bin/pip3 install --upgrade pydispatcher >/dev/null
		echo -e "${CHECKMARK}${VERB_TEXT}schedule"
		${VENVPATH}/bin/pip3 install --upgrade schedule >/dev/null
		echo -e "${CHECKMARK}${VERB_TEXT}suntime"
		${VENVPATH}/bin/pip3 install --upgrade suntime >/dev/null
		echo -e "${CHECKMARK}${VERB_TEXT}psutil"
		${VENVPATH}/bin/pip3 install --upgrade psutil >/dev/null
		echo -e "${CHECKMARK}${VERB_TEXT}yaml"
		${VENVPATH}/bin/pip3 install --upgrade ruamel.yaml >/dev/null
		echo -e "${CHECKMARK}${VERB_TEXT}orjson"
		${VENVPATH}/bin/pip3 install --upgrade orjson >/dev/null
		echo -e "${CHECKMARK}${VERB_TEXT}RGBMatrixEmulator"
		${VENVPATH}/bin/pip3 install --upgrade RGBMatrixEmulator >/dev/null
		echo -e "${CHECKMARK}░░░▒▒▓▓ Completed ▓▓▒▒░░░\n"
	else
		echo "  Skipping due to no internet."
	fi
	touch $CHECK_FILE
	touch $LOGFILE
	chown -f ${OWNER_OF_FGDIR}:${GROUP_OF_FGDIR} ${LOGFILE} >/dev/null 2>&1
	chmod -f 777 ${LOGFILE} >/dev/null 2>&1
fi

if [ -f "$LOGFILE" ]; then
	LOGLENGTH=$(wc -l < $LOGFILE)
	if [ $LOGLENGTH -gt 1000 ]; then
		time_now=$(date '+%Y-%m-%d %H:%M')
		echo "$(tail -n 1000 $LOGFILE)" > $LOGFILE
		sed -i -e "1i********** $time_now --- This logfile has been truncated to the latest 1000 lines. (was $LOGLENGTH) **********\\" $LOGFILE
		echo "> Logfile housekeeping: truncated logfile to latest 1000 lines. (was $LOGLENGTH)"
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
	echo -e "${NC}${ORANGE}>>> Install-only/dependency check was requested. Not starting main script."
	sleep 2s
	exit 0
else
	# fire up the script and watch over it
	echo -e "> Running main script with additional options: [ ${DFLAG} ${EFLAG} ${FFLAG} ${VFLAG} ]"
	if [ ! -f "$PROFILING_FLAG" ];
	then
		if [ -t 1 ]; then
			# always have the -i interactive flag in use if no other options are given
			echo -e "${GREEN}> We're running in an interactive shell. Program output will be shown.${NC}${FADE}"
			if [ "$TMUX_AVAIL" = true ] && [ "$TFLAG" = true ]; then
				tmux new-session -d -s FlightGazer "sudo ${VENVPATH}/bin/python3 ${BASEDIR}/FlightGazer.py -i ${DFLAG} ${EFLAG} ${FFLAG} ${VFLAG}"
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
				fi
				TRADITIONAL_START=true
				sudo ${VENVPATH}/bin/python3 ${BASEDIR}/FlightGazer.py -i ${DFLAG} ${EFLAG} ${FFLAG} ${VFLAG} & child_pid=$!
				wait "$child_pid"
			fi
		else 
			# edit the entry in /etc/systemd/system/flightgazer.service manually if you want to start with additional flags
			# then use `systemctl daemon-reload` to use the updated settings
			if [ "$TMUX_AVAIL" = true ] && [ "$TFLAG" = true ]; then
				tmux new-session -d -s FlightGazer "sudo ${VENVPATH}/bin/python3 ${BASEDIR}/FlightGazer.py -i ${DFLAG} ${EFLAG} ${FFLAG} ${VFLAG}"
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
				sudo ${VENVPATH}/bin/python3 ${BASEDIR}/FlightGazer.py ${EFLAG} ${VFLAG} & child_pid=$!
				wait "$child_pid"
			fi
		fi
	else
		echo -e "${ORANGE}>>> ⚠️ Profiling enabled. You MUST run the below command in a new console window!"
		echo -e "${VENVPATH}/bin/python3 -m scalene --cli --reduced-profile --profile-interval 60 ${BASEDIR}/FlightGazer.py \n"
		echo "Note: this can only be run once. This terminal must be restarted to profile again."
		echo "--- To disable profiling on the next run, rename or delete the \"profile\" file."
		python3 -c "exec(\"import time\nwhile True: time.sleep(1)\")" & child_pid=$! # to keep the session alive
		wait "$child_pid"
	fi
fi
# the following will only run if the python script exits with an error
if [ "$TRADITIONAL_START" = true ]; then
	>&2 echo -e "\n${NC}${RED}>>> Warning: Script exited unexpectedly.
             Please review the output above for error details.${NC}"
	exit 1
fi