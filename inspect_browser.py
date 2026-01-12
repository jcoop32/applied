import inspect
from browser_use import Browser, Agent
try:
    from browser_use import BrowserConfig
    print("BrowserConfig found")
    print(inspect.signature(BrowserConfig))
except ImportError:
    print("BrowserConfig not found")

print("Browser signature:")
print(inspect.signature(Browser))
