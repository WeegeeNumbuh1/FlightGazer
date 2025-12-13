#!/bin/bash
# Script to install FlightGazer's web interface.
# This is bundled with the FlightGazer repository
# and inherits its version number.
# Last updated: v.9.7.1
# by: WeegeeNumbuh1

BASEDIR=$(cd `dirname -- $0` && pwd)
TEMPPATH=/tmp/FlightGazer-tmp
VENVPATH=/etc/FlightGazer-pyvenv
GREEN='\033[0;32m'
ORANGE='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
FADE='\033[2m'
OWNER_OF_FGDIR='nobody'
GROUP_OF_FGDIR='nogroup'

echo -ne "\033]0;FlightGazer Web Interface Installer\007" # set window title
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
echo -e "\n${ORANGE}>>> FlightGazer Web Interface installer script started.${NC}"
if [ `id -u` -ne 0 ]; then
	>&2 echo -e "${RED}>>> ERROR: This script must be run as root.${NC}"
	sleep 1s
	exit 1
fi
if [ ! -f "${BASEDIR}/FlightGazer.py" ]; then
	echo -e "\n${NC}${RED}>>> ERROR: Cannot find FlightGazer.py. This installer script must be in the same directory as FlightGazer.py!${NC}"
	sleep 2s
	exit 1
fi

if [ ! -d "${VENVPATH}" ]; then
	echo -e "\n${NC}${RED}>>> ERROR: Cannot find FlightGazer virtual environment! Has FlightGazer been installed before?${NC}"
	sleep 2s
	exit 1
fi

systemctl list-unit-files flightgazer.service &>/dev/null
if [ $? -ne 0 ]; then
	>&2 echo -e "${NC}${RED}>>> ERROR: Could not find the FlightGazer service on the system. This is a requirement for the web interface.${NC}"
	exit 1
fi

wget -q --timeout=10 --spider http://github.com
if [ $? -ne 0 ]; then
	>&2 echo -e "${NC}${RED}>>> ERROR: Failed to connect to internet. Try again when there is internet connectivity.${NC}"
	exit 1
fi

venv_install() {
	VENVCMD="${VENVPATH}/bin/pip3"
	echo -e "${FADE}> Flask..."
	"${VENVCMD}" install --upgrade Flask >/dev/null
	echo "Done."
	echo -e "${FADE}> gunicorn..."
	"${VENVCMD}" install --upgrade gunicorn >/dev/null
	echo -e "Done.${NC}"
}

systemctl list-unit-files flightgazer-webapp.service >/dev/null
if [ $? -ne 0 ] && [ ! -d "${BASEDIR}/web-app" ]; then
	echo "The FlightGazer web interface is not installed."
	echo ""
	while read -t 30 -p "Would you like to continue the install? [yY|nN]: " do_it; do
		case "$do_it" in
			"y" | "Y" | "yes" | "Yes" | "YES")
				break
				;;
			"n" | "N" | "no" | "No" | "NO")
				echo "> Install cancelled. No changes have been made."
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
else
	echo -e "${GREEN}>>> The web interface is already installed!${NC}"
	echo "Checking for updates..."
	if [ -f "${BASEDIR}/web-app/version-webapp" ]; then
		VER_STR=$(head -c 12 "${BASEDIR}/web-app/version-webapp")
		echo -e "> Currently installed version:        ${VER_STR}"
	else
		VER_STR=""
		echo -e "> ${ORANGE}Could not determine installed version!${NC}"
	fi
	LATEST_VER="$(wget -q -O - "https://raw.githubusercontent.com/WeegeeNumbuh1/FlightGazer-webapp/refs/heads/master/version-webapp")"
	if [ -z "$LATEST_VER" ]; then
		echo -e "> ${ORANGE}Could not determine latest version!${NC}"
	else
		echo -e "> Latest version available on GitHub: ${LATEST_VER}"
	fi
	if [ "$VER_STR" == "$LATEST_VER" ]; then
		echo "> The currently installed version is the same as what is available online."
	else
		echo "> An update is available!"
	fi
	echo ""
	while read -t 30 -p "Would you like to update? [yY|nN]: " do_it; do
		case "$do_it" in
			"y" | "Y" | "yes" | "Yes" | "YES")
				break
				;;
			"n" | "N" | "no" | "No" | "NO")
				echo "> Update cancelled. No changes have been made."
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
	# fire up the bundled updater
	if [ -f "${BASEDIR}/web-app/update-webapp.sh" ]; then
		echo "Checking venv dependencies first (please wait)..."
		systemctl stop flightgazer-webapp >/dev/null 2>&1
		echo -e "${FADE}The web interface has been shut down."
		venv_install
		bash "${BASEDIR}/web-app/update-webapp.sh"
		if [ $? -ne 0 ]; then
			>&2 echo -e "${NC}${RED}>>> ERROR: Update failed.${NC}"
			exit 1
		else
			echo -e "${NC}${GREEN}>>> Success.${NC}"
			exit 0
		fi
	else
		>&2 echo -e "${NC}${RED}>>> ERROR: Update script is missing! Cannot update.${NC}"
		exit 1
	fi
fi
# continue the install
rm -rf "$TEMPPATH" >/dev/null 2>&1 # make sure the temp directory doesn't exist before we start
echo -e "${GREEN}>>> Downloading latest version...${NC}${FADE}"
git clone --depth=1 https://github.com/WeegeeNumbuh1/FlightGazer-webapp "$TEMPPATH"
if [ $? -ne 0 ]; then
	rm -rf "$TEMPPATH" >/dev/null 2>&1
	echo -e "${RED}>>> ERROR: Failed to download from GitHub. Installer cannot continue.${NC}"
	exit 1
fi
rm -rf "${TEMPPATH}/.git" >/dev/null 2>&1
find "${TEMPPATH}" -type f -name '.*' -exec rm '{}' \; >/dev/null 2>&1
if [ -f "${TEMPPATH}/version-webapp" ]; then
	VER_STR=$(head -c 12 "${TEMPPATH}/version-webapp")
	echo -e "${NC}> Downloaded FlightGazer-webapp version: ${VER_STR}"
fi

read -r OWNER_OF_FGDIR GROUP_OF_FGDIR <<<$(stat -c "%U %G" "${BASEDIR}")
chown -Rf ${OWNER_OF_FGDIR}:${GROUP_OF_FGDIR} "$TEMPPATH" # need to do this as we are running as root
echo -e "${FADE}Copying ${TEMPPATH} to ${BASEDIR}/web-app..."
cp -afT "$TEMPPATH" "${BASEDIR}/web-app"
rm -rf "$TEMPPATH" >/dev/null 2>&1 # clean up after ourselves
echo -e "Done.${NC}"

echo -e "${GREEN}>>> Installing dependencies in existing FlightGazer venv...${NC}"
venv_install

echo -e "${GREEN}>>> Checking networking capabilities...${NC}"
command -v netstat >/dev/null && command -v ifconfig >/dev/null
if [ $? -eq 1 ]; then
	apt-cache --generate pkgnames | \
	grep --line-regexp --fixed-strings \
	-e netstat \
	-e ifconfig \
	| xargs apt-get install -y >/dev/null
fi
# https://stackoverflow.com/a/33550399
NET_IF=`netstat -rn | awk '/^0.0.0.0/ {thif=substr($0,74,10); print thif;} /^default.*UG/ {thif=substr($0,65,10); print thif;}'`
NET_IP=`ifconfig ${NET_IF} | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1'`

# Programatically install entries for nginx, Apache, or lighttpd that redirects
# port 9898 to the directory '/flightgazer'
if command -v nginx >/dev/null 2>&1; then
	echo -e "> Detected nginx. Configuring reverse proxy for FlightGazer webapp...${FADE}"
	NGINX_CONF_PATH="/etc/nginx/sites-available/flightgazer-webapp"
	cat <<- 'EOF' > $NGINX_CONF_PATH
server {
	listen 80;
	server_name _;
	location /flightgazer/ {
		proxy_pass http://127.0.0.1:9898;
		proxy_set_header Host $host;
		proxy_set_header X-Real-IP $remote_addr;
		proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
		proxy_set_header X-Forwarded-Proto $scheme;
	}
}
EOF
	ln -sf $NGINX_CONF_PATH /etc/nginx/sites-enabled/flightgazer-webapp
	nginx -t && systemctl reload nginx
	echo -e "${NC}> nginx configured. Access via http://$NET_IP/flightgazer"
	echo -e "  or via http://$HOSTNAME.local/flightgazer"
elif command -v apache2 >/dev/null 2>&1; then
	echo -e "> Detected Apache. Configuring reverse proxy for FlightGazer webapp...${FADE}"
	APACHE_CONF_PATH="/etc/apache2/sites-available/flightgazer-webapp.conf"
	cat <<- 'EOF' > $APACHE_CONF_PATH
<VirtualHost *:80>
	ServerName localhost
	ProxyPreserveHost On
	ProxyPass /flightgazer/ http://127.0.0.1:9898/
	ProxyPassReverse /flightgazer/ http://127.0.0.1:9898/
</VirtualHost>
EOF
	a2enmod proxy proxy_http
	a2ensite flightgazer-webapp
	systemctl reload apache2
	echo -e "${NC}> Apache configured. Access via http://$NET_IP/flightgazer"
	echo -e "  or via http://$HOSTNAME.local/flightgazer"
elif command -v lighttpd >/dev/null 2>&1; then
	echo -e "> Detected Lighttpd. Configuring reverse proxy for FlightGazer webapp...${FADE}"
	LIGHTTPD_CONF_PATH="/etc/lighttpd/conf-available/98-flightgazer-webapp.conf"
	cat <<- 'EOF' > $LIGHTTPD_CONF_PATH
server.modules += ( "mod_proxy" )
#url.rewrite-once = (
#    "^/flightgazer/(.*)" => "/$1",
#    "^/flightgazer$" => "/"
#)
$HTTP["url"] =~ "^/flightgazer($|/)" {
    proxy.server = (
        "/flightgazer" => ((
            "host" => "127.0.0.1",
            "port" => 9898
        ))
    )
}
EOF
	lighttpd-enable-mod proxy
	lighttpd-enable-mod flightgazer-webapp
	systemctl restart lighttpd
	echo -e "${NC}> Lighttpd configured. Access via http://$NET_IP/flightgazer"
	echo -e "  or via http://$HOSTNAME.local/flightgazer"
else
	echo -e "${ORANGE}>>> Neither nginx, Apache, nor Lighttpd detected.${NC}"
	echo "Please configure your web server manually to proxy '/flightgazer' to 127.0.0.1:9898."
	echo "You can still access the web interface at:"
	echo -e "http://$NET_IP:9898/flightgazer or"
	echo -e "http://$HOSTNAME.local:9898/flightgazer"
fi

echo -e "${GREEN}>>> Creating systemd service...${NC}${FADE}"
if [ ! -f "/etc/systemd/system/flightgazer-webapp.service" ]; then
	cat <<- EOF > /etc/systemd/system/flightgazer-webapp.service
	[Unit]
	Description=FlightGazer Web Interface
	Documentation="https://github.com/WeegeeNumbuh1/FlightGazer-webapp"
	StartLimitIntervalSec=30

	[Service]
	# yeah we use root for this, but this web app isn't something you expose to the rest of the internet anyway (if you do, then gg)
	User=root
	ExecStart="${VENVPATH}/bin/gunicorn" -w 1 -b 0.0.0.0:9898 --worker-connections 3 --chdir "${BASEDIR}/web-app/" "FG-webapp:app"
	Type=simple
	# Note: the below is required to handle the case when the web interface updates itself and needs to restart the service.
	# Without this, this service will fail to restart as the process that sent the restart command is killed once the command is initiated.
	KillMode=process
	TimeoutStartSec=10
	TimeoutStopSec=2
	Restart=on-failure
	StartLimitBurst=2
	RestartSec=10s

	[Install]
	WantedBy=multi-user.target
	EOF

	systemctl daemon-reload 2>&1
	systemctl enable flightgazer-webapp.service 2>&1
	echo "Starting service..."
	systemctl start flightgazer-webapp.service
	echo "Service status:"
	systemctl status flightgazer-webapp.service --no-pager
	echo ""
	echo -e "${NC}> Service installed. The FlightGazer web interface will run at boot via systemd.\n"
	echo -e "${RED}> Do not move the FlightGazer directory (${ORANGE}${BASEDIR}${RED})!"
	echo -e "  Doing so will cause the service to fail!${NC}"
	sleep 5s
else
echo "> Service already exists."
fi

echo -e "${GREEN}>>> Install complete.${NC}"
exit 0