import asyncio
import os
from anp.anp_crawler import ANPCrawler
from pathlib import Path
from openai import AsyncOpenAI


async def main():
    print("🚀 ANPCrawler + OpenAI 智能客户端")
    print("连接到视频搜索服务 (localhost:8000)\n")

    # 初始化 OpenAI 客户端
    client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY", "xxx"),
        base_url=os.getenv("OPENAI_BASE_URL", "http://xxx/v1")
    )
    model = os.getenv("OPENAI_MODEL", "xxx")

    # 初始化 ANPCrawler
    print("=" * 60)
    print("步骤 1: 初始化 ANPCrawler")
    print("=" * 60)

    crawler = ANPCrawler(
        did_document_path="./client_did_keys/did.json",
        private_key_path="./client_did_keys/key-1_private.pem",
        cache_enabled=True
    )
    print("✓ ANPCrawler 初始化完成 (启用 DID-WBA 认证)\n")

    # 连接到服务端并发现工具
    print("=" * 60)
    print("步骤 2: 发现远程 Agent")
    print("=" * 60)

    server_url = "http://localhost:8000/ad.json"
    print(f"正在连接: {server_url}")

    try:
        content_json, interfaces_list = await crawler.fetch_text(server_url)
        print(f"✓ 成功获取 Agent 描述")
        print(f"  发现 {len(interfaces_list)} 个接口\n")
    except Exception as e:
        print(f"✗ 连接失败: {str(e)}")
        return

        # 获取可用工具列表
    tools = crawler.list_available_tools()
    print(f"可用工具: {tools}\n")

    # 将 ANP 接口转换为 OpenAI Tools 格式
    openai_tools = interfaces_list


    print("智能查询模式 (输入 'quit' 退出)")


    messages = [
        {
            "role": "system",
            "content": "你是一个视频搜索助手。用户会用自然语言描述他们想搜索的视频,你需要调用合适的工具来帮助他们搜索。并返回对应的视频信息，包含url"
        }
    ]

    while True:
        # 获取用户输入
        user_query = input("\n💬 输入查询: ").strip()

        if user_query.lower() in ['quit', 'exit', '退出']:
            print("\n👋 再见!")
            break

        if not user_query:
            continue

        messages.append({"role": "user", "content": user_query})

        try:
            # 调用 OpenAI 进行工具选择
            print("\n🤔 正在分析您的查询...")
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=openai_tools,
                tool_choice="auto"
            )

            response_message = response.choices[0].message
            messages.append(response_message)

            # 检查是否需要调用工具
            if response_message.tool_calls:
                print(f"✓ 识别到 {len(response_message.tool_calls)} 个工具调用\n")

                # 执行所有工具调用
                for tool_call in response_message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = eval(tool_call.function.arguments)

                    print(f"🔧 调用工具: {tool_name}")
                    print(f"   参数: {tool_args}")

                    # 使用 ANPCrawler 执行工具调用
                    result = await crawler.execute_tool_call(
                        tool_name=tool_name,
                        arguments=tool_args
                    )

                    if result.get("success"):
                        data = result.get("result", {})
                        print(f"✓ 搜索成功! 找到 {data.get('count', 0)} 个结果\n")

                        # 将结果添加到对话历史
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(data)
                        })
                    else:
                        error_msg = result.get("error", "未知错误")
                        print(f"✗ 搜索失败: {error_msg}\n")
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": f"错误: {error_msg}"
                        })

                        # 让 OpenAI 总结结果
                print("📊 正在生成结果摘要...")
                final_response = await client.chat.completions.create(
                    model=model,
                    messages=messages
                )

                assistant_message = final_response.choices[0].message.content
                messages.append({"role": "assistant", "content": assistant_message})

                print(f"\n🤖 助手: {assistant_message}")

            else:
                # 没有工具调用,直接返回回复
                print(f"\n🤖 助手: {response_message.content}")

        except Exception as e:
            print(f"\n✗ 处理查询时出错: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())