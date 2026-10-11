import asyncio
import base64
import importlib.util
import sys
from types import ModuleType
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

# These declared plugin dependencies are not needed by the media/cache unit tests.
for _module_name in ("json5", "bs4"):
    if importlib.util.find_spec(_module_name) is None:
        sys.modules.setdefault(_module_name, ModuleType(_module_name))

import media as media_module  # noqa: E402
import qzone_api as qzone_api_module  # noqa: E402
from media import QzoneMediaAnalyzer  # noqa: E402
from qzone_api import QzoneAPI  # noqa: E402


def test_media_download_is_cached_without_forwarding_qzone_cookie(monkeypatch, tmp_path: Path) -> None:
    requests = []
    original_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"image-bytes", headers={"Content-Type": "image/jpeg"})

    monkeypatch.setattr(
        qzone_api_module.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    api = QzoneAPI(
        {"uin": "01234567", "p_skey": "secret", "skey": "secret"},
        media_options={"cache_dir": tmp_path, "cache_media_locally": True},
    )

    payload, local_path = asyncio.run(
        api._download_media("https://a1.qpic.cn/example/photo.jpg?token=temporary", "image")
    )

    assert payload == b"image-bytes"
    assert local_path is not None and local_path.is_file()
    assert local_path.parent == tmp_path
    assert "Cookie" not in requests[0].headers
    assert requests[0].headers["referer"] == "https://user.qzone.qq.com/"


def test_media_download_rejects_untrusted_hosts_before_request(monkeypatch, tmp_path: Path) -> None:
    api = QzoneAPI({"uin": "01234567"}, media_options={"cache_dir": tmp_path})
    request_client = AsyncMock()
    monkeypatch.setattr(qzone_api_module.httpx, "AsyncClient", request_client)

    payload, local_path = asyncio.run(api._download_media("https://example.com/steal.jpg", "image"))

    assert payload is None
    assert local_path is None
    request_client.assert_not_called()


def test_process_feed_media_caches_video_and_returns_understanding(monkeypatch, tmp_path: Path) -> None:
    image_path = tmp_path / "image.jpg"
    video_path = tmp_path / "video.mp4"
    image_path.write_bytes(b"image")
    video_path.write_bytes(b"video")
    api = QzoneAPI(
        {"uin": "01234567"},
        media_options={
            "cache_dir": tmp_path,
            "cache_media_locally": True,
            "enable_image_understanding": True,
            "enable_video_understanding": True,
        },
    )

    async def fake_download(url, kind, *, force_cache=False):
        return (b"image-data", image_path) if kind == "image" else (b"video-data", video_path)

    class FakeAnalyzer:
        async def get_image_description(self, image_base64):
            return "动态配图描述"

        async def get_video_description(self, video, *, frame_count):
            assert video == str(video_path)
            assert frame_count == 4
            return "视频摘要"

    monkeypatch.setattr(api, "_download_media", fake_download)
    monkeypatch.setattr(qzone_api_module, "image_manager", FakeAnalyzer())

    images, videos, summaries, files = asyncio.run(
        api._process_feed_media(
            ["https://a1.qpic.cn/photo.jpg"],
            [{"url3": "https://video.qq.com/clip.mp4"}],
        )
    )

    assert images == ["动态配图描述"]
    assert videos == ["https://video.qq.com/clip.mp4"]
    assert summaries == ["视频摘要"]
    assert {item["type"] for item in files} == {"image", "video"}


def test_image_analyzer_sends_image_data_to_host_vlm() -> None:
    calls = []

    class FakeLLM:
        async def generate(self, prompt, **kwargs):
            calls.append((prompt, kwargs))
            return {"success": True, "response": "一只猫趴在窗边。"}

    png_base64 = base64.b64encode(b"\x89PNG\r\n\x1a\nrest").decode("ascii")
    analyzer = QzoneMediaAnalyzer(SimpleNamespace(llm=FakeLLM()), model_task="vlm")

    result = asyncio.run(analyzer.get_image_description(png_base64))

    assert result == "一只猫趴在窗边。"
    prompt, options = calls[0]
    assert options["task_name"] == "vlm"
    assert prompt[0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_video_analyzer_extracts_evenly_spaced_frames_and_summarizes(monkeypatch, tmp_path: Path) -> None:
    calls = []

    class FakeLLM:
        async def generate(self, prompt, **kwargs):
            calls.append((prompt, kwargs))
            return {"success": True, "response": "视频中人物先挥手，随后离开画面。"}

    analyzer = QzoneMediaAnalyzer(SimpleNamespace(llm=FakeLLM()), model_task="vlm")
    monkeypatch.setattr(media_module.shutil, "which", lambda name: f"/mock/bin/{name}")
    monkeypatch.setattr(
        analyzer,
        "_run_process",
        AsyncMock(side_effect=["2.0", b"frame-1", b"frame-2"]),
    )

    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")
    result = asyncio.run(analyzer.get_video_description(str(video_path), frame_count=2))

    assert result == "视频中人物先挥手，随后离开画面。"
    prompt, options = calls[0]
    assert options["task_name"] == "vlm"
    assert sum(part.get("type") == "image_url" for part in prompt[0]["content"]) == 2
    assert "0.5 秒" in prompt[0]["content"][1]["text"]
    assert "1.5 秒" in prompt[0]["content"][3]["text"]
