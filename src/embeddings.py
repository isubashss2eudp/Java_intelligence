from __future__ import annotations

import os

from langchain_huggingface import HuggingFaceEmbeddings



os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

_MODEL_PATH = os.path.join(
    os.path.expanduser("~"),
    ".cache", "huggingface", "hub",
    "models--BAAI--bge-base-en-v1.5",
    "snapshots",
    "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"
)

def load_embeddings():
    embeddings = HuggingFaceEmbeddings(
        model_name=_MODEL_PATH,
        model_kwargs={
            "local_files_only": True
        },
        encode_kwargs={
            "normalize_embeddings": True
        }
    )
    return embeddings