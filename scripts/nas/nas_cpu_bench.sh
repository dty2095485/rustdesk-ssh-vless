echo '=== CPU model ==='
grep -iE 'model name|hardware|processor|^model' /proc/cpuinfo | head -8
echo '=== zstd benchmark (high-entropy, like video) ==='
dd if=/dev/urandom of=/tmp/bench.bin bs=1M count=64 2>/dev/null
ls -l /tmp/bench.bin | awk '{print $5" bytes"}'
echo '--- zstd level 3 ---'
time zstd -3 -c /tmp/bench.bin > /dev/null
echo '--- zstd level 1 ---'
time zstd -1 -c /tmp/bench.bin > /dev/null
rm -f /tmp/bench.bin
