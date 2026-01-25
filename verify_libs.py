
import inspect
import asyncio
try:
    from browser_use import Browser
    print("Browser class found")
    print(inspect.signature(Browser.__init__))
except ImportError:
    print("browser_use not found")

try:
    import camoufox
    print("camoufox imported")
    print(dir(camoufox))
except ImportError:
    print("camoufox not found")
