import asyncio
print("start")

async def main():
    print("before sleep")
    await asyncio.sleep(0.1)
    print("after sleep")

asyncio.run(main())
print("done")
