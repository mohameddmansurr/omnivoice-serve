# 🚀 OmniVoice Serve

A production-ready, high-throughput inference server for **OmniVoice**, designed for large-scale real-time conversational AI workloads.

The server maximizes GPU utilization through **dynamic batching**, **asynchronous request queuing**, **fail-fast admission control**, and **Nginx load balancing**, enabling stable inference under heavy concurrent traffic while minimizing latency and preventing GPU memory fragmentation.

---

# ✨ Features

- 🚀 Dynamic request batching
- ⚡ Low-latency streaming inference
- 🎯 Multi-GPU support
- 🔄 Nginx load balancing
- 📦 Async request queue
- 🛡️ Fail-fast overload protection
- 💾 Optimized FP16 inference
- 📈 Prometheus-ready monitoring
- 🧪 Built-in Locust load testing

---

# 🏗️ Architecture

```text
                    Client Requests
                           │
                           ▼
                  Nginx Load Balancer
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
      GPU Worker 0     GPU Worker 1     GPU Worker 2
      FastAPI          FastAPI          FastAPI
          │                │                │
          ▼                ▼                ▼
     Async Request Queue (per worker)
          │
          ▼
    Dynamic Batch Builder
      • Max Batch: 16
      • Wait: 40 ms
          │
          ▼
      OmniVoice Model
          │
          ▼
     Streaming WAV Response
```

---

# ⚙️ How It Works

Incoming requests follow this execution pipeline:

1. Requests arrive through **Nginx**.
2. Nginx distributes traffic across available GPU workers.
3. Each worker places incoming requests into an asynchronous queue.
4. The batch scheduler waits up to **40 ms** to accumulate requests.
5. Up to **16 requests** are merged into a single GPU forward pass.
6. Audio is streamed back to each client independently.
7. If the queue reaches capacity, new requests immediately receive **HTTP 503** instead of waiting indefinitely.

This design maximizes GPU utilization while preventing VRAM fragmentation and out-of-memory crashes.

---

# 💻 Hardware Requirements

## Tested Configuration

| Component | Specification |
|-----------|---------------|
| GPUs | 3 × NVIDIA RTX 4090 (24 GB) |
| CPU | 45 Cores |
| Memory | 235 GB RAM |
| NVIDIA Driver | 580.159.03 or newer |
| CUDA | 13.0+ |

---

# 📦 Software Requirements

- Python 3.12
- Conda
- Docker
- CUDA Toolkit
- NVIDIA Drivers
- Nginx

---

# 🚀 Installation

## 1. Create the Conda Environment

```bash
conda create -n omnivoice python=3.12 -y
conda activate omnivoice
```

---

## 2. Install PyTorch

CUDA 12.8 wheels:

```bash
pip install torch torchaudio \
    --index-url https://download.pytorch.org/whl/cu128
```

---

## 3. Install Dependencies

```bash
pip install \
    omnivoice \
    fastapi \
    "uvicorn[standard]" \
    soundfile \
    prometheus-client \
    pydantic \
    locust
```

---

# 🚦 Deployment

Run all commands from the project root.

## Step 1 — Clean Existing Processes

```bash
pkill -9 python
pkill -9 uvicorn

sudo fuser -k /dev/nvidia*

nvidia-smi \
    --query-gpu=index,memory.used \
    --format=csv
```

GPU memory should be close to **0 MiB** before launching workers.

---

## Step 2 — Start Nginx

```bash
sudo docker rm -f nginx_lb 2>/dev/null

sudo docker run -d \
    --name nginx_lb \
    --network host \
    -v $(pwd)/nginx/nginx.conf:/etc/nginx/nginx.conf:ro \
    nginx:alpine
```

---

## Step 3 — Launch GPU Workers

```bash
cd api

for GPU in 0 1 2; do
    PORT=$((8001 + GPU))

    nohup bash -c "
        export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

        GPU_ID=${GPU}
        MAX_BATCH=16
        BATCH_WAIT_MS=40

        uvicorn main:app \
            --host 0.0.0.0 \
            --port ${PORT} \
            --workers 1
    " >> /tmp/api_gpu${GPU}.log 2>&1 &

    echo "Started GPU ${GPU} on port ${PORT}"
done
```

Wait approximately **60 seconds** for the models to finish loading.

---

## Step 4 — Health Checks

```bash
curl http://localhost:8001/health

curl http://localhost:8002/health

curl http://localhost:8003/health
```

All workers should report healthy.

---

# 🧪 Load Testing

A preconfigured **Locust** benchmark is included.

Start the Locust server:

```bash
conda activate omnivoice

locust \
    -f locust/locustfile.py \
    --host http://localhost \
    --web-port 8090
```

Open:

```
http://localhost:8090
```

Recommended benchmark:

| Parameter | Value |
|-----------|-------|
| Users | 100 |
| Spawn Rate | 10 users/sec |
| Think Time | 10–20 seconds |

Target performance:

- 0% failures
- Median latency < 3.5 seconds

---

# 📡 API

## Endpoint

```
POST /tts/stream
```

---

## Request

```json
{
  "text": "مرحبا كيف يمكنني مساعدتك اليوم",
  "language": "ars"
}
```

The language defaults to **`ars`** (Saudi / Najdi Arabic).

---

## Response

Returns a streamed **WAV** audio response.

- Format: 16-bit PCM
- Sample Rate: 24 kHz
- Content-Type: `audio/wav`

---

## Example

```bash
curl -X POST http://localhost/tts/stream \
    -H "Content-Type: application/json" \
    -d '{
        "text":"مرحبا كيف حالك",
        "language":"ars"
    }' \
    --output output.wav
```

---

# 📁 Repository Structure

```text
serve/
├── api/
│   ├── main.py
│   ├── batching.py
│   ├── inference.py
│   └── queue.py
│
├── nginx/
│   └── nginx.conf
│
├── locust/
│   └── locustfile.py
│
├── Dockerfile
├── requirements.txt
└── README.md
```

---

# 📄 License

Update this section with the appropriate license before public release.
