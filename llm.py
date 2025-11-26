from langchain_openai import ChatOpenAI
from pydantic import SecretStr
import os
from dotenv import load_dotenv
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

logger = logging.getLogger(__name__)

load_dotenv()

tongyi_llm = ChatOpenAI(
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    api_key=SecretStr(os.getenv("DASHSCOPE_API_KEY")),
    model="qwen-plus",
    temperature=0.7,
)

# 默认配置
DEFAULT_LLM_PROVIDER = "qwen"
DEFAULT_LLM_MODEL = "qwen-plus"
DEFAULT_TEMPERATURE = 0.7



# 模型配置字典
llm_model_configs = {
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": SecretStr(os.getenv("DASHSCOPE_API_KEY")),
        "chat_model": os.getenv("DASHSCOPE_API_MODEL", "qwen-plus"),
        "embedding_model": "text-embedding-v1",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key": SecretStr(os.getenv("GEMINI_API_KEY")),
        "chat_model": os.getenv("GEMINI_API_MODEL", DEFAULT_LLM_MODEL),
        "embedding_model": "gemini-embedding-001",
    },
}


class LLMInitializationError(Exception):
    """自定义异常类用于LLM初始化错误"""

    pass


def init_llm(llm_provider: str = DEFAULT_LLM_PROVIDER) -> ChatOpenAI:
    """
    初始化LLM实例

    Args:
        llm_provider (str): LLM供应商，可选值为 'qwen', 'gemini'

    Returns:
        ChatOpenAI: 初始化后的LLM实例

    Raises:
        LLMInitializationError: 当LLM初始化失败时抛出
    """
    try:
        if llm_provider not in llm_model_configs:
            raise LLMInitializationError(f"不支持的LLM供应商: {llm_provider}")

        model_config = llm_model_configs[llm_provider]
        logger.info(f"初始化 {llm_provider} LLM 模型配置: {model_config}")
        api_key = model_config["api_key"]
        if api_key is None or (hasattr(api_key, "get_secret_value") and not api_key.get_secret_value()):
            raise LLMInitializationError(f"{llm_provider} 的 API Key 未配置")
        llm = ChatOpenAI(
            base_url=model_config["base_url"],
            api_key=model_config["api_key"],
            model=model_config["chat_model"],
            temperature=DEFAULT_TEMPERATURE,
            timeout=30,
            max_retries=1,
        )
        logger.info(f"成功初始化 {llm_provider} LLM")
        return llm
    except Exception as e:
        raise LLMInitializationError(f"LLM初始化失败: {str(e)}")


def _detect_provider() -> str:
    if os.getenv("DASHSCOPE_API_KEY"):
        return "qwen"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"

    return DEFAULT_LLM_PROVIDER


def get_llm(llm_provider: str | None = None) -> ChatOpenAI:
    """
    获取LLM实例

    Args:
        llm_provider (str): LLM供应商，可选值为 'qwen', 'gemini'

    Returns:
        ChatOpenAI: 初始化后的LLM实例

    Raises:
        LLMInitializationError: 当LLM初始化失败时抛出
    """

    try:
        provider = llm_provider or _detect_provider()
        logger.info(f"检测到LLM供应商: {provider}")
        return init_llm(provider)
    except LLMInitializationError as e:
        logger.warning(f"使用默认配置重试: {str(e)}")
        if (llm_provider or DEFAULT_LLM_PROVIDER) != DEFAULT_LLM_PROVIDER:
            return init_llm(DEFAULT_LLM_PROVIDER)
        raise  # 如果默认配置也失败，则抛出异常

# 示例使用
if __name__ == "__main__":
    try:
        # 测试不同类型的LLM初始化
        llm_openai = get_llm("gemini")
        llm_qwen = get_llm("qwen")
        # 测试无效类型
        llm_invalid = get_llm("openai")
    except LLMInitializationError as e:
        logger.error(f"程序终止: {str(e)}")
