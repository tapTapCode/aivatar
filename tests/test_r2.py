from pathlib import Path
from pipeline.storage.r2 import R2Storage


class FakeS3:
    def __init__(self):
        self.objects = {}
    def upload_file(self, source, bucket, key, ExtraArgs=None):
        self.objects[(bucket, key)] = Path(source).read_bytes()
    def head_object(self, Bucket, Key):
        data = self.objects[(Bucket, Key)]
        return {"ETag": '"abc"', "ContentLength": len(data)}
    def download_file(self, bucket, key, destination):
        Path(destination).write_bytes(self.objects[(bucket, key)])


def test_r2_keys_and_roundtrip(monkeypatch, tmp_path: Path):
    storage = R2Storage("acct", "key", "secret", "bucket")
    fake = FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)
    source = tmp_path / "a.txt"
    source.write_text("hello")
    key = storage.project_key("p1", "images", "a.txt")
    meta = storage.upload_file(source, key, "text/plain")
    dest = tmp_path / "downloaded.txt"
    storage.download_file(key, dest)
    assert key == "projects/p1/images/a.txt"
    assert meta["size"] == 5
    assert dest.read_text() == "hello"
