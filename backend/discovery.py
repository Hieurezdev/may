"""Hybrid retrieval with separate text and visual services and live catalog filtering."""

import base64
import binascii
import hashlib
import io
import json
import math
import re
import sqlite3
import unicodedata
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from . import recommendations
from .auth import Operator
from .config import setting
from .db import ROOT, connection, new_id
from .dtos import EmbeddingResponse, IndexInput, SearchInput
from .inventory import audit
from .recommendations import eligible_ids

router = APIRouter(tags=['Search'])
router.include_router(recommendations.router)


def normalize(text: str) -> str:
    plain = ''.join(c for c in unicodedata.normalize('NFD',text.lower().replace('đ','d')) if unicodedata.category(c)!='Mn')
    return re.sub(r'[^a-z0-9\s-]',' ',plain)


def source_text(row: sqlite3.Row) -> str:
    return f"{row['name']} {row['brand']} {row['category']} {row['specs']} version:{row['source_version']}"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def validate_image(encoded: str) -> bytes:
    try:
        image = base64.b64decode(encoded,validate=True)
    except (ValueError,binascii.Error) as exc:
        raise HTTPException(422,'Ảnh phải dùng base64 hợp lệ.') from exc
    if len(image)>5*1024*1024:
        raise HTTPException(413,'Ảnh tối đa 5 MB.')
    try:
        with Image.open(io.BytesIO(image)) as picture:
            if picture.format not in {'JPEG','PNG','WEBP'} or picture.width*picture.height>20000000:
                raise HTTPException(422,'Chỉ nhận JPEG, PNG, WebP tối đa 20 megapixel.')
            picture.verify()
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as exc:
        raise HTTPException(422,'Không đọc được ảnh tải lên.') from exc
    return image


async def embed_text(text: str) -> EmbeddingResponse:
    endpoint = setting('TEXT_ENCODER_URL')
    revision = setting('TEXT_ENCODER_REVISION')
    if not endpoint or not revision:
        raise HTTPException(503,'Chưa cấu hình dịch vụ BGE-M3 cho văn bản.')
    return await encoder(endpoint+'/embed-text',{'text':text,'model':'BAAI/bge-m3'},revision)


async def embed_image(image: bytes) -> EmbeddingResponse:
    endpoint = setting('VISUAL_ENCODER_URL')
    revision = setting('VISUAL_ENCODER_REVISION')
    if not endpoint or not revision:
        raise HTTPException(503,'Chưa cấu hình visual encoder riêng cho tìm ảnh.')
    return await encoder(endpoint+'/embed-image',{'image_base64':base64.b64encode(image).decode()},revision)


async def encoder(url: str, payload: dict[str,str], revision: str) -> EmbeddingResponse:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5,connect=2)) as client:
            response = await client.post(url,json=payload)
    except httpx.TimeoutException as exc:
        raise HTTPException(504,'Encoder phản hồi quá hạn.') from exc
    except httpx.RequestError as exc:
        raise HTTPException(503,'Không kết nối được encoder đã cấu hình.') from exc
    if response.status_code>=500:
        raise HTTPException(503,'Encoder tạm thời không khả dụng.')
    if not response.is_success:
        raise HTTPException(502,f'Encoder từ chối yêu cầu (HTTP {response.status_code}).')
    try:
        result = EmbeddingResponse.model_validate_json(response.content)
    except ValidationError as exc:
        raise HTTPException(502,'Encoder trả dữ liệu sai hợp đồng.') from exc
    if result.model_revision!=revision or not all(math.isfinite(v) for v in result.vector) or not any(result.vector):
        raise HTTPException(502,'Vector không hữu hạn, bằng không hoặc sai phiên bản encoder.')
    return result


def cosine(left: list[float], right: list[float]) -> float:
    if len(left)!=len(right):
        raise HTTPException(502,'Số chiều vector không khớp; cần xây lại chỉ mục.')
    denominator = math.sqrt(sum(v*v for v in left)*sum(v*v for v in right))
    return sum(a*b for a,b in zip(left,right))/denominator if denominator else 0.0


def vector_ranking(db: sqlite3.Connection, kind: str, embedding: EmbeddingResponse, allowed: set[str]) -> list[str]:
    manifest = db.execute("SELECT * FROM index_manifests WHERE index_kind=? AND status='ready'", (kind,)).fetchone()
    if not manifest or manifest['model_revision']!=embedding.model_revision:
        raise HTTPException(503,'Chưa có chỉ mục sẵn sàng đúng phiên bản encoder.')
    scores: dict[str,float] = {}
    if kind=='text':
        rows = db.execute('''SELECT e.*,p.* FROM text_embeddings e JOIN products p ON p.id=e.product_id WHERE e.index_version=? AND e.model_revision=?''', (manifest['version'],embedding.model_revision)).fetchall()
        for row in rows:
            if row['product_id'] in allowed and row['source_hash']==digest(source_text(row)):
                scores[row['product_id']] = cosine(embedding.vector,json.loads(row['vector_data']))
    else:
        rows = db.execute('''SELECT e.*,a.product_id,a.media_hash AS live_hash,a.moderation_state FROM image_embeddings e JOIN media_assets a ON a.id=e.asset_id WHERE e.index_version=? AND e.model_revision=?''', (manifest['version'],embedding.model_revision)).fetchall()
        for row in rows:
            if row['product_id'] in allowed and row['media_hash']==row['live_hash'] and row['moderation_state']=='approved':
                score = cosine(embedding.vector,json.loads(row['vector_data']))
                scores[row['product_id']] = max(scores.get(row['product_id'],-1.0),score)
    return sorted(scores,key=lambda identity:(-scores[identity],identity))


@router.post('/api/search')
async def search(data: SearchInput) -> dict[str,list[str] | str | None]:
    if data.image_base64 and not data.media_consent:
        raise HTTPException(422,'Cần đồng ý gửi ảnh trước khi tìm kiếm.')
    if not data.query.strip() and not data.image_base64:
        raise HTTPException(422,'Hãy nhập từ khóa hoặc chọn ảnh.')
    rankings: list[list[str]] = []
    warnings: list[str] = []
    embeddings: list[tuple[str,EmbeddingResponse]] = []
    if data.query and data.semantic:
        try:
            embeddings.append(('text',await embed_text(data.query)))
        except HTTPException as exc:
            if exc.status_code not in {503,504}:
                raise
            warnings.append('text_encoder_unavailable')
    if data.image_base64:
        image = validate_image(data.image_base64)
        try:
            embeddings.append(('image',await embed_image(image)))
        except HTTPException as exc:
            if exc.status_code not in {503,504} or not data.query:
                raise
            warnings.append('visual_encoder_unavailable')
    with connection() as db:
        allowed = eligible_ids(db,data.category)
        if data.query:
            words = normalize(data.query).split()
            lexical = [r['id'] for r in db.execute('SELECT p.*,c.name AS category_name FROM products p JOIN categories c ON c.id=p.category')
                       if r['id'] in allowed and all(w in normalize(f"{r['name']} {r['brand']} {r['category_name']}") for w in words)] if words else []
            rankings.append(lexical)
        for kind,embedding in embeddings:
            try:
                rankings.append(vector_ranking(db,kind,embedding,allowed))
            except HTTPException as exc:
                if exc.status_code!=503 or (not data.query and kind=='image'):
                    raise
                warnings.append(kind+'_index_unavailable')
        scores: dict[str,float] = {}
        for ranking in rankings:
            for rank,identity in enumerate(ranking):
                scores[identity] = scores.get(identity,0)+1/(60+rank+1)
        selected = sorted(scores,key=lambda identity:(-scores[identity],identity))[:data.limit]
    return {'product_ids':selected,'mode':'hybrid' if len(rankings)>1 else 'lexical' if data.query else 'visual','fallback_reason':','.join(warnings) or None}


@router.post('/api/operator/indexes/build')
async def build_index(data: IndexInput, operator: Operator) -> dict[str,str | int]:
    with connection() as db:
        if data.kind=='text':
            records = [(r['id'],digest(source_text(r)),source_text(r)) for r in db.execute('SELECT * FROM products WHERE active=1')]
        else:
            records = [(r['id'],r['media_hash'],r['uri']) for r in db.execute("SELECT a.* FROM media_assets a JOIN products p ON p.id=a.product_id WHERE a.moderation_state='approved' AND p.active=1")]
    if not records:
        raise HTTPException(409,'Không có dữ liệu đủ điều kiện lập chỉ mục.')
    vectors: list[tuple[str,str,EmbeddingResponse]] = []
    for identity,source_hash,value in records:
        if data.kind=='text':
            embedding = await embed_text(value)
        else:
            assets = (ROOT/'frontend'/'assets').resolve()
            path = (assets/value).resolve()
            if not path.is_relative_to(assets) or not path.is_file():
                raise HTTPException(409,'Ảnh danh mục không có trong kho tài nguyên cục bộ.')
            image = path.read_bytes()
            if hashlib.sha256(image).hexdigest()!=source_hash:
                raise HTTPException(409,'Ảnh đã thay đổi, cần cập nhật media hash trước khi lập chỉ mục.')
            embedding = await embed_image(image)
        vectors.append((identity,source_hash,embedding))
    revision = vectors[0][2].model_revision
    dimension = len(vectors[0][2].vector)
    if any(e.model_revision!=revision or len(e.vector)!=dimension for _,_,e in vectors):
        raise HTTPException(502,'Phiên bản hoặc số chiều encoder thay đổi giữa quá trình lập chỉ mục.')
    version = new_id()
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        # Recheck snapshots after network calls; never publish a partially stale generation.
        for identity,source_hash,_ in vectors:
            if data.kind=='text':
                row = db.execute('SELECT * FROM products WHERE id=? AND active=1', (identity,)).fetchone()
                current = digest(source_text(row)) if row else None
            else:
                row = db.execute("SELECT media_hash FROM media_assets WHERE id=? AND moderation_state='approved'", (identity,)).fetchone()
                current = row['media_hash'] if row else None
            if current!=source_hash:
                raise HTTPException(409,'Danh mục thay đổi trong lúc xây chỉ mục. Phiên bản hiện tại vẫn được giữ.')
        db.execute("INSERT INTO index_manifests(index_kind,version,model_revision,status) VALUES (?,?,?,'building')", (data.kind,version,revision))
        for identity,source_hash,embedding in vectors:
            if data.kind=='text':
                db.execute('INSERT INTO text_embeddings(product_id,model_revision,index_version,source_hash,vector_data) VALUES (?,?,?,?,?)', (identity,revision,version,source_hash,json.dumps(embedding.vector)))
            else:
                db.execute('INSERT INTO image_embeddings(asset_id,model_revision,index_version,media_hash,vector_data) VALUES (?,?,?,?,?)', (identity,revision,version,source_hash,json.dumps(embedding.vector)))
        db.execute("UPDATE index_manifests SET status='retired' WHERE index_kind=? AND status='ready'", (data.kind,))
        db.execute("UPDATE index_manifests SET status='ready' WHERE index_kind=? AND version=?", (data.kind,version))
        audit(db,operator,'index.published',version,data.kind)
    return {'version':version,'kind':data.kind,'items':len(vectors),'status':'ready'}


@router.get('/api/operator/indexes')
def indexes(operator: Operator) -> list[dict[str,str]]:
    with connection() as db:
        return [dict(r) for r in db.execute('SELECT * FROM index_manifests ORDER BY rowid DESC')]
