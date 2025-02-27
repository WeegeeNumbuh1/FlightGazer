#!/bin/bash
{
# Uninstall script for FlightGazer.py
# Last updated: v.2.7.1
# by: WeegeeNumbuh1
BASEDIR=$(cd `dirname -- $0` && pwd)
TEMPPATH='/tmp/FlightGazerUninstall.sh'
GREEN='\033[0;32m'
ORANGE='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -ne "\033]0;FlightGazer Uninstall\007" # set window title
echo -e "\n${ORANGE}>>> FlightGazer uninstall script started."
echo -e "${GREEN}>>> Setting up...${NC}"
if [ `id -u` -ne 0 ]; then
	>&2 echo -e "${RED}>>> ERROR: This script must be run as root.${NC}"
	sleep 1s
	exit 1
fi
if [ ! -f "${BASEDIR}/FlightGazer.py" ]; then
	echo -e "\n${NC}${RED}>>> ERROR: Cannot find FlightGazer.py. This uninstall script must be in the same directory as FlightGazer.py!"
	sleep 2s
	exit 1
fi
echo -e "${GREEN}>>> Transferring execution to /tmp...${NC}"
set -o noclobber
echo '#!/bin/bash' >| $TEMPPATH
echo "FGDIR=$BASEDIR" >> $TEMPPATH
echo "FADE='\033[2m'" >> $TEMPPATH
echo "ORANGE='\033[0;33m'" >> $TEMPPATH
echo "RED='\033[0;31m'" >> $TEMPPATH
echo "NC='\033[0m'" >> $TEMPPATH
echo '
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

echo ""
echo -e "${NC}${RED}>>> You have 15 seconds to quit (Ctrl+C) before this script takes action.
    All files in ${ORANGE}${FGDIR}${RED} will be deleted!${NC}${FADE}"
echo -n "15... "
sleep 5s
echo -n "10... "
sleep 5s
echo -n "5... "
sleep 5s
echo ""
' >> $TEMPPATH
echo 'echo "Terminating any running FlightGazer processes..."' >> $TEMPPATH
echo -e 'kill -15 $(ps aux | grep \047[F]lightGazer.py\047 | awk \047{print $2}\047)' >> $TEMPPATH
echo 'echo "Removing any startup entries..."' >> $TEMPPATH
# sed -i -e '/^[^#]/ s/\(^.*FlightGazer.*$\)/#\ \1/' /etc/rc.local
echo -e 'sed -i -e \047/^[^#]/ s/\(^.*FlightGazer.*$\)/#\ \1/\047 /etc/rc.local 2>&1' >> $TEMPPATH
echo 'systemctl stop flightgazer.service 2>&1
systemctl disable flightgazer.service 2>&1
rm -f /etc/systemd/system/flightgazer.service 2>&1
systemctl daemon-reload 2>&1
systemctl reset-failed 2>&1
' >> $TEMPPATH
echo 'echo "Removing virtual Python environment..."
rm -rf /etc/FlightGazer-pyvenv
echo -e "Removing FlightGazer directory ${FGDIR}..."
rm -rf ${FGDIR}
rm -f ${FGDIR}/../emulator_config.json 2>&1
sleep 2s
echo -e "${NC}\nDone."
exit 0' >> $TEMPPATH
chmod +x $TEMPPATH
echo -e "${GREEN}>>> Thanks for using FlightGazer!${NC}"
bash $TEMPPATH
exit 0
}