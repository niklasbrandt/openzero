import asyncio
import httpx

async def main():
    async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(uds="/var/run/docker.sock")) as client:
        resp = await client.get("http://docker/containers/openzero-pihole-1/json")
        data = resp.json()
        status = data.get("State", {}).get("Health", {}).get("Status")
        print(f"Health Status: {status}")

asyncio.run(main())
