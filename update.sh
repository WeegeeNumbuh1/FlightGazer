#!/bin/bash
# Updater script for FlightGazer.py
# Version = v.2.0.0
# by: WeegeeNumbuh1
BASEDIR=$(cd `dirname -- $0` && pwd)
TEMPPATH=/tmp/FlightGazer-tmp
VENVPATH=/etc/FlightGazer-pyvenv
MIGRATE_LOG=${BASEDIR}/settings_migrate.log
GREEN='\033[0;32m'
ORANGE='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
MIGRATE_FLAG=0
OLDER_BUILD=0

echo -ne "\033]0;FlightGazer Updater\007" # set window title
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

wget -q --timeout=10 --spider http://github.com
if [ $? -ne 0 ]; then
    >&2 echo -e "${NC}${RED}>>> ERROR: Failed to connect to internet. Try again when there is internet connectivity.${NC}"
    exit 1
fi

rm -rf ${TEMPPATH} 2>&1 >/dev/null # make sure the temp directory doesn't exist before we start
echo -e "${GREEN}>>> Downloading latest version...${NC}${FADE}"
git clone --depth 1 https://github.com/WeegeeNumbuh1/FlightGazer $TEMPPATH
if [ $? -ne 0 ]; then
    echo -e "${RED}>>> ERROR: Failed to download from Github. Updater cannot continue.${NC}"
    exit 1
fi
echo -e "${GREEN}>>> Shutting down any running FlightGazer processes...${NC}${FADE}"
systemctl stop flightgazer.service
sleep 1s
kill -15 $(ps aux | grep '[F]lightGazer.py' | awk '{print $2}') # ensure nothing remains running
echo -e "${NC}${GREEN}>>> Migrating settings...${NC}${FADE}"
if [ -f "$BASEDIR/config.py" -a ! -f "$BASEDIR/config.yaml" ]; then
    echo "    > Old version of FlightGazer detected. You must migrate your settings manually."
    mv ${BASEDIR}/config.py ${BASEDIR}/config_old.py 2>&1 >/dev/null
    OLDER_BUILD=1
else
    time_now=$(date '+%Y-%m-%d %H:%M')
    echo -e "--- FlightGazer settings migration log. ${time_now} ---" >> $MIGRATE_LOG
    ${VENVPATH}/bin/python3 ${BASEDIR}/utilities/settings_migrator.py ${BASEDIR}/config.yaml ${TEMPPATH}/config.yaml | tee -a $MIGRATE_LOG
    if [ $? -ne 0 ]; then
        MIGRATE_FLAG=1
    fi
fi
cp -f ${BASEDIR}/flybys.csv ${TEMPPATH}/flybys.csv 2>&1 >/dev/null # copy flyby stats file if present
cp -f ${BASEDIR}/config.yaml ${BASEDIR}/config_old.yaml 2>&1 >/dev/null # create backup of old config file
echo -e "${NC}${GREEN}>>> Installing latest version of FlightGazer... ${NC}${FADE}"
rm -f ${VENVPATH}/first_run_complete 2>&1 >/dev/null # force the init script to update the venv for any changes
# if there are additonal files not pulled from the latest commit, simply leave them be in the install directory
cp -Tf ${TEMPPATH} ${BASEDIR} 2>&1 >/dev/null
# nb: we are also likely rewriting this script with the above command. It *should* be fine as this current copy
#     *should* be in memory at this point. See: https://unix.stackexchange.com/questions/121013/how-does-linux-deal-with-shell-scripts
echo -e "${NC}${GREEN}>>> Restarting FlightGazer...${NC}${FADE}"
systemctl start flightgazer.service
echo -e "${NC}${GREEN}>>> Update complete.${NC}"
if [ $MIGRATE_FLAG -e 1 ]; then
    echo -e "${ORANGE}>>> Warning: Settings migrator failed during the update process.${NC}"
    echo "    FlightGazer is currently running with default settings."
    echo -e "    Your previous settings are in a file named 'config_old.yaml' in ${BASEDIR}"
    echo "    You must migrate your settings manually, then restart FlightGazer."
    echo "    Restart using 'sudo systemctl restart flightgazer.service'"
    sleep 5s
fi
if [ $OLDER_BUILD -e 1 ]; then
    echo -e "${ORANGE}>>> Notice: FlightGazer is currently running on default settings.${NC}"
    echo -e "    Your previous configuration file has been renamed 'config_old.py' in ${BASEDIR}"
    echo "    Please update your settings in the new configuration file 'config.yaml',"
    echo "    then restart FlightGazer."
    echo "    Restart using 'sudo systemctl restart flightgazer.service'" 
    sleep 5s
fi
exit 0