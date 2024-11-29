from typing import Union, Type
from . import language_adapters

# API CONFIGURATION
API_KEY: Union[str, None] = "sk-aG6lb5DqGaKHj3bv5b9dA2A76eE14948Bf1857F451B8820a"
ORG_KEY: Union[str, None] = None
MODEL: str = "gpt-4o" # DEFAULT MODEL
API_BASE: str = "https://oneapi.deepwisdom.ai/v1"


# AutoTestGen CONFIGURATION
ADAPTER: Type[language_adapters.BaseAdapter] = None