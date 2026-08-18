echo '=== ENV ==='
echo 'Zww3.1415926' | sudo -S docker inspect hbbr --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep -E 'LIMIT|VLESS'
echo '=== CMD ==='
echo 'Zww3.1415926' | sudo -S docker inspect hbbr --format '{{json .Config.Cmd}}' 2>/dev/null
echo '=== LOGS (bandwidth) ==='
echo 'Zww3.1415926' | sudo -S docker logs hbbr 2>&1 | grep -iE 'LIMIT_SPEED|SINGLE_BANDWIDTH|TOTAL_BANDWIDTH|bandwidth|relay'
