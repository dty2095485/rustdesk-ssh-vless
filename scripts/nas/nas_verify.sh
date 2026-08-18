echo 'Zww3.1415926' | sudo -S docker ps -a --filter name=hbssh 2>/dev/null
echo '---ENV---'
echo 'Zww3.1415926' | sudo -S docker exec hbssh env 2>/dev/null | grep SSH_
echo '---LISTEN---'
echo 'Zww3.1415926' | sudo -S ss -ltnp 2>/dev/null | grep -E ':29999|:2222|:22117'
