"""Download pinned local models and configure their separate HTTP embedding spaces."""

import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
os.environ.setdefault('HF_HOME',str(ROOT/'data'/'models'))
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY','1')
os.environ.setdefault('HF_HUB_DISABLE_XET','1')

from huggingface_hub import HfApi
from sentence_transformers import SentenceTransformer

bge_revision='5617a9f61b028005a4858fdac845db406aefb181'
clip_revision=HfApi(token=False).model_info('sentence-transformers/clip-ViT-B-32').sha
if not clip_revision:
    raise RuntimeError('Could not resolve the visual model commit')
for name,revision in [('BAAI/bge-m3',bge_revision),('sentence-transformers/clip-ViT-B-32',clip_revision)]:
    print('Preparing',name,'at',revision,flush=True)
    SentenceTransformer(name,revision=revision,device='cpu',trust_remote_code=False,token=False)
updates={'TEXT_ENCODER_URL':'http://127.0.0.1:8768','TEXT_ENCODER_REVISION':'BAAI/bge-m3@'+bge_revision,
         'VISUAL_ENCODER_URL':'http://127.0.0.1:8768','VISUAL_ENCODER_REVISION':'sentence-transformers/clip-ViT-B-32@'+clip_revision,
         'BGE_MODEL_REVISION':bge_revision,'CLIP_MODEL_REVISION':clip_revision}
config=ROOT/'.env.local'
previous=config.read_text().splitlines() if config.exists() else []
previous=[line for line in previous if line.partition('=')[0] not in updates]
config.write_text('\n'.join(previous+[f'{key}={value}' for key,value in updates.items()])+'\n')
config.chmod(0o600)
(ROOT/'data'/'encoder_revisions.json').write_text(json.dumps(updates,indent=2)+'\n')
print('Pinned text and visual models ready; local encoder configuration saved.',flush=True)
