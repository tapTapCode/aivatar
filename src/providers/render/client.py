from src.providers.http_client import JsonHttpProviderClient
from src.schemas.assets import GeneratedAsset
from src.schemas.requests import SceneRenderRequest


class RenderWorkerClient(JsonHttpProviderClient):
    async def render(self, request: SceneRenderRequest) -> GeneratedAsset:
        return await self.post_asset("v1/generate", request)
