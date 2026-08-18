echo '=== HBBR ==='
echo 'Zww3.1415926' | sudo -S docker inspect hbbr --format '{{json .Config.Cmd}}
{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null
echo '=== HBBS ==='
echo 'Zww3.1415926' | sudo -S docker inspect hbbs --format '{{json .Config.Cmd}}
{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null
echo '=== HBBR mounts/net ==='
echo 'Zww3.1415926' | sudo -S docker inspect hbbr --format 'net={{.HostConfig.NetworkMode}} binds={{json .HostConfig.Binds}} restart={{.HostConfig.RestartPolicy.Name}}' 2>/dev/null
