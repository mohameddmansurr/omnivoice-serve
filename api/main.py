import asyncio
import io
import os
import time
from typing import List
import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, Response
from prometheus_client import Histogram, Gauge, Counter, generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel
from omnivoice import OmniVoice

app = FastAPI()
GPU_ID = int(os.environ.get("GPU_ID", 0))
MAX_BATCH = int(os.environ.get("MAX_BATCH", 8))
BATCH_WAIT_MS = float(os.environ.get("BATCH_WAIT_MS", 50))

LATENCY = Histogram("tts_inference_latency_seconds", "Inference latency", buckets=[0.5, 1, 2, 5, 10, 20, 30], labelnames=["gpu"])
ACTIVE = Gauge("tts_active_connections", "Active connections", labelnames=["gpu"])
BATCH_SIZE = Histogram("tts_batch_size", "Batch size", buckets=[1,2,4,6,8,10,12,16], labelnames=["gpu"])
ERRORS = Counter("tts_errors_total", "Total errors", labelnames=["gpu"])
GPU_LABEL = str(GPU_ID)

print(f"[GPU {GPU_ID}] Loading OmniVoice on cuda:{GPU_ID} ...")
model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map={"": f"cuda:{GPU_ID}"}, torch_dtype=torch.float16)
print(f"[GPU {GPU_ID}] Ready.")

_queue = asyncio.Queue()

async def batch_runner():
    loop = asyncio.get_event_loop()
    while True:
        first = await _queue.get()
        batch = [first]
        deadline = loop.time() + BATCH_WAIT_MS / 1000.0
        while len(batch) < MAX_BATCH:
            remaining = deadline - loop.time()
            if remaining <= 0: break
            try:
                item = await asyncio.wait_for(_queue.get(), timeout=remaining)
                batch.append(item)
            except asyncio.TimeoutError: break
        
        texts = [item["text"] for item in batch]
        langs = [item["language"] for item in batch]
        futures = [item["future"] for item in batch]
        
        BATCH_SIZE.labels(GPU_LABEL).observe(len(batch))
        try:
            results = await loop.run_in_executor(None, _run_batch, texts, langs[0])
            for fut, wav in zip(futures, results):
                if not fut.done(): fut.set_result(wav)
        except Exception as e:
            for fut in futures:
                if not fut.done(): fut.set_exception(e)

def _run_batch(texts: List[str], lang: str) -> List[bytes]:
    audios = model.generate(text=texts, language=lang)
    results = []
    for audio in audios:
        buf = io.BytesIO()
        sf.write(buf, audio.astype(np.float32), model.sampling_rate, format="WAV", subtype="PCM_16")
        results.append(buf.getvalue())
    return results

@app.on_event("startup")
async def startup():
    asyncio.create_task(batch_runner())

class TTSRequest(BaseModel):
    text: str
    language: str = "ars"

@app.post("/tts/stream")
async def tts_http(req: TTSRequest):
    if _queue.qsize() >= MAX_BATCH * 8:
        raise HTTPException(status_code=503, detail="queue_full")
    ACTIVE.labels(GPU_LABEL).inc()
    future = asyncio.get_event_loop().create_future()
    await _queue.put({"text": req.text, "language": req.language, "future": future})
    try:
        wav = await asyncio.wait_for(future, timeout=60.0)
        return StreamingResponse(io.BytesIO(wav), media_type="audio/wav")
    finally:
        ACTIVE.labels(GPU_LABEL).dec()

@app.get("/health")
def health():
    return {"status": "ok", "gpu": GPU_ID, "queue": _queue.qsize()}
