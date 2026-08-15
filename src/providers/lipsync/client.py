from src.providers.http_client import JsonHttpProviderClient
from src.schemas.assets import GeneratedAsset
from src.schemas.requests import LipSyncRequest


class LipSyncWorkerClient(JsonHttpProviderClient):
    async def generate(self, request: LipSyncRequest) -> GeneratedAsset:
        return await self.post_asset("v1/generate", request)
