"""Couche neuronale facultative, 100 % locale (ONNX Runtime sur le processeur, sans PyTorch ni GPU).

- Encodeur de phrases multilingue (famille E5 : « query: » / « passage: », moyenne des jetons, normalisation L2) :
  la question et le texte sont comparés par le sens, même dans deux langues différentes.
- Reranker « cross-encoder » multilingue (mMiniLM entraîné sur mMARCO) : relit la question et chaque candidat ensemble
  pour le classement final des 30 premiers.

Les modèles ne sont jamais téléchargés sans action explicite (écran « API & moteur ») ; ils vivent dans
data/models/<id>/ (model.onnx + tokenizer.json). Sans eux, le moteur reste hybride lexical (BM25F + RM3 + thésaurus +
n-grammes) : rien ne casse. Un miroir interne peut remplacer Hugging Face : MERLIN_MODELS_URL.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

HF = "https://huggingface.co"


@dataclass(frozen=True)
class ModelSpec:
    id: str
    kind: str  # encoder | reranker
    label: str
    repo: str
    files: dict[str, str]  # nom local → chemin dans le dépôt
    size_mb: int
    license: str
    dim: int = 0
    max_len: int = 512
    query_prefix: str = ""
    passage_prefix: str = ""
    note: str = ""


MODELS: dict[str, ModelSpec] = {m.id: m for m in [
    ModelSpec("e5-small", "encoder", "Multilingual E5 small (int8)", "Xenova/multilingual-e5-small",
              {"model.onnx": "onnx/model_quantized.onnx", "tokenizer.json": "tokenizer.json"}, 136, "MIT", 384, 512,
              "query: ", "passage: ", "Rapide : ~100 langues, idéal sur un poste standard."),
    ModelSpec("e5-base", "encoder", "Multilingual E5 base (int8)", "Xenova/multilingual-e5-base",
              {"model.onnx": "onnx/model_quantized.onnx", "tokenizer.json": "tokenizer.json"}, 296, "MIT", 768, 512,
              "query: ", "passage: ", "Plus précis, deux fois plus lent à indexer."),
    ModelSpec("rerank-mminilm", "reranker", "mMiniLM-L12 cross-encoder mMARCO (int8)", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
              {"model.onnx": "onnx/model_quint8_avx2.onnx", "tokenizer.json": "tokenizer.json"}, 136, "Apache-2.0", 0, 512,
              note="Reclasse les 30 premiers résultats en lisant question et texte ensemble (FR / EN / ES / IT…)."),
    ModelSpec("rerank-bge-m3", "reranker", "BGE reranker v2 m3 (int8)", "onnx-community/bge-reranker-v2-m3-ONNX",
              {"model.onnx": "onnx/model_int8.onnx", "tokenizer.json": "tokenizer.json"}, 588, "Apache-2.0", 0, 512,
              note="Reranker multilingue de référence (BAAI) : plus fin, environ trois fois plus lent."),
]}
DEFAULT_ENCODER = "e5-small"
DEFAULT_RERANKER = "rerank-mminilm"


def available() -> bool:
    try:
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def model_dir(root: Path, model_id: str) -> Path:
    return root / model_id


def installed(root: Path, model_id: str) -> bool:
    spec = MODELS.get(model_id)
    return bool(spec) and all((model_dir(root, model_id) / name).exists() for name in spec.files)


# ---------------------------------------------------------------------------------------------- téléchargement
class Downloads:
    """Téléchargements explicites, un à la fois par modèle, écriture atomique (.part puis renommage)."""

    def __init__(self, root: Path):
        self.root = root
        self.state: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start(self, model_id: str) -> dict[str, Any]:
        spec = MODELS[model_id]
        with self._lock:
            current = self.state.get(model_id)
            if current and current.get("running"):
                return current
            self.state[model_id] = {"running": True, "done": 0, "total": spec.size_mb * 1_000_000, "error": None, "file": ""}
        threading.Thread(target=self._run, args=(spec,), name=f"model-{model_id}", daemon=True).start()
        return self.state[model_id]

    def _run(self, spec: ModelSpec) -> None:
        import httpx

        from ..fundshop.net import NetError, _classify  # mêmes règles réseau que le reste de l'app (proxy, certificats)

        state = self.state[spec.id]
        base = os.environ.get("MERLIN_MODELS_URL", HF).rstrip("/")
        folder = model_dir(self.root, spec.id)
        folder.mkdir(parents=True, exist_ok=True)
        verify: Any = True
        try:
            import ssl

            import truststore

            verify = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:  # noqa: BLE001
            pass
        try:
            with httpx.Client(follow_redirects=True, timeout=120, verify=verify) as client:
                for name, remote in spec.files.items():
                    target = folder / name
                    if target.exists():
                        continue
                    state["file"] = name
                    part = target.with_suffix(target.suffix + ".part")
                    url = f"{base}/{spec.repo}/resolve/main/{remote}"
                    with client.stream("GET", url) as r:
                        if r.status_code >= 400:
                            raise RuntimeError(f"{url} : HTTP {r.status_code}")
                        with part.open("wb") as f:
                            for chunk in r.iter_bytes(1 << 20):
                                f.write(chunk)
                                state["done"] += len(chunk)
                    part.replace(target)
            state.update(running=False, finished=time.time())
        except httpx.HTTPError as error:
            err: NetError = _classify(error, base)
            state.update(running=False, error=f"{err.code} : {err}")
        except Exception as error:  # noqa: BLE001 - un échec n'arrête jamais l'app
            state.update(running=False, error=str(error)[:300])


# ---------------------------------------------------------------------------------------------- inférence
def _session(path: Path):
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = max(1, min(8, (os.cpu_count() or 2) - 1))
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(path), sess_options=opts, providers=["CPUExecutionProvider"])


def _tokenizer(path: Path, max_len: int):
    from tokenizers import Tokenizer

    tok = Tokenizer.from_file(str(path))
    tok.enable_truncation(max_length=max_len)
    tok.enable_padding(pad_id=tok.token_to_id("<pad>") if tok.token_to_id("<pad>") is not None else 0)
    return tok


class Encoder:
    """Encodeur de phrases ONNX : vecteurs normalisés (cosinus = produit scalaire)."""

    def __init__(self, root: Path, model_id: str = DEFAULT_ENCODER, max_len: int = 384):
        self.spec = MODELS[model_id]
        folder = model_dir(root, model_id)
        self.session = _session(folder / "model.onnx")
        self.tokenizer = _tokenizer(folder / "tokenizer.json", min(max_len, self.spec.max_len))
        self.inputs = {i.name for i in self.session.get_inputs()}
        self._lock = threading.Lock()

    @property
    def id(self) -> str:
        return self.spec.id

    def _run(self, texts: list[str]) -> np.ndarray:
        enc = self.tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        with self._lock:
            hidden = self.session.run(None, feed)[0]
        summed = (hidden * mask[..., None]).sum(axis=1)
        vectors = summed / np.clip(mask.sum(axis=1, keepdims=True), 1, None)
        return vectors / np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9, None)

    def encode(self, texts: list[str], kind: str = "passage", batch: int = 16) -> np.ndarray:
        prefix = self.spec.query_prefix if kind == "query" else self.spec.passage_prefix
        out = []
        # tri par longueur : moins de remplissage, deux à trois fois plus rapide sur un gros lot
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        for start in range(0, len(order), batch):
            idx = order[start:start + batch]
            out.append((idx, self._run([prefix + (texts[i] or " ") for i in idx])))
        result = np.zeros((len(texts), self.spec.dim or (out[0][1].shape[1] if out else 1)), dtype=np.float32)
        for idx, vecs in out:
            result[idx] = vecs
        return result


class Reranker:
    """Cross-encoder ONNX : score de pertinence (0–1) d'un couple (question, texte)."""

    def __init__(self, root: Path, model_id: str = DEFAULT_RERANKER, max_len: int = int(os.environ.get("MERLIN_RERANK_MAXLEN", "320"))):
        self.spec = MODELS[model_id]
        folder = model_dir(root, model_id)
        self.session = _session(folder / "model.onnx")
        self.tokenizer = _tokenizer(folder / "tokenizer.json", min(max_len, self.spec.max_len))
        self.inputs = {i.name for i in self.session.get_inputs()}
        self._lock = threading.Lock()

    @property
    def id(self) -> str:
        return self.spec.id

    def score(self, query: str, passages: list[str], batch: int = 16) -> np.ndarray:
        scores = []
        for start in range(0, len(passages), batch):
            enc = self.tokenizer.encode_batch([(query, p or " ") for p in passages[start:start + batch]])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.inputs:
                feed["token_type_ids"] = np.array([e.type_ids for e in enc], dtype=np.int64)
            with self._lock:
                logits = self.session.run(None, feed)[0].reshape(-1)
            scores.append(1 / (1 + np.exp(-logits)))
        return np.concatenate(scores) if scores else np.zeros(0)


# ---------------------------------------------------------------------------------------------- vecteurs en cache
def text_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]


class VectorCache:
    """Vecteurs des passages, par empreinte du texte : seuls les textes nouveaux ou modifiés sont encodés."""

    def __init__(self, path: Path | None = None):
        self.path = path  # None : en mémoire seulement
        self.vectors: dict[str, np.ndarray] = {}
        if path is not None and path.exists():
            try:
                data = np.load(path, allow_pickle=False)
                for key, row in zip(data["keys"], data["vectors"]):
                    self.vectors[str(key)] = row.astype(np.float32)
            except Exception:  # noqa: BLE001 - cache illisible : on réencode
                self.vectors = {}

    def missing(self, keys: list[str]) -> list[str]:
        return [k for k in dict.fromkeys(keys) if k not in self.vectors]

    def put(self, keys: list[str], vectors: np.ndarray) -> None:
        for k, v in zip(keys, vectors):
            self.vectors[k] = v.astype(np.float32)

    def matrix(self, keys: list[str]) -> np.ndarray:
        dim = next(iter(self.vectors.values())).shape[0] if self.vectors else 1
        return np.stack([self.vectors.get(k, np.zeros(dim, dtype=np.float32)) for k in keys]) if keys else np.zeros((0, dim), np.float32)

    def save(self, keep: set[str] | None = None) -> None:
        keys = [k for k in self.vectors if keep is None or k in keep]
        if not keys or self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.stem + ".tmp.npz")
        np.savez(tmp, keys=np.array(keys), vectors=np.stack([self.vectors[k] for k in keys]).astype(np.float16))
        tmp.replace(self.path)


__all__ = ["MODELS", "ModelSpec", "Encoder", "Reranker", "VectorCache", "Downloads", "available", "installed", "model_dir",
           "text_hash", "DEFAULT_ENCODER", "DEFAULT_RERANKER"]
