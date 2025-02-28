#!/bin/bash
{
# Updater script for FlightGazer.py
# Last updated: v.2.7.3
# by: WeegeeNumbuh1

# Notice the '{' in the second line:
# We need bash to load this whole file into memory so that when we replace this file
# during the second-stage of the updater, we won't run into any odd behaviors.
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

set -o noclobber
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

wget -q --timeout=10 --spider http://github.com
if [ $? -ne 0 ]; then
    >&2 echo -e "${NC}${RED}>>> ERROR: Failed to connect to internet. Try again when there is internet connectivity.${NC}"
    exit 1
fi

rm -rf ${TEMPPATH} >/dev/null 2>&1 # make sure the temp directory doesn't exist before we start
echo -e "${GREEN}>>> Downloading latest version...${NC}${FADE}"
git clone --depth 1 https://github.com/WeegeeNumbuh1/FlightGazer $TEMPPATH
if [ $? -ne 0 ]; then
    echo -e "${RED}>>> ERROR: Failed to download from Github. Updater cannot continue.${NC}"
    exit 1
fi
echo -e "${GREEN}>>> Shutting down any running FlightGazer processes...${NC}${FADE}"
systemctl stop flightgazer.service
sleep 3s
kill -15 $(ps aux | grep '[F]lightGazer.py' | awk '{print $2}') >/dev/null 2>&1 # ensure nothing remains running
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
if [ -f "$BASEDIR/config.py" -a ! -f "$BASEDIR/config.yaml" ]; then
    echo "> Old version of FlightGazer detected. You must migrate your settings manually."
    mv ${BASEDIR}/config.py ${BASEDIR}/config_old.py >/dev/null 2>&1
    chown -f ${OWNER_OF_FGDIR}:${GROUP_OF_FGDIR} ${BASEDIR}/config_old.py >/dev/null 2>&1
    chmod -f 644 ${BASEDIR}/config_old.py >/dev/null 2>&1
    OLDER_BUILD=1
else
    time_now=$(date '+%Y-%m-%d %H:%M')
    echo -e "--- FlightGazer settings migration log. ${time_now} ---" >> $MIGRATE_LOG
    ${VENVPATH}/bin/python3 ${BASEDIR}/utilities/settings_migrator.py ${BASEDIR}/config.yaml ${TEMPPATH}/config.yaml | tee -a $MIGRATE_LOG
    if [ $? -ne 0 ]; then
        MIGRATE_FLAG=1
    fi
fi
echo -n "> Migrating color configuration... "
grep -q "# CONFIG_START" ${BASEDIR}/setup/colors.py >/dev/null 2>&1 # check that this is using the newer-style
if [ $? -eq 0 ]; then
    color_migrator ${TEMPPATH}/setup/colors.py ${BASEDIR}/setup/colors.py > ${TEMPPATH}/colors_migrated
    mv -f ${TEMPPATH}/colors_migrated ${TEMPPATH}/setup/colors.py >/dev/null 2>&1
    echo "Done."
else
    echo -e "\n> Older version of colors.py detected. Updating to newer version in this update."
fi
cp -f ${BASEDIR}/flybys.csv ${TEMPPATH}/flybys.csv >/dev/null 2>&1 # copy flyby stats file if present
cp -f ${BASEDIR}/config.yaml ${TEMPPATH}/config_old.yaml >/dev/null 2>&1 # create backup of old config file
echo -e "${NC}${GREEN}>>> Installing latest version of FlightGazer... ${NC}${FADE}"
rm -f ${VENVPATH}/first_run_complete >/dev/null 2>&1 # force the init script to update the venv for any changes
# transfer execution to another script as this current script will get overwritten
TEMP_SCRIPT='/tmp/FG_update_step2.sh'
echo '#!/bin/bash' >| $TEMP_SCRIPT
echo '# stage 2 updater for FlightGazer' >> $TEMP_SCRIPT
echo "FGDIR=${BASEDIR}" >> $TEMP_SCRIPT
echo "TEMPDIR=${TEMPPATH}" >> $TEMP_SCRIPT
echo "FADE='\033[2m'" >> $TEMP_SCRIPT
echo "ORANGE='\033[0;33m'" >> $TEMP_SCRIPT
echo "GREEN='\033[0;32m'" >> $TEMP_SCRIPT
echo "NC='\033[0m'" >> $TEMP_SCRIPT
echo "MF=${MIGRATE_FLAG}" >> $TEMP_SCRIPT
echo "OB=${OLDER_BUILD}" >> $TEMP_SCRIPT
echo "FG_O=${OWNER_OF_FGDIR}" >> $TEMP_SCRIPT
echo "FG_G=${GROUP_OF_FGDIR}" >> $TEMP_SCRIPT
echo '' >> $TEMP_SCRIPT
cat >> ${TEMP_SCRIPT} <<'EOF'
# if there are additonal files in the install directory that aren't in the latest commit,
# simply leave them be in the install directory (they could be user files)
chown -Rf ${FG_O}:${FG_G} $TEMPDIR # need to do this as we are running as root
echo -e "${FADE}Copying $TEMPDIR to $FGDIR..."
cp -TR ${TEMPDIR} ${FGDIR}
chown -f ${FG_O}:${FG_G} $FGDIR/config.yaml
chmod -f 644 $FGDIR/config.yaml
chown -f ${FG_O}:${FG_G} $FGDIR/flybys.csv >/dev/null 2>&1
chmod -f 644 $FGDIR/flybys.csv >/dev/null 2>&1
echo -e "${NC}${GREEN}>>> Restarting FlightGazer...${NC}${FADE}"
systemctl is-enabled flightgazer.service >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "> Service does not exist!"
    echo -e "${ORANGE}> You must restart FlightGazer manually."
else
    if [ "$(systemctl is-enabled flightgazer.service)" = "disabled" ]; then
        echo "> Service is disabled!"
        echo -e "${ORANGE}> You must restart FlightGazer manually."
    else
        systemctl start flightgazer.service &
        echo -e "> FlightGazer started.\n${ORANGE}> It may take a few minutes for the display to start as the system prepares itself!"
    fi
fi
echo -e "${NC}${GREEN}>>> Update complete.${NC}"
if [ $MF -eq 1 ]; then
    echo -e "${ORANGE}>>> Warning: Settings migrator failed during the update process.${NC}"
    echo "    FlightGazer is currently running with default settings."
    echo "    If 'config.yaml' was present, your previous settings"
    echo -e "    are in a file named 'config_old.yaml' in ${FGDIR}"
    echo "    You must migrate your settings manually, then restart FlightGazer."
    echo "    Restart using 'sudo systemctl restart flightgazer.service'"
    sleep 5s
fi
if [ $OB -eq 1 ]; then
    echo -e "${ORANGE}>>> Notice: FlightGazer is currently running on default settings.${NC}"
    echo -e "    Your previous configuration file has been renamed 'config_old.py' in ${FGDIR}"
    echo "    Please update your settings in the new configuration file 'config.yaml',"
    echo "    then restart FlightGazer."
    echo "    Restart using 'sudo systemctl restart flightgazer.service'" 
    sleep 5s
fi
exit 0
EOF
chmod +x ${TEMP_SCRIPT}
sudo bash ${TEMP_SCRIPT}
exit 0
}