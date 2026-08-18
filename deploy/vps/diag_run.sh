#!/usr/bin/env bash
docker exec rustdesk_rrsc-rustdesk_rrsC-1 /bin/sh -c '
echo "--- ls run file ---"; ls -la /run/service/hbvless/run
echo "--- shebang ---"; head -1 /run/service/hbvless/run | od -c | head -2
echo "--- with-contev ---"; ls -la /command/with-contev 2>&1
echo "--- exec directly ---"; cd /run/service/hbvless && timeout 3 ./run; echo "run exit=$?"
echo "--- exec via sh ---"; timeout 3 /bin/sh /run/service/hbvless/run; echo "sh exit=$?"
echo "--- run hbvless directly ---"; timeout 3 /usr/bin/hbvless; echo "hbvless exit=$?"
'
