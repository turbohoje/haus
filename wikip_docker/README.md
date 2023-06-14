# Setup Instructions

for running a raspberry pi or similar as a ubiquiti dream machine

## Pi install

1. `apt-get update`
1. `apt-get upgrade`
1. allow ssh
1. `apt-get install vim`
1. enable swap for a rpi 3 as there is not enough ram to run the 64bit dream machine
    1. vim `/etc/dphys-swapfile` 
    1. `CONF_SWAPSIZE=2048`
    1. `sudo dphys-swapfile setup|swapoff|swapon`
1. `curl -sSL https://get.docker.com | sh`
1. `sudo usermod -aG docker $USER`
1. set the IP on the pi
