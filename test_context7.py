import os
from dotenv import load_dotenv
from mcp import StdioServerParameters
from smolagents import ToolCollection, ToolCallingAgent
import asyncio

# Load the .env file to get CONTEXT7_API_KEY
load_dotenv()

async def test_mcp():
    print("Testing Context7 MCP connection...")
    
    # Configure the MCP server for Context7.
    # NOTE : le package npm historique @context7/mcp n'existe plus (404).
    # Le serveur officiel est désormais publié par Upstash sous @upstash/context7-mcp.
    server_parameters = StdioServerParameters(
        command="npx",
        args=["-y", "@upstash/context7-mcp"],
        env=os.environ.copy()
    )

    try:
        with ToolCollection.from_mcp(server_parameters, trust_remote_code=True) as tool_collection:
            print("Successfully connected to Context7 MCP Server!")
            print("Available tools:")
            for tool in tool_collection.tools:
                print(f"- {tool.name}: {tool.description[:50]}...")
                
            print("\nTest successful! The Coder node will be able to use these tools.")
    except Exception as e:
        print(f"Error connecting to Context7 MCP: {e}")

if __name__ == "__main__":
    asyncio.run(test_mcp())
