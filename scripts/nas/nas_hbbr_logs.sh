echo 'Zww3.1415926' | sudo -S docker logs hbbr 2>&1 | grep -iE 'relay|paired|request|key|listen' | tail -40
