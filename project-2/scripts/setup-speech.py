"""Install only the optional local recognizer model; never disables TLS verification."""
import argparse
import os
import ssl
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--model',default='base.en',choices=['base.en','small.en'])
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
os.environ.setdefault('HF_HUB_DISABLE_XET','1')
try:
    import httpx
    from huggingface_hub import set_client_factory
    from faster_whisper import WhisperModel
    set_client_factory(lambda:httpx.Client(verify=ssl.create_default_context(),follow_redirects=True,timeout=60))
    WhisperModel(args.model,device='cpu',compute_type='int8',download_root=str(root/'backend/models/whisper'))
except Exception as exc:
    print('Speech model setup failed ('+type(exc).__name__+'). Check approved network access to Hugging Face model files.')
    print('If binary downloads are blocked, ask your network administrator or use an approved local model folder in WHISPER_MODEL.')
    raise SystemExit(1)
print('Model ready:',args.model)
