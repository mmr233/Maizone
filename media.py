"""QQ 空间图片与视频画面的多模态分析。"""

from __future__ import annotations

import asyncio
import base64
import shutil
from pathlib import Path
from typing import Any


def _image_mime(image_base64: str) -> str:
    try:
        header = base64.b64decode(image_base64[:96], validate=False)
    except Exception:
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"RIFF") and b"WEBP" in header[:16]:
        return "image/webp"
    return "image/jpeg"


class QzoneMediaAnalyzer:
    """通过 MaiBot LLM 能力把图片或抽帧画面交给配置的 VLM 任务。"""

    def __init__(self, context: Any, model_task: str = "vlm", ffmpeg_path: str = "ffmpeg"):
        self.context = context
        self.model_task = str(model_task or "vlm").strip() or "vlm"
        self.ffmpeg_path = str(ffmpeg_path or "ffmpeg").strip() or "ffmpeg"

    async def get_image_description(self, image_base64: str) -> str:
        prompt = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "简洁客观地描述这张 QQ 空间配图的可见内容，不要猜测画面外的信息。"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{_image_mime(image_base64)};base64,{image_base64}"},
                    },
                ],
            }
        ]
        return await self._generate(prompt, max_tokens=300)

    async def get_video_description(self, video_path: str, *, frame_count: int = 4) -> str:
        path = Path(video_path)
        if not path.is_file():
            raise FileNotFoundError(f"视频文件不存在：{path}")

        ffmpeg = shutil.which(self.ffmpeg_path) or self.ffmpeg_path
        ffprobe_candidate = Path(ffmpeg).with_name("ffprobe.exe" if ffmpeg.lower().endswith(".exe") else "ffprobe")
        ffprobe = str(ffprobe_candidate) if ffprobe_candidate.is_file() else shutil.which("ffprobe")
        if not ffprobe:
            raise RuntimeError("未找到 FFprobe；请安装 FFmpeg 并配置 PATH")

        duration_text = await self._run_process(
            [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            timeout_seconds=20,
        )
        try:
            duration = float(duration_text.strip())
        except ValueError as exc:
            raise RuntimeError("无法读取视频时长") from exc
        if duration <= 0:
            raise RuntimeError("视频时长无效")

        count = max(1, min(8, int(frame_count or 4)))
        timestamps = [min(duration * (index + 0.5) / count, max(0.0, duration - 0.04)) for index in range(count)]
        parts: list[dict[str, Any]] = [
            {"type": "text", "text": f"请根据下列按时间均匀抽取的视频画面，简洁概括视频内容和动作变化。视频时长约 {duration:.1f} 秒；不要猜测画面外信息。"}
        ]
        for timestamp in timestamps:
            frame = await self._run_process(
                [
                    ffmpeg,
                    "-hide_banner", "-loglevel", "error", "-nostdin", "-ss", f"{timestamp:.3f}",
                    "-i", str(path), "-frames:v", "1", "-vf", "scale=768:-2",
                    "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
                ],
                timeout_seconds=25,
                binary_output=True,
            )
            if not frame:
                continue
            parts.append({"type": "text", "text": f"画面时间：{timestamp:.1f} 秒"})
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/jpeg;base64," + base64.b64encode(frame).decode("ascii")
                    },
                }
            )
        if not any(part.get("type") == "image_url" for part in parts):
            raise RuntimeError("FFmpeg 没有抽取到可识别画面")
        return await self._generate([{"role": "user", "content": parts}], max_tokens=500)

    async def _generate(self, prompt: list[dict[str, Any]], *, max_tokens: int) -> str:
        result = await self.context.llm.generate(
            prompt,
            task_name=self.model_task,
            max_tokens=max_tokens,
        )
        if not isinstance(result, dict) or result.get("success") is False:
            raise RuntimeError(str((result or {}).get("error") or "多模态模型请求失败"))
        text = str(result.get("response") or "").strip()
        if not text:
            raise RuntimeError("多模态模型未返回描述")
        return text

    @staticmethod
    async def _run_process(
        args: list[str], *, timeout_seconds: int, binary_output: bool = False
    ) -> bytes | str:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise RuntimeError("FFmpeg 处理超时") from exc
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()[:300]
            raise RuntimeError(detail or f"FFmpeg 退出码 {process.returncode}")
        return stdout if binary_output else stdout.decode("utf-8", errors="replace")
