import os
"""Check the packaged native core and absence of private network defaults."""
import hashlib,json,sys,zipfile
from pathlib import Path

apk=Path(sys.argv[1])
root=Path(__file__).parent
repo=Path(sys.argv[2]) if len(sys.argv)>2 else root/'rustdesk'
jni=repo/'flutter/android/app/src/main/jniLibs/arm64-v8a/librustdesk.so'
profiles=Path(os.environ.get('RD_PROFILES_DIR', 'D:/RD/releases/windows/ssh'))
needles=set()
def collect(value):
    if not isinstance(value,dict):return
    for k,v in value.items():
        if isinstance(v,dict):collect(v)
        elif isinstance(v,str) and len(v)>=8 and k in {'host','relay','key','server','server_name','uuid','private_key','public_key','reality_public_key'}:
            needles.add(v)
for name in ('VPS1-network.json','VPS3-network.json'):
    collect(json.loads((profiles/name).read_text(encoding='utf-8-sig')))
with zipfile.ZipFile(apk) as z:
    names=z.namelist()
    core=z.read('lib/arm64-v8a/librustdesk.so')
    assert hashlib.sha256(core).digest()==hashlib.sha256(jni.read_bytes()).digest(),'Packaged native core differs from new JNI core'
    scanned=[]
    required=['lib/arm64-v8a/librustdesk.so','lib/arm64-v8a/libapp.so']
    if (jni.parent/'libxray.so').is_file():
        xray=z.read('lib/arm64-v8a/libxray.so')
        assert hashlib.sha256(xray).digest()==hashlib.sha256((jni.parent/'libxray.so').read_bytes()).digest(),'Packaged Xray differs'
        assert 'assets/flutter_assets/assets/xray-LICENSE.txt' in names,'Xray license missing'
        required.append('lib/arm64-v8a/libxray.so')
    for name in required:
        data=z.read(name)
        for private in needles:
            assert private.encode() not in data and private.encode('utf-16le') not in data,'Private network parameter embedded in '+name
        scanned.append(name)
    assert not any(n.endswith(('VPS1-network.json','VPS3-network.json','RustDesk2.toml')) for n in names),'Private profile file included'
    abis=sorted({n.split('/')[1] for n in names if n.startswith('lib/') and n.endswith('.so')})
print(json.dumps({'apk':apk.name,'sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),'new_native_core_matches':True,'abis':abis,'private_network_values_not_embedded':True,'scanned':scanned},indent=2))
