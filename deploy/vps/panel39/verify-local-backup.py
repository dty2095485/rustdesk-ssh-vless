import hashlib
from pathlib import Path
import tarfile

path = Path(r'<workspace>\backups\vps3\panel39-20261004T123658Z-bySBXD.tar.gz')
expected = '91f07281058ac3c2d52243b9e6aa5caf939f56d361066a1182943a9ff5a2048f'
with path.open('rb') as data:
    assert hashlib.file_digest(data, 'sha256').hexdigest() == expected
prefix = 'panel39-20261004T123658Z-bySBXD/'
with tarfile.open(path, 'r:gz') as archive:
    names = set(archive.getnames())
    for relative in ('old-image.tar', 'old-container.json', 'root/compose.yml',
                     'root/.env', 'root/x-ui-data/x-ui.db', 'root/data/db_v2.sqlite3',
                     'root/data/id_ed25519', 'root/internal-tls/privkey.pem'):
        assert prefix + relative in names, 'Required recovery file missing: ' + relative
    expected_image = archive.extractfile(prefix + 'old-image.sha256').read().decode().split()[0]
    with archive.extractfile(prefix + 'old-image.tar') as image:
        assert hashlib.file_digest(image, 'sha256').hexdigest() == expected_image
print('PASS archive SHA256, required recovery files, and embedded old-image SHA256')
