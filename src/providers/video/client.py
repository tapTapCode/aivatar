from src.providers.http_client import JsonHttpProviderClient
from src.schemas.assets import GeneratedAsset
from src.schemas.requests import VisualGenerationRequest


class VideoWorkerClient(JsonHttpProviderClient):
    async def generate(self, request: VisualGenerationRequest) -> GeneratedAsset:
        return await self.post_asset("v1/generate", request)
