"""Rename sample records and matching face labels while retaining numeric IDs."""
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
import numpy as np
from app.main import ROOT
from app.database import Database


def main():
    db = Database()
    backup = ROOT / 'data/backups' / ('names_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True)
    fields = {'users': ('username', 'fullName'), 'students': ('studentCode', 'fullName'),
              'rooms': ('roomCode', 'name'), 'classes': ('classCode', 'name'),
              'learning_sessions': ('subjectCode', 'subjectName', 'teacherName')}
    records = {table: db.all(f'SELECT id,{",".join(columns)} FROM {table}') for table, columns in fields.items()}
    (backup / 'records.json').write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
    mapping = {r['studentCode']: f"SV{r['id']:03d}" for r in records['students'] if 'demo' in r['studentCode'].lower()}
    gallery = ROOT / 'data/embeddings/gallery.npz'
    if gallery.exists():
        shutil.copy2(gallery, backup / 'gallery.npz')
    moved = []
    try:
        with db.transaction():
            for table, rows in records.items():
                columns = fields[table]
                for row in rows:
                    updated = dict(row)
                    for column in columns:
                        value = row[column]
                        if 'demo' not in value.lower():
                            continue
                        if column == 'username':
                            value = {'admin_demo': 'admin01', 'sinhvien_demo': 'sinhvien01', 'demo_teacher': 'giaovien01'}.get(value, re.sub('demo_?', '', value, flags=re.I))
                        elif column == 'studentCode':
                            value = mapping[value]
                        elif column == 'roomCode':
                            value = {'DEMO-LAB01': 'LAB02'}.get(value, value.replace('DEMO-', ''))
                        elif column == 'classCode':
                            value = value.replace('DEMO-', '')
                        elif column == 'subjectCode':
                            value = {'DEMO-MON1': 'PY101', 'DEMO-MON2': 'CSDL101', 'DEMO-MON3': 'AI101', 'DEMO-STUDENT-LIVE': 'FACE101', 'DEMO-STUDENT-NEXT': 'PY101', 'DEMO-STUDENT-PAST': 'CSDL101', 'DEMO-PY': 'PY101', 'DEMO-CSDL': 'CSDL101', 'DEMO-AI': 'AI101'}.get(value, value.replace('DEMO-', ''))
                        elif column == 'fullName' and table == 'students':
                            value = {12: 'Nguyễn Văn Minh', 14: 'Nguyễn Văn Hùng', 15: 'Sinh viên'}.get(row['id'], re.sub(r'\s*demo\d*', '', value, flags=re.I).strip())
                        elif column == 'fullName' and row['id'] == 17:
                            value = 'Nguyễn Văn Hùng'
                        else:
                            value = re.sub(r'\s*demo\d*', '', value, flags=re.I).strip()
                        updated[column] = value
                    if updated != row:
                        for key in columns:
                            if key.endswith('Code') or key == 'username':
                                if table != 'learning_sessions' and db.all(f'SELECT id FROM {table} WHERE {key}=? AND id<>?', [updated[key], row['id']]):
                                    raise ValueError(f'Name collision in {table}.{key}')
                        db.execute(f'UPDATE {table} SET '+','.join(key+'=?' for key in columns)+' WHERE id=?', [*[updated[key] for key in columns], row['id']])
            for old, new in mapping.items():
                source, destination = ROOT / 'data/registration' / old, ROOT / 'data/registration' / new
                if source.exists():
                    if destination.exists():
                        raise ValueError('Registration folder already exists')
                    source.rename(destination)
                    moved.append((source, destination))
            if gallery.exists():
                with np.load(gallery, allow_pickle=False) as data:
                    arrays = {key: data[key].copy() for key in data.files}
                arrays['ids'] = np.asarray([mapping.get(str(value), str(value)) for value in arrays['ids']])
                temporary = gallery.with_suffix('.rename.npz')
                np.savez_compressed(temporary, **arrays)
                temporary.replace(gallery)
            for table, columns in fields.items():
                for column in columns:
                    assert not db.all(f'SELECT id FROM {table} WHERE LOWER({column}) LIKE ?', ['%demo%'])
        print('Renamed visible records and face labels. Backup:', backup.name)
    except Exception:
        for source, destination in reversed(moved):
            destination.rename(source)
        if (backup / 'gallery.npz').exists():
            shutil.copy2(backup / 'gallery.npz', gallery)
        raise
    finally:
        db.close()


if __name__ == '__main__':
    main()
