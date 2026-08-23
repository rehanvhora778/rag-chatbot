"""The embedding model itself — ONNX Runtime, with a PyTorch fallback.

Both backends load the SAME all-MiniLM-L6-v2 weights in fp32 and apply the same
mean-pooling and L2-normalisation, so they produce identical vectors: an index
built under one stays valid under the other.

This is the machinery. ``LocalEmbeddingProvider`` in ``local.py`` is the
interface the rest of the system talks to — nothing outside this package should
import from here directly.

All ML imports are lazy, so importing this module costs nothing: Django starts,
``manage.py`` runs and tests collect without loading onnxruntime, transformers
or torch.
"""
import contextlib
import logging
import threading
from typing import List

logger = logging.getLogger(__name__)

_backend = None
_backend_lock = threading.Lock()

# all-MiniLM-L6-v2's native sequence limit.
_MAX_SEQ_LENGTH = 256


def _usable_cores() -> int:
    """How many cores this process may actually use.

    os.cpu_count() reports the *host's* cores, not the container's limit. A
    Render free instance is capped at 0.15 CPU while the host reports 8+, and
    giving ONNX Runtime that many intra-op threads makes them fight over a
    fraction of a core: embedding stops finishing rather than failing, so an
    upload sits in "processing" forever with nothing in the log. The cgroup
    quota is the number that matters inside a container.
    """
    import os

    # cgroup v2 — "<quota> <period>", or "max <period>" when unlimited.
    # Not every platform has cgroups, and the files are absent rather than
    # empty when it doesn't — suppress rather than log, because "this is not
    # Linux" is the expected case, not a fault.
    with contextlib.suppress(Exception):
        with open('/sys/fs/cgroup/cpu.max') as fh:
            quota, period = fh.read().split()
        if quota != 'max':
            return max(1, round(int(quota) / int(period)))

    # cgroup v1
    with contextlib.suppress(Exception):
        with open('/sys/fs/cgroup/cpu/cpu.cfs_quota_us') as fh:
            quota = int(fh.read())
        with open('/sys/fs/cgroup/cpu/cpu.cfs_period_us') as fh:
            period = int(fh.read())
        if quota > 0:
            return max(1, round(quota / period))

    return os.cpu_count() or 1


class _OnnxBackend:
    """MiniLM-style bi-encoder on ONNX Runtime (mean pooling + L2 norm)."""

    def __init__(self, model_name: str, provider_pref: str = 'auto'):
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from transformers import AutoTokenizer

        repo_id = model_name if '/' in model_name else f'sentence-transformers/{model_name}'
        try:
            model_path = hf_hub_download(repo_id, 'onnx/model.onnx')
        except Exception:
            # No network — fall back to whatever is already in the local HF cache.
            model_path = hf_hub_download(repo_id, 'onnx/model.onnx', local_files_only=True)
        self.tokenizer = AutoTokenizer.from_pretrained(repo_id)

        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        use_dml = (
            provider_pref in ('auto', 'dml')
            and 'DmlExecutionProvider' in ort.get_available_providers()
        )
        if use_dml:
            providers = ['DmlExecutionProvider', 'CPUExecutionProvider']
        else:
            providers = ['CPUExecutionProvider']
            so.intra_op_num_threads = _usable_cores()
            so.inter_op_num_threads = 1
            so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

            # ONNX Runtime's thread pools busy-wait before parking. That is a
            # throughput win on a dedicated box and a disaster on a CPU-capped
            # container: the spinning threads burn the whole cgroup quota, the
            # scheduler throttles the process, and the thread doing the actual
            # inference barely advances. On a 0.15 CPU Render instance a single
            # batch of six short chunks never finished.
            so.add_session_config_entry('session.intra_op.allow_spinning', '0')
            so.add_session_config_entry('session.inter_op.allow_spinning', '0')

            logger.info("ONNX intra-op threads: %d (spinning off)", so.intra_op_num_threads)
        self.session = ort.InferenceSession(model_path, so, providers=providers)
        self.input_names = {i.name for i in self.session.get_inputs()}
        self.device = 'DirectML GPU' if 'DmlExecutionProvider' in self.session.get_providers() else 'CPU'

        # One backend instance is shared by every request and every background
        # upload thread. The DirectML provider is NOT safe to enter from two
        # threads at once — concurrent run() calls segfault the whole process,
        # which takes Django down with them (uploading two files at the same
        # time was enough to trigger it). Inference is therefore serialised.
        # The GPU is a single resource anyway, so this costs no real throughput:
        # work is already batched inside each call.
        self._infer_lock = threading.Lock()

    def _encode_batch(self, texts: List[str]):
        import numpy as np

        enc = self.tokenizer(
            texts,
            return_tensors='np',
            padding=True,
            truncation=True,
            max_length=_MAX_SEQ_LENGTH,
        )
        feeds = {k: v.astype(np.int64) for k, v in enc.items() if k in self.input_names}
        with self._infer_lock:
            (hidden,) = self.session.run(None, feeds)
        mask = enc['attention_mask'][..., None].astype(np.float32)
        emb = (hidden * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1e-9, None)
        emb /= np.clip(np.linalg.norm(emb, axis=1, keepdims=True), 1e-12, None)
        return emb.astype(np.float32)

    def encode(self, texts: List[str], batch_size: int):
        import time

        import numpy as np

        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        # Sort by length so each batch pads to its own (shorter) maximum, then
        # restore the caller's order at the end.
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))

        starts = list(range(0, len(order), batch_size))
        total = len(starts)
        chunks = []
        started = time.perf_counter()
        for n, i in enumerate(starts, 1):
            chunks.append(self._encode_batch([texts[j] for j in order[i:i + batch_size]]))
            # A 50-page document is ~100 chunks and takes minutes on a throttled
            # container. Without this the log goes silent between "embedding…"
            # and "embedded", which is indistinguishable from a hang — that cost
            # a long time to diagnose once already.
            if total > 1:
                logger.info(
                    "  embedding batch %d/%d (%d texts, %.1fs elapsed)",
                    n, total, len(order[i:i + batch_size]), time.perf_counter() - started,
                )

        flat = np.vstack(chunks)
        out = np.empty_like(flat)
        out[order] = flat
        return out


class _TorchBackend:
    """Original sentence-transformers path — fallback when ONNX is unavailable."""

    def __init__(self, model_name: str):
        import os

        from sentence_transformers import SentenceTransformer

        # Best-effort thread tuning; torch works fine at its default if this
        # version doesn't expose the setter.
        with contextlib.suppress(Exception):
            import torch
            torch.set_num_threads(os.cpu_count() or 1)
        self.model = SentenceTransformer(model_name)
        self.device = 'CPU (torch)'

    def encode(self, texts: List[str], batch_size: int):
        import numpy as np

        emb = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return emb.astype(np.float32)


def get_embedding_model():
    """Return the singleton embedding backend, creating it on first use."""
    global _backend
    if _backend is not None:
        return _backend
    with _backend_lock:
        if _backend is not None:
            return _backend

        from django.conf import settings

        model_name = settings.EMBEDDING_MODEL_NAME
        preferred = getattr(settings, 'EMBEDDING_BACKEND', 'onnx')
        if preferred == 'onnx':
            try:
                logger.info("Loading embedding model (ONNX): %s", model_name)
                _backend = _OnnxBackend(
                    model_name,
                    provider_pref=getattr(settings, 'EMBEDDING_ONNX_PROVIDER', 'auto'),
                )
                logger.info("Embedding model ready on %s.", _backend.device)
                return _backend
            except Exception as exc:
                logger.warning("ONNX embedding backend unavailable (%s) — falling back to torch.", exc)

        logger.info("Loading embedding model (torch): %s", model_name)
        try:
            _backend = _TorchBackend(model_name)
        except ImportError as exc:
            # Production installs (requirements-prod.txt) leave PyTorch out, so
            # this fallback simply isn't there. Say so plainly — otherwise the
            # only clue is a bare "No module named 'sentence_transformers'".
            raise RuntimeError(
                f"No embedding backend is available. The ONNX backend failed to load and "
                f"the PyTorch fallback is not installed ({exc}). On a production install "
                f"keep EMBEDDING_BACKEND=onnx and check the ONNX error logged above; "
                f"to use the fallback instead, install sentence-transformers."
            ) from exc
        logger.info("Embedding model ready on %s.", _backend.device)
        return _backend


def embed_texts(texts: List[str], batch_size: int = None):
    from django.conf import settings

    if batch_size is None:
        batch_size = getattr(settings, 'EMBEDDING_BATCH_SIZE', 64)

    # A batch of 64 sequences padded to 256 tokens is a large activation tensor
    # to hold at once in a 512 MB container, and on a fraction of a core it is
    # also a long time to spend inside one call with nothing observable. Where
    # the cgroup quota says we have a single core, embed in small batches
    # instead: the same total work, but steady progress and a far lower peak.
    if _usable_cores() <= 1:
        batch_size = min(batch_size, 8)

    return get_embedding_model().encode(texts, batch_size=batch_size)


def embed_query(query: str):
    return embed_texts([query])
