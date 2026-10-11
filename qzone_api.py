import base64
import hashlib
import json
import mimetypes
import os
import time
from typing import Any
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
# 额外依赖库
import json5
import bs4

cookie_path = str(Path(__file__).parent.resolve() / "cookies.json")
# ===== logger =====
class NoLogger:
    def info(self, msg):
        pass
    def warning(self, msg):
        pass
    def error(self, msg):
        pass
    def debug(self, msg):
        pass
logger = NoLogger()
def set_qzoneapi_logger(custom_logger):
    global logger
    logger = custom_logger

_media_runtime: dict[str, Any] = {}

def set_qzone_media_runtime(**options):
    """设置媒体分析与本地缓存选项，由插件加载时注入。"""
    global _media_runtime
    _media_runtime = dict(options)

# ===== Image Manager =====
class NoImageManager:
    async def get_image_description(self, image_base64: str) -> str:
        return "[图片]"
image_manager = NoImageManager()
def set_image_manager(image_manager_instance):
    """设置image_manager实例"""
    global image_manager
    image_manager = image_manager_instance
# ===== 辅助函数 =====
def generate_gtk(skey: str) -> str:
    """特定协议算法，生成QQ空间的gtk值"""
    hash_val = 5381
    for i in range(len(skey)):
        hash_val += (hash_val << 5) + ord(skey[i])
    return str(hash_val & 2147483647)


def get_picbo_and_richval(upload_result) -> tuple[str | None, str | None]:
    """从上传结果中提取图片的picbo和richval值用于发表图片说说"""
    if not isinstance(upload_result, dict) or 'ret' not in upload_result:
        logger.error("获取图片picbo和richval失败: 返回数据不合法")
        return None, None
    if upload_result.get('ret') != 0:
        logger.error(f"上传图片失败: {upload_result}")
        return None, None
    
    try:
        picbo = upload_result['data']['url'].split('&bo=')[1]
        richval = ",{},{},{},{},{},{},,{},{}".format(
            upload_result['data']['albumid'], upload_result['data']['lloc'],
            upload_result['data']['sloc'], upload_result['data']['type'],
            upload_result['data']['height'], upload_result['data']['width'],
            upload_result['data']['height'], upload_result['data']['width']
        )
        return picbo, richval
    except (KeyError, IndexError) as e:
        logger.error(f"提取picbo和richval失败: {e}")
        return None, None


def extract_code_html(html_content: str) -> Any | None:
    """从QQ空间响应的HTML内容中提取响应码code的值"""
    try:
        soup = bs4.BeautifulSoup(html_content, 'html.parser')
        script_tags = soup.find_all('script')
        for script in script_tags:
            if script.string and 'frameElement.callback' in script.string:
                script_content = script.string
                start_index = script_content.find('frameElement.callback(') + len('frameElement.callback(')
                end_index = script_content.rfind(');')
                if 0 < start_index < end_index:
                    json_str = script_content[start_index:end_index].strip()
                    if json_str.endswith(';'):
                        json_str = json_str[:-1]
                    data = json5.loads(json_str)
                    if isinstance(data, dict) and 'code' in data:
                        return data.get("code")
                    else:
                        continue
        return None
    except:
        return None


def extract_code_json(json_response) -> Any | None:
    """
    从QQ空间响应的json内容中提取code值，如果不存在则返回None
    """
    try:
        if isinstance(json_response, str):
            data = json.loads(json_response)
        else:
            data = json_response

        return data.get('code', None)
    except (json.JSONDecodeError, KeyError, AttributeError):
        return None


def image_to_base64(image: bytes) -> str:
    """将图片转换为base64字符串"""
    pic_base64 = base64.b64encode(image)
    return str(pic_base64)[2:-1]


class QzoneAPI:
    # QQ空间url常量
    UPLOAD_IMAGE_URL = "https://up.qzone.qq.com/cgi-bin/upload/cgi_upload_image"
    EMOTION_PUBLISH_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_publish_v6"
    DOLIKE_URL = "https://user.qzone.qq.com/proxy/domain/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app"
    COMMENT_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds"
    REPLY_URL = "https://h5.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds"
    LIST_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msglist_v6"
    ZONE_LIST_URL = "https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds3_html_more"

    def __init__(self, cookies_dict: dict | None = None, media_options: dict | None = None):
        self.cookies = dict(cookies_dict or {})
        options = dict(media_options or {})
        cache_dir = options.get("cache_dir")
        self.media_cache_dir = Path(cache_dir).expanduser() if cache_dir else None
        self.cache_media_locally = bool(options.get("cache_media_locally", False))
        self.enable_image_understanding = bool(options.get("enable_image_understanding", True))
        self.enable_video_understanding = bool(options.get("enable_video_understanding", False))
        self.media_cache_ttl_hours = max(1, min(720, int(options.get("media_cache_ttl_hours", 24) or 24)))
        self.image_max_size_mb = max(1, min(100, int(options.get("image_max_size_mb", 20) or 20)))
        self.video_max_size_mb = max(1, min(2048, int(options.get("video_max_size_mb", 64) or 64)))
        self.video_frame_count = max(1, min(8, int(options.get("video_frame_count", 4) or 4)))
        self.ffmpeg_path = str(options.get("ffmpeg_path", "ffmpeg") or "ffmpeg").strip()
        self._last_media_cleanup = 0.0
        self.uin = self.cookies.get("uin", "").lstrip("o0")   # uin 从cookies中提取，去除前导o和0
        if self.uin == "":
            logger.error("未找到uin，请检查cookies是否正确")
            return
        self.qq_nickname = ""
        self.gtk2 = ''

        if 'p_skey' in self.cookies:
            self.gtk2 = generate_gtk(self.cookies['p_skey'])

    @staticmethod
    def _normalize_media_url(url: str) -> str:
        try:
            value = str(url or "").strip()
            if value.startswith("//"):
                value = "https:" + value
            parsed = urlparse(value)
            host = (parsed.hostname or "").lower().rstrip(".")
            allowed_domains = ("qpic.cn", "qlogo.cn", "gtimg.cn", "qq.com")
            if not host or parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
                return ""
            port = parsed.port
            if port not in {None, 80, 443}:
                return ""
            if not any(host == domain or host.endswith("." + domain) for domain in allowed_domains):
                return ""
            netloc = host if port in {None, 80} else f"{host}:443"
            return parsed._replace(scheme="https", netloc=netloc).geturl()
        except (TypeError, ValueError):
            return ""

    @classmethod
    def _is_allowed_media_url(cls, url: str) -> bool:
        return bool(cls._normalize_media_url(url))

    def _cleanup_expired_media(self) -> None:
        if not self.media_cache_dir or time.time() - self._last_media_cleanup < 300:
            return
        self._last_media_cleanup = time.time()
        if not self.media_cache_dir.is_dir():
            return
        cutoff = time.time() - self.media_cache_ttl_hours * 3600
        try:
            for path in self.media_cache_dir.iterdir():
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(f"清理QQ空间媒体缓存失败: {exc}")

    def _media_cache_path(self, url: str, kind: str, content_type: str = "") -> Path | None:
        if not self.media_cache_dir:
            return None
        raw_suffix = Path(urlparse(url).path).suffix.lower()
        allowed = {".jpg", ".jpeg", ".png", ".webp", ".gif"} if kind == "image" else {".mp4", ".m4v", ".mov", ".webm"}
        suffix = raw_suffix if raw_suffix in allowed else mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if suffix not in allowed:
            suffix = ".jpg" if kind == "image" else ".mp4"
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        return self.media_cache_dir / f"{digest}{suffix}"

    async def _download_media(self, url: str, kind: str, *, force_cache: bool = False) -> tuple[bytes | None, Path | None]:
        normalized_url = self._normalize_media_url(url)
        if not normalized_url:
            try:
                host = urlparse(str(url or "").strip()).hostname or "未知域名"
            except ValueError:
                host = "未知域名"
            logger.warning(f"跳过非受信任的QQ空间媒体地址: {host}")
            return None, None

        cache_enabled = bool(self.media_cache_dir and (self.cache_media_locally or force_cache))
        if cache_enabled:
            self._cleanup_expired_media()
            cached_path = self._media_cache_path(normalized_url, kind)
            if cached_path and cached_path.is_file():
                try:
                    if time.time() - cached_path.stat().st_mtime <= self.media_cache_ttl_hours * 3600:
                        return cached_path.read_bytes(), cached_path
                    cached_path.unlink(missing_ok=True)
                except OSError:
                    pass
        else:
            cached_path = None

        max_size = (self.image_max_size_mb if kind == "image" else self.video_max_size_mb) * 1024 * 1024
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/139.0.0.0 Safari/537.36",
            "Referer": "https://user.qzone.qq.com/",
        }
        current_url = normalized_url
        timeout = httpx.Timeout(45.0, connect=10.0)
        temp_path: Path | None = None
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
                for _ in range(6):
                    current_url = self._normalize_media_url(current_url)
                    if not current_url:
                        raise RuntimeError("媒体重定向到非受信任域名，已阻止下载")
                    async with client.stream("GET", current_url, headers=headers) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("Location")
                            if not location:
                                raise RuntimeError("媒体重定向缺少 Location")
                            current_url = urljoin(current_url, location)
                            continue
                        response.raise_for_status()
                        content_type = str(response.headers.get("Content-Type", "") or "")
                        if content_type and not content_type.lower().startswith(("image/", "video/", "application/octet-stream")):
                            raise RuntimeError(f"媒体响应类型异常: {content_type.split(';', 1)[0]}")
                        content_length = int(response.headers.get("Content-Length", "0") or 0)
                        if content_length > max_size:
                            raise RuntimeError(f"媒体超过大小限制: {content_length / 1024 / 1024:.1f}MB")

                        if cache_enabled:
                            cached_path = self._media_cache_path(normalized_url, kind, content_type)
                            if not cached_path:
                                raise RuntimeError("未配置媒体缓存目录")
                            cached_path.parent.mkdir(parents=True, exist_ok=True)
                            temp_path = cached_path.with_name(f".{cached_path.name}.{os.getpid()}.{os.urandom(4).hex()}.part")
                            size = 0
                            with temp_path.open("wb") as file_obj:
                                async for chunk in response.aiter_bytes(65536):
                                    size += len(chunk)
                                    if size > max_size:
                                        raise RuntimeError(f"媒体超过大小限制: {size / 1024 / 1024:.1f}MB")
                                    file_obj.write(chunk)
                            if size == 0:
                                raise RuntimeError("媒体下载结果为空")
                            os.replace(temp_path, cached_path)
                            return cached_path.read_bytes(), cached_path

                        chunks = bytearray()
                        async for chunk in response.aiter_bytes(65536):
                            chunks.extend(chunk)
                            if len(chunks) > max_size:
                                raise RuntimeError(f"媒体超过大小限制: {len(chunks) / 1024 / 1024:.1f}MB")
                        return bytes(chunks), None
                raise RuntimeError("媒体重定向次数过多")
        except Exception as exc:
            if temp_path:
                temp_path.unlink(missing_ok=True)
            logger.warning("QQ空间%s下载失败: %s", "图片" if kind == "image" else "视频", exc)
            return None, None

    async def get_image_base64_by_url(self, url: str) -> str | None:
        """
            从指定的URL获取图片并将其转换为Base64编码格式，用于解析配图。

            Args:
                url (str): 图片的URL地址。

            Returns:
                str: 图片的Base64编码字符串，如果获取失败则返回None。
        """
        image_bytes, _ = await self._download_media(url, "image")
        if not image_bytes:
            return None
        return base64.b64encode(image_bytes).decode("utf-8")

    async def _process_feed_media(
        self,
        image_urls: list[str],
        video_items: list[dict[str, Any]],
    ) -> tuple[list[str], list[str], list[str], list[dict[str, str]]]:
        image_descriptions: list[str] = []
        video_urls: list[str] = []
        video_summaries: list[str] = []
        media_files: list[dict[str, str]] = []
        seen_images: set[str] = set()

        for image_url in image_urls:
            url = str(image_url or "").strip()
            if not url or url in seen_images:
                continue
            seen_images.add(url)
            image_bytes, local_path = await self._download_media(url, "image")
            if not image_bytes:
                continue
            if local_path:
                media_files.append({"type": "image", "path": str(local_path)})
            if self.enable_image_understanding:
                try:
                    encoded = base64.b64encode(image_bytes).decode("ascii")
                    description = await image_manager.get_image_description(encoded)
                    if description:
                        image_descriptions.append(str(description).strip())
                except Exception as exc:
                    logger.warning("读取QQ空间图片理解失败: %s", exc)

        seen_videos: set[str] = set()
        for video_item in video_items:
            if not isinstance(video_item, dict):
                continue
            video_url = str(video_item.get("url3") or video_item.get("video_url") or "").strip()
            if not video_url or video_url in seen_videos:
                continue
            seen_videos.add(video_url)
            video_urls.append(video_url)
            if not (self.cache_media_locally or self.enable_video_understanding):
                continue

            _, local_path = await self._download_media(
                video_url,
                "video",
                force_cache=self.enable_video_understanding,
            )
            if not local_path:
                continue
            media_files.append({"type": "video", "path": str(local_path)})
            if self.enable_video_understanding:
                describe_video = getattr(image_manager, "get_video_description", None)
                if not callable(describe_video):
                    logger.warning("当前媒体分析器不支持视频理解")
                    continue
                try:
                    summary = await describe_video(
                        str(local_path), frame_count=self.video_frame_count
                    )
                    if summary:
                        video_summaries.append(str(summary).strip())
                except Exception as exc:
                    logger.warning("读取QQ空间视频理解失败: %s", exc)

        return image_descriptions, video_urls, video_summaries, media_files

    async def upload_image(self, image: bytes) -> str | None:
        """
            上传图片到QQ空间。

            Args:
                image (bytes): 图片的二进制数据。

            Returns:
                str: 上传成功后返回的响应数据，如果上传失败则返回None。
        """
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            res = await client.request(
                method="POST",
                url=self.UPLOAD_IMAGE_URL,
                data={
                    "filename": "filename",
                    "zzpanelkey": "",
                    "uploadtype": "1",
                    "albumtype": "7",
                    "exttype": "0",
                    "skey": self.cookies["skey"],
                    "zzpaneluin": self.uin,
                    "p_uin": self.uin,
                    "uin": self.uin,
                    "p_skey": self.cookies['p_skey'],
                    "output_type": "json",
                    "qzonetoken": "",
                    "refer": "shuoshuo",
                    "charset": "utf-8",
                    "output_charset": "utf-8",
                    "upload_hd": "1",
                    "hd_width": "2048",
                    "hd_height": "10000",
                    "hd_quality": "96",
                    "backUrls": "http://upbak.photo.qzone.qq.com/cgi-bin/upload/cgi_upload_image,"
                                "http://119.147.64.75/cgi-bin/upload/cgi_upload_image",
                    "url": "https://up.qzone.qq.com/cgi-bin/upload/cgi_upload_image?g_tk=" + self.gtk2,
                    "base64": "1",
                    "picfile": image_to_base64(image),
                },
                headers={
                    'referer': 'https://user.qzone.qq.com/' + str(self.uin),
                    'origin': 'https://user.qzone.qq.com'
                },
                cookies=self.cookies
            )
        if res.status_code == 200:
            logger.debug(f"上传图片响应: {res.text}")
            try:
                return eval(res.text[res.text.find('{'):res.text.rfind('}') + 1])
            except Exception as e:
                logger.error(f"解析上传响应失败: {e}")
                return None
        else:
            logger.error(f"上传图片失败: 状态码 {res.status_code}")
            return None

    async def publish_emotion(self, content: str, images: list[bytes] = []) -> str | None:
        """
        将说说内容和图片上传到QQ空间。图片会先上传并生成对应的pic_bo和richval值，然后与文本内容一起提交。

        Args:
            content (str): 说说的文本内容。
            images (list[bytes], 可选): 图片的二进制数据列表，默认为空列表。

        Returns:
            str: 成功发送后返回的说说ID（tid），如果发送失败则返回None。
        """
        if images is None:
            images = []

        post_data = {
            "syn_tweet_verson": "1",
            "paramstr": "1",
            "who": "1",
            "con": content,
            "feedversion": "1",
            "ver": "1",
            "ugc_right": "1",
            "to_sign": "0",
            "hostuin": self.uin,
            "code_version": "1",
            "format": "json",
            "qzreferrer": "https://user.qzone.qq.com/" + str(self.uin)
        }

        if len(images) > 0:
            pic_bos = []
            richvals = []
            for img in images:
                upload_result = await self.upload_image(img)
                if upload_result:
                    picbo, richval = get_picbo_and_richval(upload_result)
                    if picbo and richval:
                        pic_bos.append(picbo)
                        richvals.append(richval)
            
            if pic_bos:
                post_data['pic_bo'] = ','.join(pic_bos)
                post_data['richtype'] = '1'
                post_data['richval'] = '\t'.join(richvals)

        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            res = await client.request(
                method="POST",
                url=self.EMOTION_PUBLISH_URL,
                params={
                    'g_tk': self.gtk2,
                    'uin': self.uin,
                },
                data=post_data,
                headers={
                    'referer': 'https://user.qzone.qq.com/' + str(self.uin),
                    'origin': 'https://user.qzone.qq.com'
                },
                cookies=self.cookies
            )
        if res.status_code == 200:
            if extract_code_json(res.text) != 0:
                logger.error(f"发表说说失败，响应内容: {res.text}")
                return None
            try:
                return res.json().get('tid')
            except Exception as e:
                logger.error(f"解析发表结果失败: {e}")
                return None
        else:
            logger.error(f"发表说说失败: 状态码 {res.status_code} 内容: {res.text}")
            return None

    async def like(self, fid: str, target_qq: str) -> bool:
        """
        点赞指定说说。

        Args:
            fid (str): 说说的动态ID。
            target_qq (str): 目标QQ号。

        Returns:
            bool: 如果点赞成功返回True，否则返回False。
        """
        uin = self.uin
        post_data = {
            'qzreferrer': f'https://user.qzone.qq.com/{uin}',  # 来源
            'opuin': uin,  # 操作者QQ
            'unikey': f'http://user.qzone.qq.com/{target_qq}/mood/{fid}',  # 动态唯一标识
            'curkey': f'http://user.qzone.qq.com/{target_qq}/mood/{fid}',  # 要操作的动态对象
            'appid': 311,  # 应用ID(说说:311)
            'from': 1,  # 来源
            'typeid': 0,  # 类型ID
            'abstime': int(time.time()),  # 当前时间戳
            'fid': fid,  # 动态ID
            'active': 0,  # 活动ID
            'format': 'json',  # 返回格式
            'fupdate': 1,  # 更新标记
        }
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            res = await client.request(
                method="POST",
                url=self.DOLIKE_URL,
                params={
                    'g_tk': self.gtk2,
                },
                data=post_data,
                headers={
                    'referer': 'https://user.qzone.qq.com/' + str(self.uin),
                    'origin': 'https://user.qzone.qq.com'
                },
                cookies=self.cookies
            )
        if res.status_code == 200:
            if extract_code_json(res.text) != 0:
                logger.error("点赞失败" + res.text)
                return False
            return True
        else:
            logger.error("点赞失败: " + res.text)
            return False

    async def comment(self, fid: str, target_qq: str, content: str) -> bool:
        """
        评论指定说说。

        Args:
            fid (str): 说说的动态ID。
            target_qq (str): 目标QQ号。
            content (str): 评论的文本内容。

        Returns:
            bool: 如果评论成功返回True，否则返回False。
        """
        uin = self.uin
        post_data = {
            "topicId": f'{target_qq}_{fid}__1',  # 说说ID
            "uin": uin,  # botQQ
            "hostUin": target_qq,  # 目标QQ
            "feedsType": 100,  # 说说类型
            "inCharset": "utf-8",  # 字符集
            "outCharset": "utf-8",  # 字符集
            "plat": "qzone",  # 平台
            "source": "ic",  # 来源
            "platformid": 52,  # 平台id
            "format": "fs",  # 返回格式
            "ref": "feeds",  # 引用
            "content": content,  # 评论内容
        }
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            res = await client.request(
                method="POST",
                url=self.COMMENT_URL,
                params={
                    "g_tk": self.gtk2,
                },
                data=post_data,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                    'referer': 'https://user.qzone.qq.com/' + str(self.uin),
                    'origin': 'https://user.qzone.qq.com'
                },
                cookies=self.cookies
            )
        if res.status_code == 200:
            if extract_code_html(res.text) != 0:
                logger.error("评论失败" + res.text)
                return False
            return True
        else:
            logger.error("评论失败: " + res.text)
            return False

    async def reply(
        self,
        fid: str,
        target_qq: str,
        target_nickname: str,
        target_comment_qq: str,
        content: str,
        comment_tid: str,
    ) -> bool:
        """
        回复指定评论。

        Args:
            fid (str): 说说的动态ID。
            target_qq (str): 目标QQ号。
            target_nickname (str): 目标QQ昵称。
            target_comment_qq (str): 被回复评论的发布者QQ。
            content (str): 回复的文本内容。
            comment_tid (str): 评论的唯一标识ID。

        Returns:
            bool: 如果回复成功返回True，否则返回False。
        """
        uin = self.uin
        if not target_comment_qq or not comment_tid:
            logger.error("回复失败：缺少评论者QQ或评论ID，无法定位真实评论")
            return False

        target_comment_qq = str(target_comment_qq)
        comment_tid = str(comment_tid)
        post_data = {
            "topicId": f"{target_qq}_{fid}__1",
            "uin": uin,
            "hostUin": target_qq,
            "feedsType": 100,
            "inCharset": "utf-8",
            "outCharset": "utf-8",
            "content": f"@{{uin:{target_comment_qq},nick:{target_nickname},auto:1}}{content}",
            "format": "fs",
            "plat": "qzone",
            "source": "ic",
            "platformid": 52,
            "ref": "feeds",
            "commentId": comment_tid,
            "commentUin": target_comment_qq,
            "richtype": "",
            "richval": "",
            "paramstr": "1",
        }
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            res = await client.request(
                method="POST",
                url=self.COMMENT_URL,
                params={
                    "g_tk": self.gtk2,
                },
                data=post_data,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
                    'referer': 'https://user.qzone.qq.com/' + str(self.uin),
                    'origin': 'https://user.qzone.qq.com'
                },
                cookies=self.cookies
            )
        if res.status_code == 200:
            if extract_code_html(res.text) != 0:
                logger.error("回复失败" + res.text)
                return False
            return True
        else:
            logger.error(f"回复失败，错误码: {res.status_code}")
            return False

    async def get_list(self, target_qq: str, num: int, filter: bool = True) -> list[dict[str, Any]]:
        """
        获取指定QQ号的好友说说列表

        Args:
            target_qq (str): 目标QQ号。
            num (int): 要获取的说说数量。
            filter (bool, optional): 是否过滤掉已评论说说。默认为True。

        Returns:
            list[dict[str, Any]]: 包含说说信息的字典列表，每条字典包含说说的ID（tid）、发布时间（created_time）、内容（content）、图片描述（images）、视频url（videos）及转发内容（rt_con）。
            若发生错误，则返回包含错误信息的字典列表。如[{'error': '错误信息'}]。
        """
        logger.info(f'即将获取 {target_qq} 的说说列表...num={num} filter={filter}')
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            res = await client.request(
                method="GET",
                url=self.LIST_URL,
                params={
                    'g_tk': self.gtk2,
                    "uin": target_qq,  # 目标QQ
                    "ftype": 0,  # 全部说说
                    "sort": 0,  # 最新在前
                    "pos": 0,  # 起始位置
                    "num": num,  # 获取条数
                    "replynum": 100,  # 评论数
                    "callback": "_preloadCallback",
                    "code_version": 1,
                    "format": "jsonp",
                    "need_comment": 1,
                    "need_private_comment": 1
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/91.0.4472.124 Safari/537.36",
                    "Referer": f"https://user.qzone.qq.com/{target_qq}",
                    "Host": "user.qzone.qq.com",
                    "Connection": "keep-alive"
                },
                cookies=self.cookies
            )

        if res.status_code != 200:
            logger.error("访问失败: " + str(res.status_code))
            return []

        data = res.text
        if data.startswith('_preloadCallback(') and data.endswith(');'):
            # 1. 去掉res首尾的 _preloadCallback( 和 );
            json_str = data[len('_preloadCallback('):-2]
        else:
            json_str = data

        try:
            # 2. 解析JSON数据
            json_data = json.loads(json_str)
            logger.debug(f"原始说说数据: {json_data}")
            uin_nickname = json_data.get('logininfo').get('name')
            self.qq_nickname = uin_nickname

            if json_data.get('code') != 0:
                return [{"error": json_data.get('message')}]
            # 3. 提取说说内容
            feeds_list = []
            msglist = json_data.get("msglist") or []
            if not msglist:
                logger.warning("msglist为空或None，返回空的说说列表")
            for msg in msglist:
                # 已评论过的说说不再阅读
                is_comment = False
                if 'commentlist' in msg:
                    commentlist = msg.get("commentlist")
                    if isinstance(commentlist, list):  # 确保一定是可迭代的列表
                        for comment in commentlist:
                            qq_nickname = comment.get("name")
                            if uin_nickname == qq_nickname and target_qq != str(self.uin) and filter:  # 已评论且不是自己的说说且过滤已评论说说
                                logger.info('已评论过此说说，即将跳过')
                                is_comment = True
                                break

                if not is_comment or not filter:
                    # 存储结果
                    timestamp = msg.get("created_time", "")
                    if timestamp:
                        time_tuple = time.localtime(timestamp)
                        # 格式化为字符串（年-月-日 时:分:秒）
                        created_time = time.strftime('%Y-%m-%d %H:%M:%S', time_tuple)
                    else:
                        created_time = msg.get("createTime", "unknown")
                    tid = msg.get("tid", "")
                    content = msg.get("content", "")
                    logger.info(f"正在阅读说说内容: {content[:20]}...")
                    image_urls = []
                    for pic in (msg.get("pic") or []):
                        if isinstance(pic, dict):
                            image_urls.append(pic.get("url1") or pic.get("pic_id") or pic.get("smallurl") or "")
                    video_items = [item for item in (msg.get("video") or []) if isinstance(item, dict)]
                    for video in video_items:
                        image_urls.append(video.get("url1") or video.get("pic_url") or "")
                    images, videos, video_summaries, media_files = await self._process_feed_media(
                        image_urls, video_items
                    )

                    # 提取转发内容
                    rt_con = ""
                    rt_data = msg.get("rt_con") or {}
                    if isinstance(rt_data, dict):
                        rt_con = rt_data.get("content", "")

                    # 提取评论
                    def _safe_int(value):
                        try:
                            return int(value)
                        except (TypeError, ValueError):
                            return None

                    comments = []
                    for comment in (msg.get("commentlist") or []):
                        comment_nickname = comment.get("name", "")
                        comment_content = comment.get("content", "")
                        comment_uin = comment.get("uin", "")
                        comment_tid_value = _safe_int(comment.get("tid"))
                        comment_time = comment.get("createTime", "") or comment.get("createTime2", "")

                        for sub_comment in (comment.get("list_3") or []):
                            sub_content = sub_comment.get("content", "")
                            sub_nickname = sub_comment.get("name", "")
                            sub_uin = sub_comment.get("uin", "")
                            sub_tid_value = _safe_int(sub_comment.get("tid"))
                            sub_time = sub_comment.get("createTime", "") or comment.get("createTime2", "")
                            sub_parent = comment_tid_value
                            comments.append(
                                {
                                    "content": sub_content,
                                    "qq_account": str(sub_uin),
                                    "nickname": sub_nickname,
                                    "comment_tid": sub_tid_value,
                                    "created_time": sub_time,
                                    "parent_tid": sub_parent,
                                }
                            )

                        comments.append(
                            {
                                "content": comment_content,
                                "qq_account": str(comment_uin),
                                "nickname": comment_nickname,
                                "comment_tid": comment_tid_value,
                                "created_time": comment_time,
                                "parent_tid": None,
                            }
                        )
                    # 存储信息
                    feeds_list.append({"target_qq": str(target_qq),
                                       "tid": str(tid),
                                       "created_time": created_time,
                                       "content": content,
                                       "images": images,
                                       "videos": videos,
                                       "video_summaries": video_summaries,
                                       "media_files": media_files,
                                       "rt_con": rt_con,
                                       "comments": comments})
            if len(feeds_list) == 0:
                return [{"error": '你已经看过最近的所有说说了，没有必要再看一遍'}]
            return feeds_list

        except Exception as e:
            logger.error(str(json_data))
            return [{"error": f'{e},你没有看到任何东西'}]

    async def get_qzone_list(self) -> list[dict[str, Any]]:
        """
        获取自己的QQ空间下，好友最新的几条说说，过滤自己的说说，不过滤已读说说
        Returns:
            list[dict[str, Any]]: 包含说说信息的字典列表，每条字典包含目标QQ号（target_qq）、说说ID(tid)、内容(content)、图片描述(images)、视频url(videos)、转发内容(rt_con)及评论内容(comments)。
        """
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            res = await client.request(
                method="GET",
                url=self.ZONE_LIST_URL,
                params={
                    "uin": self.uin,  # QQ号
                    "scope": 0,  # 访问范围
                    "view": 1,  # 查看权限
                    "filter": "all",  # 全部动态
                    "flag": 1,  # 标记
                    "applist": "all",  # 所有应用
                    "pagenum": 1,  # 页码
                    "aisortEndTime": 0,  # AI排序结束时间
                    "aisortOffset": 0,  # AI排序偏移
                    "aisortBeginTime": 0,  # AI排序开始时间
                    "begintime": 0,  # 开始时间
                    "format": "json",  # 返回格式
                    "g_tk": self.gtk2,  # 令牌
                    "useutf8": 1,  # 使用UTF8编码
                    "outputhtmlfeed": 1  # 输出HTML格式
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/91.0.4472.124 Safari/537.36",
                    "Referer": f"https://user.qzone.qq.com/{self.uin}",
                    "Host": "user.qzone.qq.com",
                    "Connection": "keep-alive"
                },
                cookies=self.cookies
            )

        if res.status_code != 200:
            logger.error("访问失败: " + str(res.status_code))
            return []

        data = res.text
        #logger.debug(f"原始说说数据:{data}")
        if data.startswith('_Callback(') and data.endswith(');'):
            # 1. 去掉res首尾的 _Callback( 和 );
            data = data[len('_Callback('):-2]
        data = data.replace('undefined', 'null')
        try:
            # 2. 解析JSON数据
            data_dict = json5.loads(data)
            if isinstance(data_dict, dict):
                data_json = data_dict.get('data', {}).get('data', [])
            else:
                logger.error("无效的JSON数据")
            #logger.debug(f"初解析原始说说数据: {data}")
        except Exception as e:
            logger.error(f"解析错误: {e}")
            # 3. 提取说说内容
        try:
            feeds_list = []
            for feed in data_json:
                if not feed:  # 跳过None值
                    continue
                # 过滤广告类内容（appid=311）
                appid = str(feed.get('appid', ''))
                if appid != '311':
                    continue
                target_qq = feed.get('uin', '')
                tid = feed.get('key', '')
                if not target_qq or not tid:
                    logger.error(f"无效的说说数据: target_qq={target_qq}, tid={tid}")
                    continue
                # print(feed)

                html_content = feed.get('html', '')
                if not html_content:
                    logger.error(f"说说内容为空: UIN={target_qq}, TID={tid}")
                    continue

                soup = bs4.BeautifulSoup(html_content, 'html.parser')

                # 解析说说时间 - 相对时间，如'昨天17:50'
                created_time = feed.get('feedstime', '').strip()

                # 提取文字内容
                text_div = soup.find('div', class_='f-info')
                text = text_div.get_text(strip=True) if text_div else ""
                # 提取转发内容
                rt_con = ""
                txt_box = soup.select_one('div.txt-box')
                if txt_box:
                    # 获取除昵称外的纯文本内容
                    rt_con = txt_box.get_text(strip=True)
                    # 分割掉昵称部分（从第一个冒号开始取内容）
                    if '：' in rt_con:
                        rt_con = rt_con.split('：', 1)[1].strip()
                # 提取图片URL
                image_urls = []
                # 查找所有图片容器
                img_box = soup.find('div', class_='img-box')
                if img_box:
                    for img in img_box.find_all('img'):
                        src = img.get('src')
                        if src and isinstance(src, str) and not src.startswith('http://qzonestyle.gtimg.cn'):  # 过滤表情图标
                            image_urls.append(src)
                # TODO 临时视频处理办法（视频缩略图）
                img_tag = soup.select_one('div.video-img img')
                if img_tag and 'src' in img_tag.attrs:
                    image_urls.append(img_tag['src'])
                # 去重URL
                unique_urls = list(set(image_urls))
                video_items = []
                video_div = soup.select_one('div.img-box.f-video-wrap.play')
                if video_div and 'url3' in video_div.attrs:
                    video_items.append({"url3": video_div['url3']})
                images, videos, video_summaries, media_files = await self._process_feed_media(
                    unique_urls, video_items
                )
                # 获取评论内容
                comments_list = []
                # 查找所有评论项（包括主评论和回复）
                comment_items = soup.select('li.comments-item.bor3')
                if comment_items:
                    for item in comment_items:
                        # 提取基本信息
                        qq_account = item.get('data-uin', '')
                        comment_tid = item.get('data-tid', '')
                        nickname = item.get('data-nick', '')

                        # 查找评论内容
                        content_div = item.select_one('div.comments-content')
                        if content_div:
                            # 移除操作按钮（回复/删除）
                            for op in content_div.select('div.comments-op'):
                                op.decompose()
                            # 获取纯文本内容
                            content = content_div.get_text(' ', strip=True)
                        else:
                            content = ""

                        # 提取评论时间（直接使用相对时间字符串）
                        comment_time_span = item.select_one('span.state')
                        comment_time = comment_time_span.get_text(strip=True) if comment_time_span else ""

                        # 检查是否是回复
                        parent_tid = None
                        parent_div = item.find_parent('div', class_='mod-comments-sub')
                        if parent_div:
                            parent_li = parent_div.find_parent('li', class_='comments-item')
                            if parent_li:
                                parent_tid = parent_li.get('data-tid')

                        comments_list.append({
                            'qq_account': str(qq_account),
                            'nickname': nickname,
                            'comment_tid': int(comment_tid) if isinstance(comment_tid, str) and comment_tid.isdigit() else 0,
                            'content': content,
                            "created_time": comment_time,  # 直接使用相对时间字符串
                            'parent_tid': int(parent_tid) if isinstance(parent_tid, str) and parent_tid.isdigit() else None
                        })

                feeds_list.append({
                    'target_qq': str(target_qq),
                    'tid': str(tid),
                    "created_time": created_time,  # 相对时间字符串
                    'content': text,
                    'images': images,
                    'videos': videos,
                    'video_summaries': video_summaries,
                    'media_files': media_files,
                    'rt_con': rt_con,
                    'comments': comments_list,
                })

            logger.info(f"成功解析 {len(feeds_list)} 条最新说说")
            # 获取自己说说下的完整评论内容
            feeds_list = [item for item in feeds_list if item.get('target_qq') != str(self.uin)]  # 去除其中自己的说说
            return feeds_list
        except Exception as e:
            logger.error(f'解析说说错误：{str(e)}')
            return []

    async def get_send_history(self, num: int) -> str:
        """
        构建说说发送历史prompt。
        Args:
            num (int): 要获取的说说数量。
        Returns:
            str: 最近发过的说说内容。
        Raises:
            Exception: 如果请求失败或响应状态码不是200，将抛出异常。
        """
        feeds_list = await self.get_list(target_qq=str(self.uin), num=num)
        history = "==================="
        for feed in feeds_list:
            if not feed.get("rt_con", ""):
                history += f"""
时间：'{feed.get("created_time", "")}'。
说说内容：'{feed.get("content", "")}'
图片：'{feed.get("images", [])}'
===================
"""
            else:
                history += f"""
时间: '{feed.get("created_time", "")}'。
转发了一条说说，内容为: '{feed.get("rt_con", "")}'
图片: '{feed.get("images", [])}'
对该说说的评论为: '{feed.get("content", "")}'
===================
"""
        return history


def create_qzone_api() -> QzoneAPI | None:
    """
    使用存在的cookie文件创建QzoneAPI实例并返回。

    Returns:
        QzoneAPI | None: 如果成功加载cookie并创建QzoneAPI实例，则返回实例；否则返回None。

    说明:
        该函数尝试从指定路径加载与QQ账号关联的cookie文件。如果文件存在且加载成功，
        则使用加载的cookie创建并返回一个QzoneAPI实例；如果文件不存在或加载失败，
        则记录错误日志并返回None。
    """
    cookie_file = cookie_path
    if os.path.exists(cookie_file):
        try:
            with open(cookie_file, 'r') as f:
                cookies = json.load(f)
        except Exception as e:
            logger.error(f"读取 cookie 文件失败: {cookie_file}，错误: {e}")
            cookies = None
    else:
        logger.error(f"cookie 文件不存在: {cookie_file}")
        cookies = None

    if cookies:
        qzone = QzoneAPI(cookies, media_options=_media_runtime)
        return qzone
    else:
        return None
