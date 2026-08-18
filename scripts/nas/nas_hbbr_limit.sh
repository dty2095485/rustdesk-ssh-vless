echo 'Zww3.1415926' | sudo -S docker stop hbbr
echo 'Zww3.1415926' | sudo -S docker rm hbbr
echo 'Zww3.1415926' | sudo -S docker run -d --name hbbr --network host --restart unless-stopped -e VLESS_HBBR_INTERNAL=127.0.0.1:22117 -e LIMIT_SPEED=320 -e SINGLE_BANDWIDTH=1280 rustdesk-server:latest /usr/bin/hbbr -k '8N6hDJzbAj2XSIr0UyabPmHbY0tBnvAy3huqIs2HWS0XmxYEGZBrUHbse64S5GK3nZ9ZDZyzkjeVkFgkuIPwpQ='
echo '---HBBR RECREATED---'
