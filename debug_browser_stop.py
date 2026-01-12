from browser_use import Browser
import asyncio

async def main():
    browser = Browser(headless=True)
    print("Browser created.")
    # Simulate some work
    print("Simulating work...")
    
    if hasattr(browser, 'stop'):
        print("Calling stop()...")
        await browser.stop() # stop is likely async? Wait, check dir output again.
        # dir output just lists method names.
        # Usually stop is async in these frameworks.
        print("Stop called.")
    else:
        print("No stop() method.")

if __name__ == "__main__":
    asyncio.run(main())
