"""Optional CPU embedding service, separate from the transactional store.

Install the encoders extra and download the configured model revisions before use.
BGE-M3 embeds text; CLIP embeds catalog/query images in a separate vector space.
"""

import io
import os
from functools import lru_cache
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel, Field

from .discovery import validate_image
from .dtos import EmbeddingResponse
from .config import setting

os.environ.setdefault("HF_HOME",str(Path(__file__).resolve().parent.parent/"data"/"models"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY","1")

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

BGE_REVISION = '5617a9f61b028005a4858fdac845db406aefb181'
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    model('BAAI/bge-m3',setting('BGE_MODEL_REVISION') or BGE_REVISION)
    visual_revision=setting('CLIP_MODEL_REVISION')
    if visual_revision:
        model('sentence-transformers/clip-ViT-B-32',visual_revision)
    yield


app = FastAPI(title='May local text and visual encoders',version='0.3.0',lifespan=lifespan)


class TextInput(BaseModel):
    text: str = Field(min_length=1,max_length=20000)
    model: Literal['BAAI/bge-m3']


class ImageInput(BaseModel):
    image_base64: str = Field(max_length=7000000)


@lru_cache(maxsize=2)
def model(name: str, revision: str) -> 'SentenceTransformer':
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise HTTPException(503,'Cài extra encoders trước khi chạy dịch vụ embedding.') from exc
    return SentenceTransformer(name,revision=revision,device=os.environ.get('ENCODER_DEVICE','cpu'),trust_remote_code=False,token=False)


@app.post('/embed-text',response_model=EmbeddingResponse)
def text_embedding(data: TextInput) -> EmbeddingResponse:
    revision = setting('BGE_MODEL_REVISION') or BGE_REVISION
    vector = model('BAAI/bge-m3',revision).encode(data.text,normalize_embeddings=True).tolist()
    return EmbeddingResponse(model_revision='BAAI/bge-m3@'+revision,vector=vector)


@app.post('/embed-image',response_model=EmbeddingResponse)
def image_embedding(data: ImageInput) -> EmbeddingResponse:
    revision = setting('CLIP_MODEL_REVISION')
    if not revision:
        raise HTTPException(503,'Cần CLIP_MODEL_REVISION là commit của visual model.')
    image = validate_image(data.image_base64)
    with Image.open(io.BytesIO(image)) as picture:
        vector = model('sentence-transformers/clip-ViT-B-32',revision).encode(picture.convert('RGB'),normalize_embeddings=True).tolist()
    return EmbeddingResponse(model_revision='sentence-transformers/clip-ViT-B-32@'+revision,vector=vector)
