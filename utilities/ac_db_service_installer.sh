#!/bin/bash
# Aircraft database maintenance service installer for FlightGazer.
BASEDIR=$(cd `dirname -- $0` && pwd)
VENVPATH=/etc/FlightGazer-pyvenv
DB_DOWNLOADER="${BASEDIR}/aircraft_db_fetcher.py"
service_heredoc() {
	cat <<- EOF > /etc/systemd/system/flightgazer-acdb-updater.service
	[Unit]
	Description=FlightGazer Aircraft Database Updater
	Documentation="https://github.com/WeegeeNumbuh1/FlightGazer"

	[Service]
	User=root
	Type=oneshot
	Nice=19
	CPUSchedulingPolicy=idle
	IOSchedulingClass=idle
	ExecStart="${VENVPATH}/bin/python3" -u "$DB_DOWNLOADER"
EOF
}
timer_heredoc() {
	cat <<- EOF > /etc/systemd/system/flightgazer-acdb-updater.timer
	[Unit]
	Description=Updates the FlightGazer aircraft database at 2 AM every Monday
	Documentation="https://github.com/WeegeeNumbuh1/FlightGazer"
	After=flightgazer.service

	[Timer]
	OnCalendar=Mon *-*-* 02:00:00
	Persistent=false
	RandomizedDelaySec=3600

	[Install]
	WantedBy=timers.target
	WantedBy=flightgazer.service
EOF
}
if [ `id -u` -ne 0 ]; then
	>&2 echo ">>> ERROR: This script must be run as root."
	sleep 1s
	exit 1
fi
echo "Installing aircraft database maintenance service..."
service_heredoc
timer_heredoc
systemctl daemon-reload
systemctl enable flightgazer-acdb-updater.timer
systemctl start flightgazer-acdb-updater.timer
echo "Install complete."