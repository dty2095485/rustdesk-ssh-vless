PID=$(echo 'Zww3.1415926' | sudo -S ss -ltnp 2>/dev/null | grep ':29999' | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)
if [ -n "$PID" ]; then echo 'Zww3.1415926' | sudo -S kill "$PID"; echo "killed source pid $PID"; else echo "no source found"; fi
sleep 1
echo 'Zww3.1415926' | sudo -S docker stop hbssh
echo 'Zww3.1415926' | sudo -S docker rm hbssh
echo 'Zww3.1415926' | sudo -S docker run -d --name hbssh --network host --restart unless-stopped -e SSH_LISTEN=0.0.0.0:2222 -e SSH_HBBS=127.0.0.1:22116 -e SSH_NAT=127.0.0.1:22115 -e SSH_HBBR=127.0.0.1:22117 hbssh:latest
echo '---RESTORE DONE---'
