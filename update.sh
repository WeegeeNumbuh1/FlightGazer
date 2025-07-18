#!/bin/bash
{
# Updater script for FlightGazer
# Last updated: v.7.1.1
# by: WeegeeNumbuh1

# Notice the '{' in the second line:
# We need bash to load this whole file into memory so that when we replace this file
# we won't run into any odd behaviors.
# See here: https://stackoverflow.com/a/2358432
BASEDIR=$(cd `dirname -- $0` && pwd)
TEMPPATH=/tmp/FlightGazer-tmp
VENVPATH=/etc/FlightGazer-pyvenv
MIGRATE_LOG=${TEMPPATH}/settings_migrate.log
GREEN='\033[0;32m'
ORANGE='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
FADE='\033[2m'
MIGRATE_FLAG=0
OLDER_BUILD=0
OWNER_OF_FGDIR='nobody'
GROUP_OF_FGDIR='nogroup'
RESET_FLAG=0 # 1 = reset settings when updating

help_str(){
	echo ""
	echo "Usage: sudo bash $BASEDIR/$(basename $0) [options]"
	echo "[-h]     Print this help message."
	echo "[-r]     Reset existing configuration to default when updating."
	echo "Default (no options) updates to the latest version and migrates settings."
	echo ""
	echo "Report bugs to WeegeeNumbuh1 <https://github.com/WeegeeNumbuh1/FlightGazer>"
}

while getopts ':hr' opt; do
	case "$opt" in
		r)
		RESET_FLAG=1
		;;
		h)
		echo "This is the FlightGazer updater script."
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

echo -ne "\033]0;FlightGazer Updater\007" # set window title
echo -e "${FADE}"
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
echo -e "${NC}"
echo -e "\n${ORANGE}>>> FlightGazer updater script started."
if [ `id -u` -ne 0 ]; then
	>&2 echo -e "${RED}>>> ERROR: This script must be run as root.${NC}"
	sleep 1s
	exit 1
fi
if [ ! -f "${BASEDIR}/FlightGazer.py" ]; then
	echo -e "\n${NC}${RED}>>> ERROR: Cannot find FlightGazer.py. This updater script must be in the same directory as FlightGazer.py!${NC}"
	sleep 2s
	exit 1
fi

if [ ! -d "${VENVPATH}" ]; then
	echo -e "\n${NC}${RED}>>> ERROR: Cannot find FlightGazer virtual environment! Has FlightGazer been installed before?${NC}"
	sleep 2s
	exit 1
fi

wget -q --timeout=10 --spider http://github.com
if [ $? -ne 0 ]; then
	>&2 echo -e "${NC}${RED}>>> ERROR: Failed to connect to internet. Try again when there is internet connectivity.${NC}"
	exit 1
fi

echo -e "${GREEN}>>> Checking for updates...${NC}"
WEB_INF=0
WEB_UPDATE=0
systemctl list-unit-files flightgazer-webapp.service >/dev/null
if [ $? -eq 0 ]; then
	echo "> The web interface is present; will check for updates for that as well."
	WEB_INF=1
fi
echo ""
echo "===== FlightGazer info ====="
if [ -f "${BASEDIR}/version" ]; then
	VER_STR=$(head -c 12 ${BASEDIR}/version)
	echo -e "> Currently installed version:        ${VER_STR}"
else
	VER_STR=""
	echo -e "> ${ORANGE}Could not determine installed version!${NC}"
fi
LATEST_VER="$(wget -q -O - "https://raw.githubusercontent.com/WeegeeNumbuh1/FlightGazer/refs/heads/main/version")"
if [ -z $LATEST_VER ]; then
	echo -e "> ${ORANGE}Could not determine latest version!${NC}"
else
	echo -e "> Latest version available on GitHub: ${LATEST_VER}"
fi
if [ "$VER_STR" == "$LATEST_VER" ]; then
	echo "> The currently installed version is the same as what is available online."
	echo "  Choosing to continue the update will cause FlightGazer"
	echo "  to automatically check its dependencies on restart."
else
	echo -e "> ${GREEN}An update is available!${NC}"
fi
if [ $WEB_INF -eq 1 ]; then
	echo "===== Web Interface info ====="
	if [ -f "${BASEDIR}/web-app/version-webapp" ]; then
		VER_STR=$(head -c 12 ${BASEDIR}/web-app/version-webapp)
		echo -e "> Currently installed version:        ${VER_STR}"
	else
		VER_STR=""
		echo -e "> ${ORANGE}Could not determine installed version!${NC}"
	fi
	LATEST_VER="$(wget -q -O - "https://raw.githubusercontent.com/WeegeeNumbuh1/FlightGazer-webapp/refs/heads/master/version-webapp")"
	if [ -z $LATEST_VER ]; then
		echo -e "> ${ORANGE}Could not determine latest version!${NC}"
	else
		echo -e "> Latest version available on GitHub: ${LATEST_VER}"
	fi
	if [ "$VER_STR" == "$LATEST_VER" ]; then
		echo "> The currently installed version is the same as what is available online."
		echo "  No update to the web interface will occur."
	else
		echo -e "> ${GREEN}An update is available!${NC}"
		echo "If you continue the update, the web interface will be updated as well."
		WEB_UPDATE=1
	fi
	echo ""
fi

if [ $RESET_FLAG -eq 1 ]; then
	echo -e "${ORANGE}>>> Your settings will be reset to default if you continue.${NC}"
fi
echo ""
# do not touch the below line, the web interface looks for this to send 'y\n' to the script
echo "Would you like to update?"
while read -t 30 -p "[yY|nN]: " do_it; do
	case "$do_it" in
		"y" | "Y" | "yes" | "Yes" | "YES")
			break
			;;
		"n" | "N" | "No" | "NO")
			echo "> Update canceled. No changes have been made."
			exit 0
			;;
		*)
			echo -e "${ORANGE}> Invalid entry: ${do_it}${NC}\n"
			echo "Type 'y' to continue or 'n' to cancel."
			sleep 2s
	esac
done
if [ -z "$do_it" ]; then
	echo -e "${ORANGE}<No input received. Exiting.>${NC}"
	exit 0
fi

rm -rf ${TEMPPATH} >/dev/null 2>&1 # make sure the temp directory doesn't exist before we start
echo -e "${GREEN}>>> Downloading latest version...${NC}${FADE}"
git clone --depth=1 https://github.com/WeegeeNumbuh1/FlightGazer $TEMPPATH
if [ $? -ne 0 ]; then
	rm -rf ${TEMPPATH} >/dev/null 2>&1
	echo -e "${RED}>>> ERROR: Failed to download from GitHub. Updater cannot continue.${NC}"
	exit 1
fi
rm -rf ${TEMPPATH}/.git >/dev/null 2>&1
find "${TEMPPATH}" -type f -name '.*' -exec rm '{}' \; >/dev/null 2>&1
if [ -f "${TEMPPATH}/version" ]; then
	VER_STR=$(head -c 12 ${TEMPPATH}/version)
	echo -e "${NC}> Downloaded FlightGazer version: ${VER_STR}"
fi
echo -e "${GREEN}>>> Shutting down any running FlightGazer processes...${NC}${FADE}"
systemctl stop flightgazer.service
sleep 2s
tmux send-keys -t FlightGazer C-c >/dev/null 2>&1
sleep 1s
kill -15 $(ps aux | grep '[F]lightGazer\.py' | awk '{print $2}') >/dev/null 2>&1 # ensure nothing remains running
echo "> Done."
color_migrator () {
	file=$1 # new file
	file2=$2 # current file
	# read colors.py from latest pull up to "# CONFIG_START" line
	while read -r line; do
		if grep -q "# CONFIG_START" <<< "$line"; then
			break
		fi
		echo "$line"
		done < "$file"
	# read colors.py from current install from and including "# CONFIG_START" line to end of file
	sed -n '/# CONFIG_START/,$p' $file2
}
echo -e "${NC}${GREEN}>>> Migrating settings...${NC}${FADE}"
# get current owner of the install directory
read -r OWNER_OF_FGDIR GROUP_OF_FGDIR <<<$(stat -c "%U %G" ${BASEDIR})
echo -e "> ${BASEDIR} | Owner: ${OWNER_OF_FGDIR}, Group: ${GROUP_OF_FGDIR}"
if [ -f "$BASEDIR/settings_migrate.log" ]; then
	cp -p "$BASEDIR/settings_migrate.log" ${TEMPPATH} >/dev/null 2>&1
fi
if [ -f "$BASEDIR/config.py" ] && [ ! -f "$BASEDIR/config.yaml" ]; then
	echo "> Old version of FlightGazer detected. You must migrate your settings manually."
	mv ${BASEDIR}/config.py ${BASEDIR}/config_old.py >/dev/null 2>&1
	chown -f ${OWNER_OF_FGDIR}:${GROUP_OF_FGDIR} ${BASEDIR}/config_old.py >/dev/null 2>&1
	chmod -f 644 ${BASEDIR}/config_old.py >/dev/null 2>&1
	OLDER_BUILD=1
else
	time_now=$(date '+%Y-%m-%d %H:%M')
	echo -e "\n--- FlightGazer settings migration log. ${time_now} ---" >> $MIGRATE_LOG
	if [ $RESET_FLAG -eq 0 ]; then
		${VENVPATH}/bin/python3 ${BASEDIR}/utilities/settings_migrator.py ${BASEDIR}/config.yaml ${TEMPPATH}/config.yaml | tee -a $MIGRATE_LOG
		if [ $? -ne 0 ]; then
			MIGRATE_FLAG=1
		fi
	else
		echo "> Settings have been reset to default during this update." | tee -a $MIGRATE_LOG 
		echo "  Please reconfigure as necessary." | tee -a $MIGRATE_LOG
	fi
fi
if [ $RESET_FLAG -eq 0 ]; then
	echo -n "> Migrating color configuration... " | tee -a $MIGRATE_LOG
	grep -q "# CONFIG_START" ${BASEDIR}/setup/colors.py >/dev/null 2>&1 # check that this is using the newer-style
	if [ $? -eq 0 ]; then
		if [ $(wc -l < ${TEMPPATH}/setup/colors.py) -eq $(wc -l < ${BASEDIR}/setup/colors.py) ]; then
			color_migrator ${TEMPPATH}/setup/colors.py ${BASEDIR}/setup/colors.py > ${TEMPPATH}/colors_migrated
			mv -f ${TEMPPATH}/colors_migrated ${TEMPPATH}/setup/colors.py >/dev/null 2>&1
			echo "Done." | tee -a $MIGRATE_LOG
		else
			mv ${BASEDIR}/setup/colors.py ${BASEDIR}/setup/colors.bak >/dev/null 2>&1
			echo -e "\n${ORANGE}> There is a line count mismatch between the latest version and the current installed version." | tee -a $MIGRATE_LOG
			echo "  The latest version will overwrite your current color settings to default so that FlightGazer can work." | tee -a $MIGRATE_LOG
			echo "  Please reconfigure as necessary." | tee -a $MIGRATE_LOG
			echo -e "> Your previous color configuration has been backed up as: ${BASEDIR}/setup/colors.bak${NC}" | tee -a $MIGRATE_LOG
			# no need to do any fancy interim migration here, we just overwrite the file
			sleep 2s
		fi
	else
		echo -e "\n> Older version of colors.py detected. Updating to newer version in this update."
	fi
fi
cp -f ${BASEDIR}/flybys.csv ${TEMPPATH}/flybys.csv >/dev/null 2>&1 # copy flyby stats file if present
cp -f ${BASEDIR}/config.yaml ${TEMPPATH}/config_old.yaml >/dev/null 2>&1 # create backup of old config file
echo -e "${NC}${GREEN}>>> Installing latest version of FlightGazer... ${NC}${FADE}"
rm -f ${VENVPATH}/first_run_complete >/dev/null 2>&1 # force the init script to update the venv for any changes
# if there are additonal files in the install directory that aren't in the latest commit,
# simply leave them be in the install directory (they could be user files)
chown -Rf ${OWNER_OF_FGDIR}:${GROUP_OF_FGDIR} ${TEMPPATH} # need to do this as we are running as root
echo -e "${FADE}Copying ${TEMPPATH} to ${BASEDIR}..."
cp -afT ${TEMPPATH} ${BASEDIR}
chmod -f 644 ${BASEDIR}/config.yaml
# chown -fR ${OWNER_OF_FGDIR}:${GROUP_OF_FGDIR} ${BASEDIR} >/dev/null 2>&1
chmod -f 644 ${BASEDIR}/flybys.csv >/dev/null 2>&1
rm -f ${BASEDIR}/../emulator_config.json >/dev/null 2>&1 # for older installs
echo "> Copy complete."
echo -e "${NC}${GREEN}>>> Restarting FlightGazer...${NC}${FADE}"
systemctl is-enabled flightgazer.service >/dev/null 2>&1
if [ $? -ne 0 ]; then
	echo "> Service does not exist or is disabled!"
	echo -e "${ORANGE}> You must restart FlightGazer manually."
else
	nohup systemctl start flightgazer.service &
	disown # orphan the above process once the script exits so that the web interface knows this script is actually done
	echo -e "> FlightGazer started.\n${ORANGE}> It may take a few minutes for the display to start as the system prepares itself!"
fi
rm -rf ${TEMPPATH} >/dev/null 2>&1 # clean up after ourselves
if [ $WEB_UPDATE -eq 1 ]; then
	echo -e "${FADE}"
	echo "*************** Web Interface info *****************"
	echo "*   Updating the web interface in the background.  *"
	echo "* If you're viewing this log in the web interface, *"
	echo "*          please wait about 15 seconds.           *"
	echo "*     The Back to Home button may not appear.      *"
	echo "****************************************************"
	nohup bash $BASEDIR/web-app/update-webapp.sh >/dev/null 2>&1 &
	disown
fi
echo -e "${NC}${GREEN}>>> Update complete.${NC}"
echo ""
if [ $MIGRATE_FLAG -eq 1 ]; then
	echo -e "${ORANGE}>>> Warning: Settings migrator failed during the update process.${NC}"
	echo "    FlightGazer is currently running with default settings."
	echo "    If 'config.yaml' was present, your previous settings"
	echo -e "    are in a file named 'config_old.yaml' in ${BASEDIR}"
	echo "    You must migrate your settings manually, then restart FlightGazer."
	sleep 5s
fi
if [ $OLDER_BUILD -eq 1 ]; then
	echo -e "${ORANGE}>>> Notice: FlightGazer is currently running on default settings.${NC}"
	echo -e "    Your previous configuration file has been renamed 'config_old.py' in ${BASEDIR}"
	echo "    Please update your settings in the new configuration file 'config.yaml',"
	echo "    then restart FlightGazer."
	sleep 5s
fi
exit 0
}