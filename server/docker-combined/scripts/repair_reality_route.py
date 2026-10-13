#!/usr/bin/env python3
"""Repair the dedicated RustDesk route without changing client credentials."""
import argparse
import json
import sqlite3

parser = argparse.ArgumentParser()
parser.add_argument('--db', required=True)
parser.add_argument('--backup', required=True)
args = parser.parse_args()
with sqlite3.connect(args.db) as db:
    with sqlite3.connect(args.backup) as backup:
        if hasattr(db, 'backup'):
            db.backup(backup)
        else:
            backup.executescript('\n'.join(db.iterdump()))
    row = db.execute("SELECT value FROM settings WHERE key='xrayTemplateConfig'").fetchone()
    if row is None:
        raise RuntimeError('Xray template missing')
    template = json.loads(row[0])
    outbounds = template.setdefault('outbounds', [])
    outbounds[:] = [item for item in outbounds if item.get('tag') != 'rustdesk-loopback']
    outbounds.append({'tag': 'rustdesk-loopback', 'protocol': 'freedom', 'settings': {
        'finalRules': [{'action': 'allow', 'ip': ['127.0.0.1'], 'port': '22115-22117'}, {'action': 'block'}]}})
    changed = 0
    for rule in template['routing']['rules']:
        if rule.get('user') == ['rustdesk-client'] and rule.get('port') == '22115-22117' and rule.get('ip') == ['127.0.0.1']:
            rule['outboundTag'] = 'rustdesk-loopback'
            changed += 1
    if changed != 1:
        raise RuntimeError(f'Expected one restricted RustDesk route, found {changed}')
    db.execute("UPDATE settings SET value=? WHERE key='xrayTemplateConfig'", (json.dumps(template, separators=(',', ':')),))
print('RustDesk loopback outbound repaired; credential and other proxy routes preserved')
