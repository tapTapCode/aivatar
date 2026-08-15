from src.providers.http_client import JsonHttpProviderClient
from src.schemas.assets import GeneratedAsset
from src.schemas.requests import SpeechGenerationRequest


class SpeechWorkerClient(JsonHttpProviderClient):
    async def generate(self, request: SpeechGenerationRequest) -> GeneratedAsset:
        return await self.post_asset("v1/generate", request)
