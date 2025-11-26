from langchain_mcp_adapters.client import MultiServerMCPClient
import os
import asyncio
from langchain.agents import create_agent
from llm import tongyi_llm


async def create_amap_mcp_client():
    amap_key = os.getenv("AMAP_API_KEY")
    print("amap_key", amap_key)
    mcp_config = {
        "amap-maps-streamableHTTP": {
            "url": f"https://mcp.amap.com/mcp?key={amap_key}",
            "transport": "streamable_http",
        }
    }
    client = MultiServerMCPClient(mcp_config)
    tools = await client.get_tools()
    return client, tools


async def create_and_run_amap_mcp_client():
    client, tools = await create_amap_mcp_client()

    agent = create_agent(
        model=tongyi_llm,
        tools=tools,
    )
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "杭州明天天气怎么样？"}]}
    )
    print(result)


asyncio.run(create_and_run_amap_mcp_client())
