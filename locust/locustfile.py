import random
import time
from locust import HttpUser, task, between, events

TEXTS = [
    "مرحبا كيف يمكنني مساعدتك اليوم",
    "اهلا وسهلا بك في نظام المساعد الصوتي",
    "شكرا على تواصلك معنا سنرد عليك في اقرب وقت",
    "هذا النظام مخصص لخدمة عملاء الكهرباء في المملكة العربية السعودية",
    "يرجى الانتظار بينما نقوم بمعالجة طلبك",
]

class TTSUser(HttpUser):
    wait_time = between(10, 20)
    network_timeout = 60
    connection_timeout = 10

    @task(5)
    def tts(self):
        start = time.perf_counter()
        with self.client.post(
            "/tts/stream",
            json={"text": random.choice(TEXTS), "language": "ars"},
            catch_response=True,
            timeout=60,
        ) as r:
            elapsed = (time.perf_counter() - start) * 1000
            if r.status_code == 503:
                # Queue full — report as separate metric, not failure
                r.success()
                events.request.fire(
                    request_type="TTS",
                    name="503_queue_full",
                    response_time=elapsed,
                    response_length=0,
                    exception=None,
                    context={},
                )
            elif r.status_code != 200:
                r.failure(f"HTTP {r.status_code}: {r.text[:80]}")
            elif len(r.content) < 1000:
                r.failure(f"Bad response: {len(r.content)}b content={r.text[:80]}")
            else:
                r.success()
                events.request.fire(
                    request_type="TTS",
                    name="success_audio",
                    response_time=elapsed,
                    response_length=len(r.content),
                    exception=None,
                    context={},
                )

    @task(1)
    def health(self):
        self.client.get("/health", timeout=5)
