"""
统一配置管理 — 多层覆盖，遵循行业最佳工程实践。

优先级（由低到高）：
    1. 代码默认值（硬编码 fallback）
    2. .env 文件（load_dotenv 加载到 os.environ）
    3. 环境变量（os.environ 显式覆盖）
    4. CLI 参数（main.py 中运行时覆盖）

分角色模型配置：
    {ROLE}_MODEL_NAME > MODEL_NAME > 默认值 "deepseek-chat"
    {ROLE}_API_KEY   > API_KEY   > 默认值 ""
    {ROLE}_API_BASE  > API_BASE  > 默认值 "https://api.deepseek.com/v1"

用法：
    from .config import get_config

    cfg = get_config()
    # 全局模型
    client = OpenAIChatCompletionClient(**cfg.model.to_client_kwargs())
    # 分角色模型
    mc = cfg.role_model("PM")
    client = OpenAIChatCompletionClient(**mc.to_client_kwargs())
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelConfig:
    """单个模型的配置。"""

    api_key: str = ""
    api_base: str = "https://api.deepseek.com/v1"
    model_name: str = "deepseek-chat"

    def to_client_kwargs(self) -> dict:
        """转为 OpenAIChatCompletionClient 构造参数。"""
        return {
            "model": self.model_name,
            "api_key": self.api_key,
            "base_url": self.api_base,
        }


@dataclass
class AppConfig:
    """应用全局配置，多层覆盖加载。"""

    # ── 全局模型 ──────────────────────────────────
    model: ModelConfig = field(default_factory=ModelConfig)

    # ── 选择器模型 ────────────────────────────────
    selector_model: ModelConfig = field(default_factory=ModelConfig)

    # ── 运行参数 ──────────────────────────────────
    workspace: str = "./ims-output"
    max_turns: int = 100

    # ── 加载 ──────────────────────────────────────

    @classmethod
    def from_env(cls) -> "AppConfig":
        """从环境变量加载配置，多层覆盖。

        全局模型：API_KEY / API_BASE / MODEL_NAME
        选择器：  SELECTOR_API_KEY 等，未设置回退到全局模型
        运行参数：IMS_WORKSPACE / MAX_TURNS
        """
        cfg = cls()

        # 全局模型
        cfg.model.api_key = os.getenv("API_KEY", cfg.model.api_key)
        cfg.model.api_base = os.getenv("API_BASE", cfg.model.api_base)
        cfg.model.model_name = os.getenv("MODEL_NAME", cfg.model.model_name)

        # 选择器模型（未配置时回退到全局）
        cfg.selector_model.api_key = (
            os.getenv("SELECTOR_API_KEY") or cfg.model.api_key
        )
        cfg.selector_model.api_base = (
            os.getenv("SELECTOR_API_BASE") or cfg.model.api_base
        )
        cfg.selector_model.model_name = (
            os.getenv("SELECTOR_MODEL_NAME") or cfg.model.model_name
        )

        # 运行参数
        cfg.workspace = os.getenv("IMS_WORKSPACE", cfg.workspace)
        raw_turns = os.getenv("MAX_TURNS", "")
        if raw_turns:
            cfg.max_turns = int(raw_turns)

        return cfg

    def role_model(self, role: str) -> ModelConfig:
        """获取指定角色的模型配置。

        规则：{ROLE}_MODEL_NAME → MODEL_NAME → 默认值
              {ROLE}_API_KEY   → API_KEY   → 默认值
              {ROLE}_API_BASE  → API_BASE  → 默认值

        Args:
            role: 角色前缀，如 "PM"、"ARCHITECT"、"DEVELOPER"、"QA"
        """
        mc = ModelConfig()
        mc.api_key = os.getenv(f"{role}_API_KEY") or self.model.api_key
        mc.api_base = os.getenv(f"{role}_API_BASE") or self.model.api_base
        mc.model_name = (
            os.getenv(f"{role}_MODEL_NAME") or self.model.model_name
        )
        return mc


# ── 全局单例 ──────────────────────────────────────────

_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """获取全局配置单例（懒加载，首次调用时从环境变量加载）。"""
    global _config
    if _config is None:
        _config = AppConfig.from_env()
    return _config


def reload_config() -> AppConfig:
    """重新加载配置（修改 .env 后调用，或测试用）。"""
    global _config
    _config = AppConfig.from_env()
    return _config
