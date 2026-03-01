import asyncio
import httpx
import sys

BASE_URL = "http://localhost:8000"

async def test_endpoint(name, method, path, json_data=None):
    print(f"🧪 Testing {name}...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if method == "GET":
                resp = await client.get(f"{BASE_URL}{path}")
            else:
                resp = await client.post(f"{BASE_URL}{path}", json=json_data)
            
            if resp.status_code == 200:
                print(f"✅ {name} Success")
                return resp.json()
            else:
                print(f"❌ {name} Failed with status {resp.status_code}")
                print(resp.text)
                return None
        except Exception as e:
            print(f"❌ {name} Error: {e}")
            return None

async def run_suite():
    print("🚀 Starting openZero Regression Suite\n")
    
    # 1. System Health
    await test_endpoint("System API", "GET", "/api/dashboard/system")
    
    # 2. Intelligence Scaling & Action Execution
    chat_resp = await test_endpoint("Chat Intelligence", "POST", "/api/dashboard/chat", {
        "message": "Think about our projects and create a test board called 'Regression Test' with a description 'Suite verified'.",
        "history": []
    })
    
    if chat_resp:
        print(f"🤖 Z Reply: {chat_resp.get('reply')}")
        print(f"🛠️ Actions Executed: {chat_resp.get('actions')}")
        print(f"🧠 Model Used: {chat_resp.get('model')}")

    # 3. Local Memory Sync
    await test_endpoint("Add Memory", "POST", "/api/dashboard/chat", {
        "message": "/add Testing persistence mechanism 1.2.3",
        "history": []
    })
    
    search_resp = await test_endpoint("Search Memory", "POST", "/api/dashboard/chat", {
        "message": "/memory 1.2.3",
        "history": []
    })
    if search_resp and "1.2.3" in search_resp.get("reply", ""):
        print("✅ Memory Persistence Verified")
    else:
         print("❌ Memory Sync Failed")

    # 4. Life Tree Generation
    await test_endpoint("Life Tree", "GET", "/api/dashboard/life-tree")

    print("\n🏁 Suite Complete.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        BASE_URL = sys.argv[1]
    asyncio.run(run_suite())
