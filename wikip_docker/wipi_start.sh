#https://hub.docker.com/r/linuxserver/unifi-controller
#upgrade to https://github.com/linuxserver/docker-unifi-network-application?tab=readme-ov-file
#needs mongo et al

docker run -d \
  --name=unifi-controller \
  -e PUID=1000 \
  -e PGID=1000 \
  -p 3478:3478/udp \
  -p 10001:10001/udp \
  -p 8080:8080 \
  -p 8443:8443 \
  -p 1900:1900/udp `#optional` \
  -p 8843:8843 `#optional` \
  -p 8880:8880 `#optional` \
  -p 6789:6789 `#optional` \
  -p 5514:5514/udp `#optional` \
  -v /mnt/wipi2022:/config \
  --restart unless-stopped \
  lscr.io/linuxserver/unifi-controller:latest
#ghcr.io/linuxserver/unifi-controller:7.1.66-ls151

#  -v /home/turbohoje/run:/etc/services.d/unifi/run \
