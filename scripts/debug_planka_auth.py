import asyncio
import httpx
import os
from dotenv import load_dotenv

async def check_planka_auth():
    # Try to load from .env.planka if it exists
    load_dotenv(".env.planka")
    
    url = "http://localhost:1337/api/access-tokens"
    email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@example.com")
    pw = os.getenv("DEFAULT_ADMIN_PASSWORD", "OpenZeroAdmin123$")
    
    print(f"Checking Planka Auth at {url} for {email}...")
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json={
                "emailOrUsername": email,
                "password": pw
            })
            print(f"Status: {resp.status_code}")
            print(f"Body: {resp.text}")
            
            # Check cookies
            print(f"Cookies: {resp.cookies}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_planka_auth())
