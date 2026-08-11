#!/bin/bash
# https://stackoverflow.com/questions/9449417/how-do-i-assign-the-output-of-a-command-into-an-array

echo " "
echo " "
echo " "
echo " "
echo "  PiRowFlo for Waterrower"
echo "                                                    +-+"
echo "                            XX+-----------------+"
echo "               +-------+  XXXX    |----|        | |"
echo "                +-----+  XXX +----------------+ | |"
echo "                |     |XXX    |XXXXXXXXXXXXXXXX| | |"
echo "+--------------X-----X----------+XXX+------------------------+-+"
echo "|                                                            |"
echo "+--------------------------------------------------------------+"
echo " "
echo " This script will install all the needed packages and modules "
echo " to make the Waterrower Ant and BLE Raspberry Pi Module working"
echo " "

echo " "
echo "-------------------------------------------------------------"
echo "updates the list of latest updates available for the packages"
echo "-------------------------------------------------------------"
echo " "
sudo apt-get update

echo " "
echo "----------------------------------------------"
echo "installed needed packages for python & system "
echo "----------------------------------------------"

sudo apt install libgirepository1.0-dev libcairo2-dev python3-dev -y
sudo apt-get install -y python3 python3-gi python3-dev python3-gi-cairo gir1.2-gtk-3.0 python3-pip 
sudo apt-get install -y libopenblas-dev libglib2.0-dev libgirepository-2.0-dev libcairo2-dev zlib1g-dev 
sudo apt-get install -y libfreetype6-dev liblcms2-dev libopenjp2-7 libtiff6
sudo apt-get install -y build-essential libdbus-glib-1-dev 
sudo apt-get install -y git virtualenv
# NEU: Systemweite Python-Schnittstellen und Bluetooth-Treiber direkt absichern
sudo apt-get install -y python3-dbus python3-serial python3-usb bluez bluez-tools firmware-brcm80211

echo " "


echo " "
echo "----------------------------------------------"
echo "install needed python3 modules for the project         "
echo "----------------------------------------------"
echo " "
python3 -m venv pirowflo
source pirowflo/bin/activate

pip3 install pyserial
pip3 install PyGObject
pip3 install dbus-python
# pip3 install numpy
pip3 install pyusb
pip3 install gatt 
pip3 install supervisor 
pip3 install luma.oled
# pip3 install spidev

# Deaktiviert, da direkt oben über pip installiert:
# sudo pip3 install -r requirements.txt

echo " "
echo "-------------------------------------------------------"
echo "check for Ant+ dongle in order to set udev rules       "
echo "Load the Ant+ dongle with FTDI driver                  "
echo "and ensure that the user pi has access to              "
echo "-------------------------------------------------------"
echo " "

IFS=$'\n'
arrayusb=($(lsusb | cut -d " " -f 6 | cut -d ":" -f 2))

for i in "${arrayusb[@]}"
do
  if [ "$i" == "1008" ] || [ "$i" == "1009" ] || [ "$i" == "1004" ]; then
    echo "Ant dongle found with ID: $i"
    # FIX: Hier wurde $i statt der festen 1008 genutzt, damit es für 1008 UND 1009 korrekt greift
    echo 'ACTION=="add", ATTRS{idVendor}=="0fcf", ATTRS{idProduct}=="'$i'", RUN+="/sbin/modprobe ftdi_sio" RUN+="/bin/sh -c '"'echo 0fcf '$i' > /sys/bus/usb-serial/drivers/ftdi_sio/new_id'\""'' > /etc/udev/rules.d/99-garmin.rules
    echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="0fcf", ATTR{idProduct}=="'$i'", MODE="666"' >> /etc/udev/rules.d/99-garmin.rules
    echo "udev rule written to /etc/udev/rules.d/99-garmin.rules"
    break
  else
    echo "No Ant stick found in this iteration..."
  fi
done
unset IFS

echo "----------------------------------------------"
echo " add user to the group bluetooth and dialout  "
echo "----------------------------------------------"

sudo usermod -a -G bluetooth pi
sudo usermod -a -G dialout pi

echo " "
echo "-----------------------------------------------"
echo " Change bluetooth name and unblock adapter     "
echo "-----------------------------------------------"
echo " "

echo "PRETTY_HOSTNAME=PiRowFlo" | sudo tee -a /etc/machine-info > /dev/null

# NEU: Software-Sperre (Soft-Block) von Bluetooth aufheben und Dienst aktivieren
sudo rfkill unblock all
sudo systemctl enable --now bluetooth

echo " "
echo "------------------------------------------------------"
echo " configuring web interface on http://${HOSTNAME}:9001 "
echo "------------------------------------------------------"
echo " "

export repo_dir=$(cd $(dirname $0) > /dev/null 2>&1; pwd -P)
export python3_path=$(which python3)
export supervisord_path=$(which supervisord)
export supervisorctl_path=$(which supervisorctl)

cp services/supervisord.conf.orig services/supervisord.conf
sudo chown root:root services/supervisord.conf.orig
sudo chmod 655 services/supervisord.conf.orig
sed -i 's@#PYTHON3#@'"$python3_path"'@g' services/supervisord.conf
sed -i 's@#REPO_DIR#@'"$repo_dir"'@g' services/supervisord.conf

sed -i 's@#REPO_DIR#@'"$repo_dir"'@g' services/supervisord.service
sed -i 's@#SUPERVISORD_PATH#@'"$supervisord_path"'@g' services/supervisord.service
sed -i 's@#SUPERVISORCTL_PATH#@'"$supervisorctl_path"'@g' services/supervisord.service
sudo cp services/supervisord.service /etc/systemd/system/
sudo chown root:root /etc/systemd/system/supervisord.service
sudo chmod 655 /etc/systemd/system/supervisord.service
sudo systemctl enable supervisord
sudo rm -f /tmp/pirowflo*
sudo rm -f /tmp/supervisord.log

echo " "
echo "------------------------------------------------------------"
echo " Update bluetooth settings according to Apple specifications"
echo "------------------------------------------------------------"
echo " "

sed -i 's@#REPO_DIR#@'"$repo_dir"'@g' services/update-bt-cfg.service
sudo cp services/update-bt-cfg.service /etc/systemd/system/
sudo chown root:root /etc/systemd/system/update-bt-cfg.service
sudo chmod 655 /etc/systemd/system/update-bt-cfg.service
sudo systemctl enable update-bt-cfg


echo " "
echo "------------------------------------------------------------"
echo " setup screen setting to start up at boot                    "
echo "------------------------------------------------------------"
echo " "

sudo sed -i 's/#dtparam=spi=on/dtparam=spi=on/g' /boot/firmware/config.txt
sudo sed -i 's@#REPO_DIR#@'"$repo_dir"'@g' src/adapters/screen/settings.ini

sed -i 's@#PYTHON3#@'"$python3_path"'@g' services/screen.service
sed -i 's@#REPO_DIR#@'"$repo_dir"'@g' services/screen.service
sudo cp services/screen.service /etc/systemd/system/
sudo chown root:root /etc/systemd/system/screen.service
sudo chmod 655 /etc/systemd/system/screen.service
sudo systemctl enable screen

echo "----------------------------------------------"
echo " Add absolute path to the logging.conf file    "
echo "----------------------------------------------"

sed -i 's@#REPO_DIR#@'"$repo_dir"'@g' src/logging.conf

echo " "
echo "----------------------------------------------"
echo " installation done ! rebooting in 3, 2, 1 "
echo "----------------------------------------------"
sleep 3
sudo reboot
echo " "
exit 0
