from browser_use import Browser
import asyncio

async def main():
    browser = Browser(headless=True)
    print(f"Type: {type(browser)}")
    print(f"Dir: {dir(browser)}")
    try:
        if hasattr(browser, 'close'):
            print("Has close()")
            await browser.close()
        else:
            print("No close()")
    except Exception as e:
        print(f"Error closing: {e}")

if __name__ == "__main__":
    asyncio.run(main())
