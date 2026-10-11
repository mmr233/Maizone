from maibot_sdk import Field, PluginConfigBase
from pathlib import Path
from typing import Literal

config_file_path = Path(__file__).parent / "config.toml"


class PluginSectionConfig(PluginConfigBase):
    """插件基础配置。"""

    __ui_label__ = "基础配置"
    __ui_i18n__ = {"zh_CN": {"title": "基础配置"}}
    __ui_order__ = 0

    enabled: bool = Field(default=True, description="是否启用插件")
    config_version: float = Field(default=1.0, description="配置版本")
    text_model: str = Field(
        default="replyer",
        description="[默认即可]使用的文本模型在主程序的任务名（'replyer','planner','embedding', 'emoji', 'learner', 'memory', 'utils', 'vlm', 'voice'）"
    )
    media_model: str = Field(
        default="vlm",
        description="读取空间图片和视频画面时使用的多模态模型任务，通常为 vlm",
    )
    # 获取cookie相关配置
    http_host: str = Field(default="127.0.0.1", description="备用Napcat HTTP服务地址")
    http_port: int = Field(default=9999, description="备用Napcat HTTP服务端口")
    napcat_token: str = Field(default="", description="备用Napcat HTTP服务Token")
    cookie_methods: list[str] = Field(
        default=["adapter", "napcat", "qrcode", "local"],
        description="Cookie获取方式（顺序尝试）"
    )


class SendConfig(PluginConfigBase):
    """指令发说说配置"""

    __ui_label__ = "发说说"
    __ui_i18n__ = {"zh_CN": {"title": "发说说"}}
    __ui_order__ = 1

    # === 原有配置 ===
    history_number: int = Field(
        default=5,
        description="生成新说说时回顾的历史说说数量"
    )
    # 配图相关配置
    enable_image: bool = Field(
        default=True,
        description="是否附带表情包"
    )
    # 图片模式
    image_mode: Literal["only_emoji", "only_ai", "random"] = Field(
        default="only_emoji",
        description="图片使用方式（only_emoji: 仅表情包, only_ai: 仅AI生成, random: 随机混合）",
        json_schema_extra={
            "enum": ["only_emoji", "only_ai", "random"],
            "enum_titles": ["仅表情包", "仅AI生成", "随机混合"]
        }
    )
    ai_probability: float = Field(
        default=0.5,
        description="random模式下使用ai生图概率"
    )
    image_number: int = Field(
        default=1,
        description="每条说说附带图片数量"
    )
    # 提示词相关配置
    prompt: str = Field(
        default="你是'{bot_personality}'，现在是'{current_time}'你想写一条主题是'{topic}'的说说发表在qq空间上，"
                "{bot_expression}，不要刻意突出自身学科背景，不要浮夸，不要夸张修辞，可以适当使用颜文字，只输出一条说说正文的内容，不要输出多余内容"
                "(包括前后缀，冒号和引号，括号()，表情包，at或 @等 )",
        description="生成说说的提示词，占位符包括{current_time}（当前时间），{bot_personality}（人格），{topic}（说说主题），{bot_expression}（表达方式）"
    )

    # === 新增：聊天记忆配置 ===
    enable_chat_memory: bool = Field(
        default=True,
        description="是否读取今日聊天记录作为说说素材"
    )

    filter_mode: Literal["all", "whitelist", "blacklist"] = Field(
        default="all",
        description="聊天记录过滤模式（all: 全部会话, whitelist: 白名单（仅以下会话）, blacklist: 黑名单（排除以下会话））",
        json_schema_extra={
            "enum": ["all", "whitelist", "blacklist"],
            "enum_titles": ["全部会话", "白名单（仅以下会话）", "黑名单（排除以下会话）"]
        }
    )
    target_chats: list[str] = Field(
        default=[],
        description="目标会话列表，格式: group:123456 或 private:789012"
    )

    time_range: Literal["today", "last_n_hours"] = Field(
        default="today",
        description="时间范围（today: 今天00:00到现在, last_n_hours: 最近N小时）",
        json_schema_extra={
            "enum": ["today", "last_n_hours"],
            "enum_titles": ["今天00:00到现在", "最近N小时"]
        }
    )
    last_hours: int = Field(
        default=6,
        description="当time_range=last_n_hours时的小时数"
    )

    min_messages: int = Field(
        default=5,
        description="聊天记录最少条数，低于此值视为今日平淡，不使用素材"
    )
    max_messages: int = Field(
        default=50,
        description="最大聊天记录条数，超出则截断（仅在mode=direct时生效）"
    )
    per_message_max_chars: int = Field(
        default=200,
        description="单条消息最大字符数，超出截断为'<前缀>...'，0表示不截断"
    )

    chat_memory_mode: Literal["direct", "summary", "hybrid"] = Field(
        default="hybrid",
        description="聊天记录处理模式（direct: 直接截断取最近N条, summary: LLM精简摘要, hybrid: 混合: 最近N条+更早摘要）",
        json_schema_extra={
            "enum": ["direct", "summary", "hybrid"],
            "enum_titles": ["直接截断取最近N条", "LLM精简摘要", "混合:最近N条+更早摘要"]
        }
    )
    summary_model: str = Field(
        default="replyer",
        description="summary/hybrid模式下用于精简摘要的文本模型"
    )
    summary_prompt: str = Field(
        default="请用简洁的语言概括以下聊天记录的核心内容，提取今天发生的主要事件和话题，不超过200字：\n{chat_logs}",
        description="summary/hybrid模式下精简摘要的提示词，占位符{chat_logs}为聊天记录原文"
    )
    hybrid_recent_count: int = Field(
        default=10,
        description="hybrid模式下保留的最近消息条数"
    )

    fallback_prompt: str = Field(
        default="今天比较平淡，没有太多特别的对话，你可以根据主题自由发挥。",
        description="聊天记录不足时的占位提示语"
    )


class ReadConfig(PluginConfigBase):
    """指令读说说配置"""

    __ui_label__ = "读说说"
    __ui_i18n__ = {"zh_CN": {"title": "读说说"}}
    __ui_order__ = 2

    # 其它配置
    read_number: int = Field(default=5, description="读取的说说数量")
    like_probability: float = Field(default=1.0, description="读每条说说后点赞的概率")
    comment_probability: float = Field(default=1.0, description="读每条说说后评论的概率")
    allow_skip_comment: bool = Field(
        default=True,
        description="读别人空间时是否允许模型选择不评论（输出「不回复」则跳过）",
    )
    enable_image_understanding: bool = Field(
        default=True,
        description="读取动态时使用多模态模型识别配图",
    )
    cache_media_locally: bool = Field(
        default=False,
        description="将读取的图片和启用理解的视频下载到插件数据目录，便于理解和排查",
    )
    media_cache_ttl_hours: int = Field(
        default=24,
        description="本地动态媒体缓存保留小时数，过期文件会在下次读取时清理",
    )
    image_max_size_mb: int = Field(
        default=20,
        description="允许下载的单张空间图片最大体积（MB）",
    )
    enable_video_understanding: bool = Field(
        default=False,
        description="下载空间视频并抽帧交给多模态模型理解；需要系统安装 FFmpeg",
    )
    video_max_size_mb: int = Field(
        default=64,
        description="允许下载并理解的单个空间视频最大体积（MB）",
    )
    video_frame_count: int = Field(
        default=4,
        description="视频理解时均匀抽取的画面数量（1-8）",
    )
    ffmpeg_path: str = Field(
        default="ffmpeg",
        description="FFmpeg 可执行文件路径；已加入 PATH 时保持默认值",
    )
    # 提示词相关配置
    prompt: str = Field(default="你是'{bot_personality}'，你正在浏览你好友'{target_name}'的QQ空间，你看到了你的好友'{target_name}'"
                                "在qq空间上在'{created_time}'发了一条内容是'{content}'的说说，现在是'{current_time}'"
                                "你对'{target_name}'的印象是'{impression}'，若与你的印象点相关，可以适当评论相关内容，无关则忽略此印象，"
                                "{bot_expression}，回复的平淡一些，简短一些，说中文，不要刻意突出自身学科背景，不要浮夸，不要夸张修辞，不要输出多余内容"
                                "(包括前后缀，冒号和引号，括号()，表情包，at或 @等 )。若没必要评论只输出不回复，否则只输出评论正文", 
                        description="对无转发内容说说进行评论的提示词，占位符包括{current_time}（当前时间），{bot_personality}（人格），"
                                    "{target_name}（说说主人名称），{created_time}（说说发布时间），"
                                    "{content}（说说内容），{impression}（对说说主人的印象点），{bot_expression}（表达方式）"
                    )
    rt_prompt: str =  Field(default="你是'{bot_personality}'，你正在浏览你好友'{target_name}'的QQ空间，你看到了你的好友'{target_name}'"
                                    "在qq空间上在'{created_time}'转发了一条内容为'{rt_con}'的说说，你的好友的评论为'{content}'，你对'{"
                                    "target_name}'的印象是'{impression}'，若与你的印象点相关，可以适当评论相关内容，无关则忽略此印象，"
                                    "现在是'{current_time}'，{bot_expression}，"
                                    "回复的平淡一些，简短一些，说中文，不要刻意突出自身学科背景，不要浮夸，不要夸张修辞，"
                                    "不要输出多余内容(包括前后缀，冒号和引号，括号()，表情包，at或 @等 )。若没必要评论只输出不回复，否则只输出评论正文",
                            description="对转发的说说进行评论的提示词，占位符包括{current_time}（当前时间），{bot_personality}（人格），{"
                                        "target_name}（说说主人名称），{created_time}（说说发布时间），{"
                                        "content}（说说评论内容），{rt_con}（转发说说内容），{impression}（对说说主人的印象点），{"
                                        "bot_expression}（表达方式）")

class AutoSendConfig(PluginConfigBase):
    """自动发说说配置"""

    __ui_label__ = "自动发说说"
    __ui_i18n__ = {"zh_CN": {"title": "自动发说说"}}
    __ui_order__ = 3

    enable_auto_send: bool = Field(
        default=False,
        description="是否自动发说说"
    )
    daily_probability: float = Field(
        default=0.3,
        description="每天发说说的概率"
    )
    schedule: list[str] = Field(
        default=["08:00", "20:00"],
        description="每天发说说的时间点（24小时制，格式\"HH:MM\"，多个时间点用逗号分隔，如\"08:00,20:00\"）"
    )
    fluctuation: int = Field(
        default=60,
        description="发说说时间的随机浮动范围（分钟）"
    )
    random_topic: bool = Field(
        default=True,
        description="是否随机选择说说主题，若关闭则随机使用固定主题"
    )
    fixed_topic: list[str] = Field(
        default=["散文鉴赏", "今天也要加油", "日常碎片", "哲学小谈", "今天吃什么", "看书打卡", "想不到发什么了", "运动健身", "打游戏", "丧文化", "灵感碎片"],
        description="固定说说主题列表"
    )


class AutoReadConfig(PluginConfigBase):
    """自动读说说配置"""

    __ui_label__ = "自动读说说"
    __ui_i18n__ = {"zh_CN": {"title": "自动读说说"}}
    __ui_order__ = 4

    # 自动阅读
    enable_auto_read: bool = Field(
        default=True,
        description="是否自动读说说"
    )
    interval: int = Field(
        default=15,
        description="自动读说说的间隔时间（分钟）"
    )
    silent_duration: str = Field(
        default="22:00-07:00",
        description="不刷空间的时间段（24小时制，格式\"HH:MM-HH:MM\"，多个时间段用逗号分隔，如\"23:00-07:00,12:00-14:00\"）"
    )


class AutoReplyConfig(PluginConfigBase):
    """自动回复评论配置"""

    __ui_label__ = "自动回评论"
    __ui_i18n__ = {"zh_CN": {"title": "自动回评论"}}
    __ui_order__ = 5

    # 自动回复
    enable_auto_reply: bool = Field(
        default=True,
        description="是否在自动读说说时回复自己说说的评论"
    )
    reply_number: int = Field(
        default=5,
        description="自动回复的最新说说数量"
    )
    reply_probability: float = Field(
        default=1.0,
        description="对每条评论的回复概率"
    )
    # 提示词相关配置
    prompt: str = Field(
        default="你是'{bot_personality}'，你的好友'{nickname}'在'{created_time}'评论了你QQ空间上的一条内容为"
                "'{content}'的说说，你的好友对该说说的评论为:'{comment_content}'，"
                "现在是'{current_time}'，你想要对此评论进行回复，你对该好友的印象是:"
                "'{impression}'，若与你的印象点相关，可以适当回复相关内容，无关则忽略此印象，"
                "{bot_expression}，回复的平淡一些，简短一些，说中文，不要刻意突出自身学科背景，不要浮夸，不要夸张修辞，"
                "不要输出多余内容(包括前后缀，冒号和引号，括号()，表情包，at或 @等 )。只输出回复内容",
        description="自动回复评论的提示词，占位符包括{current_time}（当前时间），{bot_personality}（人格），{"
                    "nickname}（评论者昵称），{created_time}（评论时间），{"
                    "content}（说说内容），{comment_content}（评论内容），{impression}（对评论者的印象点），{"
                    "bot_expression}（表达方式）"
    )


class ImageGenerateConfig(PluginConfigBase):
    """图片生成配置"""

    __ui_label__ = "图片生成配置"
    __ui_i18n__ = {"zh_CN": {"title": "图片生成配置"}}
    __ui_order__ = 6

    # AI生图相关配置
    base_url: str = Field(
        default="https://ark.cn-beijing.volces.com/api/v3",
        description="AI生图服务地址"
    )
    model: str = Field(
        default="doubao-seedream-5-0-260128",
        description="AI生图使用的模型"
    )
    api_key: str = Field(
        default="your_api_key",
        description="AI生图服务API Key"
    )
    enable_reference: bool = Field(
        default=False,
        description="AI生图是否启用参考图功能（需图生图模型）"
    )
    reference: str = Field(
        default="",
        description="AI生图参考图URL或本地路径，启用参考图功能时使用"
    )
    prompt: str = Field(
        default="请根据以下QQ空间说说内容配图，并构建生成配图的风格和prompt。说说主人信息：'{personality}'。说说内容:'{"
                "message}'。请注意：仅回复用于生成图片的prompt，不要输出多余内容(包括前后缀，冒号和引号，括号()，表情包，at或 @等 )",
        description="AI生图提示词，占位符包括{personality}（说说主人信息），{message}（说说内容）"
    )
    ref_prompt: str = Field(
        default="说说主人的人设参考图片将随同提示词一起发送给生图AI，可使用'以参考图片风格'或'根据图中人物'等描述引导生成风格",
        description="启用参考图时的附加提示词"
    )


class AuthorityConfig(PluginConfigBase):
    """权限配置。"""

    __ui_label__ = "权限配置"
    __ui_i18n__ = {"zh_CN": {"title": "权限配置"}}
    __ui_order__ = 7

    # 发说说指令权限
    send_authority_type: Literal["blacklist", "whitelist"] = Field(
        default="blacklist",
        description="发说说指令权限控制方式（blacklist: 黑名单, whitelist: 白名单）",
        json_schema_extra={
            "enum": ["blacklist", "whitelist"],
            "enum_titles": ["黑名单（禁止以下QQ使用）", "白名单（仅允许以下QQ使用）"]
        }
    )
    send_whitelist: list[str] = Field(
        default=["123456", "350234"],
        description="允许使用发说说指令的QQ号白名单"
    )
    send_blacklist: list[str] = Field(
        default=["123456", "350234"],
        description="禁止使用发说说指令的QQ号黑名单"
    )
    # 读说说指令权限
    read_authority_type: Literal["blacklist", "whitelist"] = Field(
        default="blacklist",
        description="读说说指令权限控制方式",
        json_schema_extra={
            "enum": ["blacklist", "whitelist"],
            "enum_titles": ["黑名单（禁止以下QQ使用）", "白名单（仅允许以下QQ使用）"]
        }
    )
    read_whitelist: list[str] = Field(
        default=["123456", "350234"],
        description="允许使用读说说指令的QQ号白名单"
    )
    read_blacklist: list[str] = Field(
        default=["123456", "350234"],
        description="禁止使用读说说指令的QQ号黑名单"
    )
    # 自动读说说任务权限
    auto_read_authority_type: Literal["blacklist", "whitelist"] = Field(
        default="blacklist",
        description="自动读说说任务权限控制方式",
        json_schema_extra={
            "enum": ["blacklist", "whitelist"],
            "enum_titles": ["黑名单（禁止自动阅读以下QQ）", "白名单（仅自动阅读以下QQ）"]
        }
    )
    auto_read_whitelist: list[str] = Field(
        default=[],
        description="自动读说说任务的QQ号白名单"
    )
    auto_read_blacklist: list[str] = Field(
        default=["123456", "350234"],
        description="自动读说说任务的QQ号黑名单"
    )


class MaizonePluginConfig(PluginConfigBase):
    """插件总配置。"""
    plugin: PluginSectionConfig = Field(
        default_factory=PluginSectionConfig,
        description="插件基础配置"
    )
    send: SendConfig = Field(
        default_factory=SendConfig,
        description="指令发说说配置"
    )
    read: ReadConfig = Field(
        default_factory=ReadConfig,
        description="指令读说说配置"
    )
    auto_send: AutoSendConfig = Field(
        default_factory=AutoSendConfig,
        description="自动发说说配置"
    )
    auto_read: AutoReadConfig = Field(
        default_factory=AutoReadConfig,
        description="自动读说说配置"
    )
    auto_reply: AutoReplyConfig = Field(
        default_factory=AutoReplyConfig,
        description="自动回评论配置"
    )
    image: ImageGenerateConfig = Field(
        default_factory=ImageGenerateConfig,
        description="AI生图配置"
    )
    authority: AuthorityConfig = Field(
        default_factory=AuthorityConfig,
        description="权限配置"
    )


def _apply_zh_cn_field_schema(config_class: type[PluginConfigBase], labels: dict[str, str]) -> None:
    """为现有配置字段补充 WebUI 简体中文标签与提示。"""

    for field_name, label in labels.items():
        field_info = config_class.model_fields[field_name]
        extra = dict(field_info.json_schema_extra or {})
        hint = str(field_info.description or "").strip()
        extra.update(
            label=label,
            hint=hint,
            i18n={"zh_CN": {"label": label, "hint": hint}},
        )
        field_info.json_schema_extra = extra


_apply_zh_cn_field_schema(
    PluginSectionConfig,
    {
        "enabled": "启用插件",
        "config_version": "配置版本",
        "text_model": "文本模型任务",
        "media_model": "多模态理解模型任务",
        "http_host": "NapCat HTTP 地址",
        "http_port": "NapCat HTTP 端口",
        "napcat_token": "NapCat HTTP Token",
        "cookie_methods": "Cookie 获取方式",
    },
)
_apply_zh_cn_field_schema(
    SendConfig,
    {
        "history_number": "历史说说数量",
        "enable_image": "发布时附带图片",
        "image_mode": "图片来源模式",
        "ai_probability": "AI 配图概率",
        "image_number": "配图数量",
        "prompt": "发说说提示词",
        "enable_chat_memory": "使用今日聊天素材",
        "filter_mode": "聊天记录过滤模式",
        "target_chats": "目标会话列表",
        "time_range": "聊天记录时间范围",
        "last_hours": "最近小时数",
        "min_messages": "最少消息数",
        "max_messages": "最多消息数",
        "per_message_max_chars": "单条消息最大字符数",
        "chat_memory_mode": "聊天记录处理模式",
        "summary_model": "聊天摘要模型任务",
        "summary_prompt": "聊天摘要提示词",
        "hybrid_recent_count": "混合模式保留消息数",
        "fallback_prompt": "聊天素材不足时的提示词",
    },
)
_apply_zh_cn_field_schema(
    ReadConfig,
    {
        "read_number": "读取说说数量",
        "like_probability": "点赞概率",
        "comment_probability": "评论概率",
        "allow_skip_comment": "允许跳过评论",
        "enable_image_understanding": "识别动态图片",
        "cache_media_locally": "缓存动态媒体到本地",
        "media_cache_ttl_hours": "媒体缓存保留小时数",
        "image_max_size_mb": "图片最大体积（MB）",
        "enable_video_understanding": "理解动态视频",
        "video_max_size_mb": "视频最大体积（MB）",
        "video_frame_count": "视频抽帧数量",
        "ffmpeg_path": "FFmpeg 路径",
        "prompt": "普通说说评论提示词",
        "rt_prompt": "转发说说评论提示词",
    },
)
_apply_zh_cn_field_schema(
    AutoSendConfig,
    {
        "enable_auto_send": "启用定时发说说",
        "daily_probability": "每日发送概率",
        "schedule": "每日发送时间",
        "fluctuation": "发送时间浮动分钟数",
        "random_topic": "随机生成主题",
        "fixed_topic": "固定主题列表",
    },
)
_apply_zh_cn_field_schema(
    AutoReadConfig,
    {
        "enable_auto_read": "启用定时读说说",
        "interval": "读取间隔分钟数",
        "silent_duration": "静默时间段",
    },
)
_apply_zh_cn_field_schema(
    AutoReplyConfig,
    {
        "enable_auto_reply": "启用自动回复评论",
        "reply_number": "检查说说数量",
        "reply_probability": "评论回复概率",
        "prompt": "评论回复提示词",
    },
)
_apply_zh_cn_field_schema(
    ImageGenerateConfig,
    {
        "base_url": "图片生成 API 地址",
        "model": "图片生成模型",
        "api_key": "图片生成 API Key",
        "enable_reference": "启用参考图",
        "reference": "参考图片地址或路径",
        "prompt": "图片生成提示词",
        "ref_prompt": "参考图附加提示词",
    },
)
_apply_zh_cn_field_schema(
    AuthorityConfig,
    {
        "send_authority_type": "发说说权限模式",
        "send_whitelist": "发说说白名单",
        "send_blacklist": "发说说黑名单",
        "read_authority_type": "读说说权限模式",
        "read_whitelist": "读说说白名单",
        "read_blacklist": "读说说黑名单",
        "auto_read_authority_type": "自动阅读权限模式",
        "auto_read_whitelist": "自动阅读白名单",
        "auto_read_blacklist": "自动阅读黑名单",
    },
)
