echo 'Zww3.1415926' | sudo -S bash -c 'nohup python3 /tmp/source.py </dev/null >/tmp/source.log 2>&1 &'
sleep 1
echo 'Zww3.1415926' | sudo -S docker stop hbssh
echo 'Zww3.1415926' | sudo -S docker rm hbssh
echo 'Zww3.1415926' | sudo -S docker run -d --name hbssh --network host --restart unless-stopped -e SSH_LISTEN=0.0.0.0:2222 -e SSH_HBBS=127.0.0.1:22116 -e SSH_NAT=127.0.0.1:22115 -e SSH_HBBR=127.0.0.1:29999 hbssh:latest
echo '---SETUP DONE---'
