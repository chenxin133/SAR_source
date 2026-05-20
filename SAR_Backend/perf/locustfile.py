from __future__ import annotations

from locust import HttpUser, between, task


class SarUser(HttpUser):
    wait_time = between(0.2, 1.0)

    @task(5)
    def list_images(self):
        self.client.get("/api/v1/images?limit=50&offset=0", name="images_list")

    @task(2)
    def healthz(self):
        self.client.get("/api/v1/healthz", name="healthz")
