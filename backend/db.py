"""Versioned SQLite migrations and deterministic catalog import for a new database."""

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from .seed import CATEGORIES, PRODUCTS

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get('MAY_DB_PATH', ROOT / 'data' / 'may.sqlite3'))


def new_id() -> str:
    return str(uuid4())


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=10000')
    try:
        with db:
            yield db
    finally:
        db.close()


def password_hash(password: str, salt: str) -> str:
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def initialize() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connection() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        for migration in sorted((ROOT / 'migrations').glob('*.sql')):
            if db.execute('SELECT 1 FROM schema_migrations WHERE version=?', (migration.name,)).fetchone():
                continue
            script = "BEGIN IMMEDIATE;\n" + migration.read_text() + f"\nINSERT INTO schema_migrations(version) VALUES ('{migration.name}');\nCOMMIT;"
            db.executescript(script)
        db.executemany('INSERT OR IGNORE INTO categories VALUES (?,?,?)', CATEGORIES)
        for p in PRODUCTS:
            if db.execute('SELECT 1 FROM products WHERE id=?', (p['id'],)).fetchone():
                continue
            db.execute('''INSERT INTO products (id,name,brand,category,price,original_price,image,rating,sold,try_on,tag,specs,source_url,collected_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (p['id'],p['name'],p['brand'],p['category'],p['price'],p['original_price'],p['image'],p['rating'],p['sold'],p['try_on'],p['tag'],json.dumps(p['specs'],ensure_ascii=False),p['source_url'],p['collected_at']))
            db.execute('INSERT INTO product_categories VALUES (?,?)', (p['id'],p['category']))
            image_path = ROOT / 'frontend' / 'assets' / p['image']
            media_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
            db.execute('INSERT INTO media_assets (id,product_id,uri,media_hash) VALUES (?,?,?,?)', (new_id(),p['id'],p['image'],media_hash))
            for index,color in enumerate(p['colors']):
                for size in p['sizes']:
                    variant_id = f"{p['id']}-{index}-{size}"
                    db.execute('INSERT INTO variants (id,product_id,sku,color,size,price) VALUES (?,?,?,?,?,?)', (variant_id,p['id'],variant_id,color,size,p['price']))
                    db.execute('INSERT INTO inventory_positions (id,variant_id,location_id,on_hand) VALUES (?,?,?,?)', (new_id(),variant_id,'main',25 if index == 0 else 12))
        db.executemany('INSERT OR IGNORE INTO vouchers (code,title,kind,value,minimum,maximum,usage_limit,expires_at) VALUES (?,?,?,?,?,?,?,?)', [
            ('HELLOMAY','Chào bạn mới · Giảm 10%','percent',10,299000,100000,1000,'2099-12-31'),
            ('MAY50','Giảm 50.000đ','fixed',50000,499000,50000,500,'2099-12-31'),
            ('FREESHIP','Miễn phí vận chuyển','shipping',30000,299000,30000,1000,'2099-12-31'),
        ])
        # Demo accounts are explicit opt-in, never provisioned in a production database.
        if os.environ.get('MAY_DEMO_MODE') == '1':
            for role in ['merchant','support','operator']:
                salt = os.urandom(16).hex()
                db.execute('INSERT OR IGNORE INTO customers (id,full_name,email,salt,password_hash,role) VALUES (?,?,?,?,?,?)',
                           (new_id(),role.title(),f'{role}@may.local',salt,password_hash('MayDemo2026!',salt),role))
