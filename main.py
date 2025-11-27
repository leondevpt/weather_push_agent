import os
import aiohttp
from dotenv import load_dotenv
from datetime import datetime
from pydantic import BaseModel, Field  # 用于参数校验

# LangChain 核心导入（1.0+ 版本）
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.messages import HumanMessage, SystemMessage
# 定时任务 + FastAPI 导入
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from contextlib import asynccontextmanager
from llm import get_llm

# 加载环境变量
load_dotenv()
app = FastAPI()

# ---------------------- Agent 全局实例 ----------------------
agent_instance = None
agent_tools = {}

# ---------------------- 全局配置（从.env读取，支持动态调整）-------------------------
TARGET_CITY = os.getenv("TARGET_CITY", "杭州")
AMAP_API_KEY = os.getenv("AMAP_API_KEY")
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL")

# ---------------------- 2. 飞书推送工具（v1.0）---------------- -------------------
class FeishuMessageInput(BaseModel):
    """飞书推送工具的输入参数模型"""
    content: str = Field(description="要推送的文本内容（支持 Markdown 格式）")

@tool(
    "send_feishu_message",  # 自定义工具名（位置参数）
    args_schema=FeishuMessageInput  # 仅保留支持的参数
)
async def send_feishu_message(content: str) -> str:
    """
    通过飞书 Webhook 推送用户传入的content文本/Markdown消息给用户/群聊
    【输入参数】
    - content：必填，消息内容（支持换行、Markdown 标题/分隔线等）。
    【输出】推送结果（成功/失败提示）。
    """

    if not os.getenv("FEISHU_WEBHOOK_URL"):
        return "❌ 工具配置错误：飞书 Webhook 地址未配置（工具版本：v1.0）"
    
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {"title": {"tag": "plain_text", "content": "🌤️ 每日天气报告与建议"}, "style": "blue"},
            "elements": [{"tag": "markdown", "content": content}],
            "footer": {
                "tag": "plain_text",
                "content": f"推送时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 工具版本：v1.0"
            }
        }
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                os.getenv("FEISHU_WEBHOOK_URL"),
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            ) as response:
                response.raise_for_status()
                result = await response.json()
                if result.get("code") == 0:
                    return f"✅ 飞书消息推送成功（工具版本：v1.0）：{result.get('msg', '未知错误')}"
    except Exception as e:
        return f"❌ 飞书推送工具异常（工具版本：v1.0）：{str(e)}"

# ---------------------- 3. 初始化 LangChain Agent（适配版本化工具）----------------------
async def init_weather_push_agent():
    """初始化天气 Agent，加载版本化工具"""
    # 加载远端 MCP 工具并直接注入 Agent，同时保留本地推送工具
    mcp_config = {
        "amap-maps-streamableHTTP": {
            "url": f"https://mcp.amap.com/mcp?key={os.getenv('AMAP_API_KEY')}",
            "transport": "streamable_http",
            "timeout": 15,
        }
    }
    client = MultiServerMCPClient(mcp_config)
    mcp_tools = await client.get_tools()
    langchain_tools = list(mcp_tools) + [send_feishu_message]
    tool_names = [getattr(t, "name", "") for t in langchain_tools]
    tool_desc_text = "\n".join([
        f"{getattr(t, 'name', '')}: {getattr(t, 'description', getattr(t, '__doc__', '') or '')}" 
        for t in langchain_tools
    ])
    # LLM 配置
    provider = os.getenv("DEFAULT_PUSH_AGENT_LLM_PROVIDER")
    if not provider:
        llm = get_llm()
    else:
        if provider not in ["qwen", "gemini"]:
            llm = get_llm()
        else:
            llm = get_llm(provider)
    
    # 创建 React Agent（LangChain 1.0+ 推荐）
    agent = create_agent(
        model=llm,
        tools=langchain_tools,
        debug=True
    )
    return agent, tool_names, tool_desc_text

# ---------------------- 4. 定时任务调度-------------------------------------
async def run_weather_push_agent():
    """执行天气 Agent 任务（异步）"""
    global agent_instance, agent_tools
    if not agent_instance:
        print("Agent尚未初始化，请等待应用启动完成。")
        return

    print(f"\n=== 定时任务触发：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    try:
        agent = agent_instance
        tool_names = agent_tools.get("tool_names", [])
        tool_desc_text = agent_tools.get("tool_desc_text", "")
        tools_text = ", ".join(tool_names)
        system_prompt = (
            f"""
            你是一个自动化天气推送 Agent，核心任务是查询指定城市的天气并通过飞书推送完整、实用的天气报告。
            请严格遵守以下规则，确保报告精准、建议细化且符合用户日常出行需求：

            1. 工具使用约束：
            - 仅使用提供的工具，工具名必须完全匹配：{tools_text}
            - 工具使用说明：{tool_desc_text}
            - 必须使用用户提供的「目标城市」查询，无需询问用户，不允许修改城市；
            - 若工具返回错误（如API失效、数据缺失），直接终止任务并返回错误信息，不重试。

            2. 执行流程：
            第一步：调用天气查询工具，获取「实时天气+今日预报+未来N天预报」完整数据（含温度、风力、湿度、天气现象）；
            第二步：基于天气数据生成结构化报告（Markdown格式），重点细化「出行与穿衣建议」；
            第三步：调用推送工具发送完整报告，无需额外交互；
            第四步：返回「今日天气推送已完成（城市：查询的城市名称）」的确认信息。

            3. 报告结构要求（推送内容为Markdown格式）：
            - 标题：【查询的城市名称天气报告】（搭配🌤️/🌧️/❄️等对应天气emoji）
            - 📌 实时天气（温度、湿度、风向、风力、更新时间）
            - 📅 今日预报（日间/夜间天气、气温范围、风向风力）
            - 🔮 未来N天预报（每天显示：日期+周X、天气、气温范围、关键建议，如「带雨具」「注意保暖」）
            - 🎯 出行与穿衣建议（核心细化部分，按以下规则生成）
            - 底部标注：数据来源（高德MCP服务）+ 推送时间

            4. 「出行与穿衣建议」细化规则（必须严格按阈值判断，不模糊表述）：
            （1）温度分档穿衣建议：
            - 严寒（≤0℃）：穿羽绒服+厚毛衣+加绒裤+雪地靴，佩戴围巾、手套、帽子，注意防冻伤；
            - 寒冷（1~10℃）：穿厚外套（呢大衣/冲锋衣）+ 毛衣+保暖裤+棉鞋，室内外温差大，建议洋葱式穿衣（方便增减）；
            - 凉爽（11~18℃）：穿薄外套（风衣/夹克）+ 长袖T恤/针织衫+长裤+单鞋，早晚偏凉可加围巾；
            - 适宜（19~25℃）：穿短袖T恤/薄针织衫+长裤/短裙+帆布鞋，舒适度高，无需额外保暖；
            - 炎热（26~32℃）：穿短袖+短裤/短裙+凉鞋，注意防晒（涂防晒霜、戴帽子），补充水分；
            - 酷热（≥33℃）：穿透气浅色短袖+短裤+凉拖，避免正午高温时段外出，谨防中暑。

            （2）风力专项建议：
            - 微风（≤3级）：无特殊影响，正常出行；
            - 和风（4~5级）：穿防风外套，长发建议扎起，户外搭建物（如帐篷）需加固；
            - 大风（≥6级）：尽量减少外出，如需出行穿防风性能好的衣物，远离广告牌、大树等易被吹倒物体。

            （3）湿度专项建议：
            - 高湿（≥70%）：穿透气吸汗的衣物，南方梅雨季注意防潮，关节不适者需保暖；
            - 低湿（≤30%）：多喝水补充水分，涂抹保湿霜，呼吸道敏感者可佩戴口罩。

            （4）天气现象专项建议：
            - 晴/多云：做好防晒（SPF30+防晒霜、遮阳帽），长时间户外建议携带遮阳伞；
            - 雨（小雨/中雨/大雨）：携带折叠伞或穿雨衣，穿防滑鞋，注意路面湿滑；暴雨天气避免低洼路段出行；
            - 雪（小雪/中雪/大雪）：穿防水防滑雪地靴，佩戴防雪镜，驾车减速慢行，注意道路结冰；
            - 雾/霾：能见度低，驾车开启雾灯、保持车距；霾天佩戴N95口罩，减少户外停留时间；
            - 雷阵雨：避免在户外逗留，远离大树、电线杆等高大物体，不使用金属雨伞。

            （5）综合建议优先级：
            - 极端天气（暴雨、暴雪、大风、高温）优先提示安全风险（如「避免外出」「谨防中暑」）；
            - 多重因素叠加（如「10℃+5级风+60%湿度」）：综合给出建议（如「穿厚外套+防风围巾，保持衣物透气」）；
            - 未来几天有降雨/降温：提前提醒（如「明日有雨，建议随身携带雨具；后天降温5℃，需增加衣物」）。

            5. 格式约束：
            - 所有建议使用「• 」开头的列表形式，简洁明了，不超过3行/条；
            - 避免专业术语，用生活化语言（如「加绒裤」而非「保暖裤袜」，「帆布鞋」而非「休闲鞋履」）；
            - 天气现象与emoji对应（晴🌞、阴🌥️、雨🌧️、雪❄️、雾🌫️、霾😷），增强可读性；
            - 不添加无关内容，报告总长度控制在手机一屏可浏览（约500字内）。
            """
        )
        human_prompt = (
            f"目标城市：{TARGET_CITY}\n"
            f"当前时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "请执行天气查询和推送任务。"
        )
        result = await agent.ainvoke({
            "messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ]
        })
        print(f"任务执行结果：{result}\n")
    except Exception as e:
        print(f"任务执行失败：{str(e)}\n")

def init_scheduler():
    """初始化定时任务调度器（北京时间）"""
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        run_weather_push_agent,
        trigger="cron",
        hour=os.getenv("CRON_HOUR", 8),
        minute=os.getenv("CRON_MINUTE", 0),
        id="daily_weather_push_v1.0",
        replace_existing=True,
        misfire_grace_time=300  # 允许延迟5分钟执行
    )
    return scheduler

# ---------------------- 5. FastAPI 生命周期（lifespan）----------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化Agent并启动定时任务，关闭时清理资源"""
    global agent_instance, agent_tools
    print("=== 应用启动，开始初始化WeatherAgent ===")
    agent_instance, tool_names, tool_desc_text = await init_weather_push_agent()
    agent_tools = {
        "tool_names": tool_names,
        "tool_desc_text": tool_desc_text
    }

    print(f"工具列表:\n{tool_names}\n")
    print(f"工具列表描述:\n{tool_desc_text}\n")
    print("=== WeatherAgent初始化完成 ===")

    scheduler = init_scheduler()
    scheduler.start()
    print("=== 天气Agent定时任务调度器已启动 ===")
    print(f"配置信息：城市={TARGET_CITY} | 每日{os.getenv('CRON_HOUR', 8)}:{os.getenv('CRON_MINUTE', '00')}推送")
    try:
        yield
    finally:
        scheduler.shutdown()
        print("=== 天气Agent定时任务调度器已关闭 ===")

app.router.lifespan_context = lifespan

# ---------------------- 6. 测试接口（支持手动触发天气查询推送和工具版本查询）----------------------
@app.get("/")
async def root():
    return {
        "message": "天气查询推送Agent服务运行中",
    }

@app.get("/trigger-weather")
async def trigger_weather():
    """手动触发天气推送"""
    await run_weather_push_agent()
    return {"message": "手动触发天气推送成功", "tool_versions": {"天气工具": "v1.0", "推送工具": "v1.0"}}

@app.get("/version")
async def get_tool_versions():
    """查询当前工具版本和元信息"""
    return {
        "detail": {
            "version": "v1.0",
            "description": "查询指定城市的天气并通过飞书推送完整、实用的天气报告" + "..."
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
