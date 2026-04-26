"""
Shared platform registry for AVOI Agent.

Single source of truth for platform metadata consumed by both
skills_config (label display) and tools_config (default toolset
resolution).  Import ``PLATFORMS`` from here instead of maintaining
duplicate dicts in each module.
"""

from collections import OrderedDict
from typing import NamedTuple


class PlatformInfo(NamedTuple):
    """Metadata for a single platform entry."""
    label: str
    default_toolset: str


# Ordered so that TUI menus are deterministic.
PLATFORMS: OrderedDict[str, PlatformInfo] = OrderedDict([
    ("cli",            PlatformInfo(label="🖥️  CLI",            default_toolset="avoi-cli")),
    ("telegram",       PlatformInfo(label="📱 Telegram",        default_toolset="avoi-telegram")),
    ("discord",        PlatformInfo(label="💬 Discord",         default_toolset="avoi-discord")),
    ("slack",          PlatformInfo(label="💼 Slack",           default_toolset="avoi-slack")),
    ("whatsapp",       PlatformInfo(label="📱 WhatsApp",        default_toolset="avoi-whatsapp")),
    ("signal",         PlatformInfo(label="📡 Signal",          default_toolset="avoi-signal")),
    ("bluebubbles",    PlatformInfo(label="💙 BlueBubbles",     default_toolset="avoi-bluebubbles")),
    ("email",          PlatformInfo(label="📧 Email",           default_toolset="avoi-email")),
    ("homeassistant",  PlatformInfo(label="🏠 Home Assistant",  default_toolset="avoi-homeassistant")),
    ("mattermost",     PlatformInfo(label="💬 Mattermost",      default_toolset="avoi-mattermost")),
    ("matrix",         PlatformInfo(label="💬 Matrix",          default_toolset="avoi-matrix")),
    ("dingtalk",       PlatformInfo(label="💬 DingTalk",        default_toolset="avoi-dingtalk")),
    ("feishu",         PlatformInfo(label="🪽 Feishu",          default_toolset="avoi-feishu")),
    ("wecom",          PlatformInfo(label="💬 WeCom",           default_toolset="avoi-wecom")),
    ("wecom_callback", PlatformInfo(label="💬 WeCom Callback",  default_toolset="avoi-wecom-callback")),
    ("weixin",         PlatformInfo(label="💬 Weixin",          default_toolset="avoi-weixin")),
    ("qqbot",          PlatformInfo(label="💬 QQBot",           default_toolset="avoi-qqbot")),
    ("webhook",        PlatformInfo(label="🔗 Webhook",         default_toolset="avoi-webhook")),
    ("api_server",     PlatformInfo(label="🌐 API Server",      default_toolset="avoi-api-server")),
    ("cron",           PlatformInfo(label="⏰ Cron",            default_toolset="avoi-cron")),
])


def platform_label(key: str, default: str = "") -> str:
    """Return the display label for a platform key, or *default*."""
    info = PLATFORMS.get(key)
    return info.label if info is not None else default
